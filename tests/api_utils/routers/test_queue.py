import asyncio
import json
import time
from unittest.mock import MagicMock

import pytest
from fastapi.responses import JSONResponse

from api_utils.routers.queue import (
    cancel_queued_request,
    cancel_request,
    get_queue_status,
)


@pytest.mark.asyncio
async def test_cancel_queued_request_found():
    """Test cancelling a request that is in the queue."""
    req_id = "req_123"
    queue = asyncio.Queue()
    logger = MagicMock()

    # Create a mock item
    future = asyncio.Future()
    item = {"req_id": req_id, "result_future": future, "cancelled": False}
    await queue.put(item)

    # Add another item
    await queue.put({"req_id": "other_req"})

    result = await cancel_queued_request(req_id, queue, logger)

    assert result is True
    assert item["cancelled"] is True
    assert future.done()
    try:
        future.result()
    except Exception as e:
        assert "cancelled" in str(e).lower()

    # Verify queue state
    assert queue.qsize() == 2

    # Verify items are put back
    items = []
    while not queue.empty():
        items.append(await queue.get())

    assert len(items) == 2
    assert items[0]["req_id"] == req_id
    assert items[1]["req_id"] == "other_req"


@pytest.mark.asyncio
async def test_cancel_queued_request_not_found():
    """Test cancelling a request that is not in the queue."""
    req_id = "req_123"
    queue = asyncio.Queue()
    logger = MagicMock()

    await queue.put({"req_id": "other_req"})

    result = await cancel_queued_request(req_id, queue, logger)

    assert result is False
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_cancel_request_endpoint_success():
    """Test cancel_request endpoint when request is found."""
    req_id = "req_123"
    queue = asyncio.Queue()
    logger = MagicMock()

    # Add item to queue
    await queue.put({"req_id": req_id, "cancelled": False})

    response = await cancel_request(req_id, logger, queue)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200
    body = bytes(response.body).decode()
    assert "success" in body
    assert "marked as cancelled" in body


@pytest.mark.asyncio
async def test_cancel_request_endpoint_not_found():
    """Test cancel_request endpoint when request is not found."""
    req_id = "req_123"
    queue = asyncio.Queue()
    logger = MagicMock()

    response = await cancel_request(req_id, logger, queue)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    body = bytes(response.body).decode()
    assert "not found" in body


@pytest.mark.asyncio
async def test_get_queue_status():
    """Test get_queue_status endpoint."""
    queue = asyncio.Queue()
    lock = asyncio.Lock()

    # Add items
    mock_request = MagicMock()
    mock_request.stream = True

    item1 = {
        "req_id": "req_1",
        "enqueue_time": time.time() - 10,
        "request_data": mock_request,
        "cancelled": False,
    }
    item2 = {
        "req_id": "req_2",
        "enqueue_time": time.time() - 5,
        "request_data": mock_request,
        "cancelled": True,
    }

    await queue.put(item1)
    await queue.put(item2)

    # Lock the lock
    await lock.acquire()

    response = await get_queue_status(queue, lock)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200

    import json

    data = json.loads(bytes(response.body))

    assert data["queue_length"] == 2
    assert data["is_processing_locked"] is True
    assert len(data["items"]) == 2
    assert data["items"][0]["req_id"] == "req_1"
    assert data["items"][1]["req_id"] == "req_2"
    assert data["items"][0]["wait_time_seconds"] >= 10

    lock.release()


@pytest.mark.asyncio
async def test_get_queue_status_empty():
    """Test get_queue_status with empty queue."""
    queue = asyncio.Queue()
    lock = asyncio.Lock()

    response = await get_queue_status(queue, lock)

    data = json.loads(bytes(response.body))
    assert data["queue_length"] == 0
    assert data["items"] == []
    assert data["is_processing_locked"] is False


"""
Extended tests for api_utils/routers/queue.py - Coverage completion.

Focus: Cover the last 2 uncovered lines (62-63).
Strategy: Test exception handling when accessing queue._queue fails.
"""

from unittest.mock import PropertyMock


@pytest.mark.asyncio
async def test_get_queue_status_queue_access_exception():
    """
    Test scenario: Accessing queue._queue throws exception
    Expected: Return empty list, no interruption (lines 62-63)
    """
    # Create a mock queue that raises exception when _queue is accessed
    mock_queue = MagicMock(spec=asyncio.Queue)
    type(mock_queue)._queue = PropertyMock(side_effect=Exception("Queue access error"))

    mock_lock = MagicMock()
    mock_lock.locked.return_value = False

    # Execute: Call get_queue_status
    response = await get_queue_status(mock_queue, mock_lock)

    # Verify: Return success response, but queue_items is empty (line 63 executed)
    assert response.status_code == 200
    import json

    data = json.loads(bytes(response.body))

    # Verify: queue_length is 0 (because queue_items = [])
    assert data["queue_length"] == 0
    assert data["items"] == []
    assert data["is_processing_locked"] is False
