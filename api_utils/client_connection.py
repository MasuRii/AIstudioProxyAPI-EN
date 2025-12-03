import asyncio
from asyncio import Event, Task
from logging import Logger
from typing import Any, Callable, Coroutine, Dict, Protocol, Tuple

from fastapi import HTTPException, Request

from logging_utils import set_request_id
from models import ClientDisconnectedError


class SupportsReceive(Protocol):
    """Protocol for request objects that support _receive method."""

    def _receive(self) -> Coroutine[Any, Any, Dict[str, Any]]:
        """Internal method to receive messages from ASGI."""
        ...


async def check_client_connection(req_id: str, http_request: Request) -> bool:
    """
    Checks if the client is still connected.
    Returns True if connected, False if disconnected.
    """
    try:
        if hasattr(http_request, "_receive"):
            try:
                # Use a very short timeout to check for disconnect message
                # _receive is a private Starlette/FastAPI method that returns a coroutine
                receive_obj = http_request  # type: ignore[misc]
                receive_coro: Coroutine[Any, Any, Dict[str, Any]] = (
                    receive_obj._receive()
                )  # type: ignore[misc]
                receive_task: Task[Dict[str, Any]] = asyncio.create_task(receive_coro)
                done, pending = await asyncio.wait([receive_task], timeout=0.01)

                if done:
                    message = receive_task.result()
                    if message.get("type") == "http.disconnect":
                        return False
                else:
                    # Cancel the task if it didn't complete immediately
                    receive_task.cancel()
                    try:
                        await receive_task
                    except asyncio.CancelledError:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception:
                # If checking fails, assume disconnected to be safe, or log and continue?
                # Usually if _receive fails it might mean connection issues.
                return False

        # Fallback to is_disconnected() if available (Starlette/FastAPI)
        if await http_request.is_disconnected():
            return False

        return True
    except asyncio.CancelledError:
        raise
    except Exception:
        return False


async def setup_disconnect_monitoring(req_id: str, http_request: Request, result_future) -> Tuple[Event, asyncio.Task, Callable]:
    from server import logger
    client_disconnected_event = Event()
    disconnect_count = 0
    disconnect_threshold = 5  # Require 5 consecutive disconnect signals (1.5 seconds)

    async def check_disconnect_periodically():
        nonlocal disconnect_count
        while not client_disconnected_event.is_set():
            try:
                is_connected = await check_client_connection(req_id, http_request)
                if not is_connected:
                    disconnect_count += 1
                    if disconnect_count >= disconnect_threshold:
                        logger.info(f"[{req_id}] 主动检测到客户端断开连接 (连续 {disconnect_count} 次)。")
                        client_disconnected_event.set()
                        if not result_future.done():
                            result_future.set_exception(HTTPException(status_code=499, detail=f"[{req_id}] 客户端关闭了请求"))
                        break
                    else:
                        logger.debug(f"[{req_id}] 主动检测到潜在断开 (第 {disconnect_count}/{disconnect_threshold} 次)")
                else:
                    disconnect_count = 0  # Reset counter on successful connection

                if await http_request.is_disconnected():
                    disconnect_count += 1
                    if disconnect_count >= disconnect_threshold:
                        logger.info(f"[{req_id}] 备用检测到客户端断开连接 (连续 {disconnect_count} 次)。")
                        client_disconnected_event.set()
                        if not result_future.done():
                            result_future.set_exception(HTTPException(status_code=499, detail=f"[{req_id}] 客户端关闭了请求"))
                        break
                    else:
                        logger.debug(f"[{req_id}] 备用检测到潜在断开 (第 {disconnect_count}/{disconnect_threshold} 次)")
                else:
                    disconnect_count = 0  # Reset counter on successful connection
                    
                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                # Task cancelled, exit gracefully
                break
            except Exception as e:
                logger.error(f"(Disco Check Task) Error: {e}")
                client_disconnected_event.set()
                if not result_future.done():
                    result_future.set_exception(
                        HTTPException(
                            status_code=500,
                            detail=f"[{req_id}] Internal disconnect checker error: {e}",
                        )
                    )
                break

    disconnect_check_task = asyncio.create_task(check_disconnect_periodically())

    def check_client_disconnected(stage: str = "") -> bool:
        if client_disconnected_event.is_set():
            logger.info(f"Client disconnected detected at stage: '{stage}'")
            raise ClientDisconnectedError(
                f"[{req_id}] Client disconnected at stage: {stage}"
            )
        return False

    return client_disconnected_event, disconnect_check_task, check_client_disconnected