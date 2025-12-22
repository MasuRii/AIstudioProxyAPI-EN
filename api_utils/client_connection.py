import asyncio
from asyncio import Event, Task
from typing import Any, Callable, Coroutine, Dict, Tuple

from fastapi import HTTPException, Request

from models import ClientDisconnectedError


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
                    # If it didn't complete immediately, proceed to fallback check
            except asyncio.CancelledError:
                raise
            except Exception:
                # If checking fails, proceed to fallback
                pass

        # Fallback to is_disconnected() if available (Starlette/FastAPI)
        # Wrap in wait_for to prevent infinite hang in some ASGI implementations
        if hasattr(http_request, "is_disconnected"):
            try:
                if await asyncio.wait_for(http_request.is_disconnected(), timeout=0.01):
                    return False
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # If it times out, it's likely still connected
                return True
            except Exception:
                return False

        return True
    except asyncio.CancelledError:
        raise
    except Exception:
        return False


async def enhanced_disconnect_monitor(
    req_id: str,
    http_request: Request,
    completion_event: asyncio.Event,
    logger: Any,
) -> bool:
    """
    Monitors for client disconnect during streaming.
    Returns True if disconnected, False otherwise.
    """
    disconnect_detection_count = 0
    while not completion_event.is_set():
        try:
            is_connected = await check_client_connection(req_id, http_request)
            if not is_connected:
                disconnect_detection_count += 1
                if disconnect_detection_count >= 3:
                    logger.info(
                        f"[{req_id}] Client disconnect confirmed during streaming."
                    )
                    completion_event.set()
                    return True
            else:
                disconnect_detection_count = 0
            await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[{req_id}] Error in enhanced_disconnect_monitor: {e}")
            break
    return False


async def non_streaming_disconnect_monitor(
    req_id: str,
    http_request: Request,
    result_future: asyncio.Future,
    logger: Any,
) -> bool:
    """
    Monitors for client disconnect during non-streaming processing.
    Returns True if disconnected, False otherwise.
    """
    while not result_future.done():
        try:
            is_connected = await check_client_connection(req_id, http_request)
            if not is_connected:
                logger.info(
                    f"[{req_id}] Client disconnect detected during non-streaming."
                )
                if not result_future.done():
                    result_future.set_exception(
                        HTTPException(status_code=499, detail="Client disconnected")
                    )
                return True
            await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[{req_id}] Error in non_streaming_disconnect_monitor: {e}")
            break
    return False


async def setup_disconnect_monitoring(
    req_id: str, http_request: Request, result_future
) -> Tuple[Event, asyncio.Task, Callable]:
    from api_utils.server_state import state

    logger = state.logger

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
                        logger.info(
                            f"[{req_id}] Active detection of client disconnect (consecutive {disconnect_count} times)."
                        )
                        client_disconnected_event.set()
                        if not result_future.done():
                            result_future.set_exception(
                                HTTPException(
                                    status_code=499,
                                    detail=f"[{req_id}] Client closed the request",
                                )
                            )
                        break
                    else:
                        logger.debug(
                            f"[{req_id}] Active detection of potential disconnect (round {disconnect_count}/{disconnect_threshold})"
                        )
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
