from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from api_utils.routers.logs_ws import websocket_log_endpoint


@pytest.mark.asyncio
async def test_websocket_log_endpoint_success():
    """Test successful websocket connection and message loop."""
    websocket = AsyncMock(spec=WebSocket)
    logger = MagicMock()
    manager = AsyncMock()

    # Simulate one message then disconnect
    websocket.receive_text.side_effect = ["ping", WebSocketDisconnect()]

    await websocket_log_endpoint(websocket, logger, manager)

    # Verify connection
    manager.connect.assert_called_once()
    assert websocket.receive_text.call_count == 2

    # Verify disconnect
    manager.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_websocket_log_endpoint_no_manager():
    """Test endpoint when manager is None."""
    websocket = AsyncMock(spec=WebSocket)
    logger = MagicMock()

    await websocket_log_endpoint(websocket, logger, None)  # type: ignore[arg-type]

    websocket.close.assert_called_with(code=1011)


@pytest.mark.asyncio
async def test_websocket_log_endpoint_exception():
    """Test endpoint handling generic exception."""
    websocket = AsyncMock(spec=WebSocket)
    logger = MagicMock()
    manager = AsyncMock()

    # Simulate exception during receive
    websocket.receive_text.side_effect = Exception("Unexpected error")

    await websocket_log_endpoint(websocket, logger, manager)

    # Verify error logging
    logger.error.assert_called_once()

    # Verify disconnect is still called
    manager.disconnect.assert_called_once()
