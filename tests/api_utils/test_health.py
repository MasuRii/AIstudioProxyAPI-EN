from unittest.mock import MagicMock

import pytest
from fastapi.responses import JSONResponse

from api_utils.routers.health import health_check


@pytest.mark.asyncio
async def test_health_check_ok():
    """Test health check when everything is OK."""
    # Mock dependencies
    server_state = {
        "is_initializing": False,
        "is_playwright_ready": True,
        "is_browser_connected": True,
        "is_page_ready": True,
    }

    worker_task = MagicMock()
    worker_task.done.return_value = False

    request_queue = MagicMock()
    request_queue.qsize.return_value = 5

    # Run health check
    response = await health_check(server_state, worker_task, request_queue)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200

    content = bytes(response.body).decode()
    assert "OK" in content
    assert "Service running" in content
    assert "queueLength" in content


@pytest.mark.asyncio
async def test_health_check_initializing():
    """Test health check when initializing."""
    server_state = {
        "is_initializing": True,
        "is_playwright_ready": False,
        "is_browser_connected": False,
        "is_page_ready": False,
    }

    worker_task = None
    request_queue = None

    response = await health_check(server_state, worker_task, request_queue)  # type: ignore[arg-type]

    assert response.status_code == 503
    content = bytes(response.body).decode()
    assert "Error" in content
    assert "Initialization in progress" in content


@pytest.mark.asyncio
async def test_health_check_worker_stopped():
    """Test health check when worker is stopped."""
    server_state = {
        "is_initializing": False,
        "is_playwright_ready": True,
        "is_browser_connected": True,
        "is_page_ready": True,
    }

    worker_task = MagicMock()
    worker_task.done.return_value = True  # Stopped

    request_queue = MagicMock()
    request_queue.qsize.return_value = 0

    response = await health_check(server_state, worker_task, request_queue)

    assert response.status_code == 503
    content = bytes(response.body).decode()
    assert "Worker not running" in content


@pytest.mark.asyncio
async def test_health_check_no_browser():
    """Test health check when browser not connected."""
    server_state = {
        "is_initializing": False,
        "is_playwright_ready": True,
        "is_browser_connected": False,
        "is_page_ready": False,
    }

    worker_task = MagicMock()
    worker_task.done.return_value = False

    request_queue = MagicMock()
    request_queue.qsize.return_value = 0

    response = await health_check(server_state, worker_task, request_queue)

    assert response.status_code == 503
    content = bytes(response.body).decode()
    assert "Browser not connected" in content
    assert "Page not ready" in content
