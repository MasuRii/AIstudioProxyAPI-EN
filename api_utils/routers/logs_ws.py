import asyncio
import logging
import uuid

from fastapi import Depends, WebSocket, WebSocketDisconnect

from models import WebSocketConnectionManager

from ..dependencies import get_log_ws_manager, get_logger


async def websocket_log_endpoint(
    websocket: WebSocket,
    logger: logging.Logger = Depends(get_logger),
    log_ws_manager: WebSocketConnectionManager = Depends(get_log_ws_manager),
):
    if not log_ws_manager:
        await websocket.close(code=1011)
        return

    client_id = str(uuid.uuid4())
    try:
        await log_ws_manager.connect(client_id, websocket)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(
            f"Log WebSocket (client {client_id}) encountered an exception: {e}",
            exc_info=True,
        )
    finally:
        log_ws_manager.disconnect(client_id)
