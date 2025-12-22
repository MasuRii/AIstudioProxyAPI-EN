import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from api_utils.client_connection import (
    check_client_connection,
    setup_disconnect_monitoring,
)
from models import ClientDisconnectedError


@pytest.mark.asyncio
async def test_check_client_connection_success():
    """Test successful client connection check."""
    req_id = "test_req"
    request = MagicMock(spec=Request)

    # Mock _receive to return a non-disconnect message
    async def mock_receive():
        return {"type": "http.request"}

    request._receive = mock_receive
    request.is_disconnected = AsyncMock(return_value=False)

    result = await check_client_connection(req_id, request)
    assert result is True


@pytest.mark.asyncio
async def test_check_client_connection_disconnected():
    """Test client connection check when disconnected."""
    req_id = "test_req"
    request = MagicMock(spec=Request)

    # Mock _receive to return a disconnect message
    async def mock_receive():
        return {"type": "http.disconnect"}

    request._receive = mock_receive

    result = await check_client_connection(req_id, request)
    assert result is False


@pytest.mark.asyncio
async def test_check_client_connection_timeout():
    """Test client connection check timeout."""
    req_id = "test_req"
    request = MagicMock(spec=Request)

    # Mock _receive to hang
    async def mock_receive():
        await asyncio.sleep(1)
        return {"type": "http.request"}

    request._receive = mock_receive
    request.is_disconnected = AsyncMock(return_value=False)

    # Should return True on timeout (assuming connected)
    result = await check_client_connection(req_id, request)
    assert result is True


@pytest.mark.asyncio
async def test_check_client_connection_exception():
    """Test client connection check exception."""
    req_id = "test_req"
    request = MagicMock(spec=Request)

    # Mock _receive to raise exception
    async def mock_receive():
        raise Exception("Connection error")

    request._receive = mock_receive

    result = await check_client_connection(req_id, request)
    assert result is False


@pytest.mark.asyncio
async def test_setup_disconnect_monitoring_active_disconnect():
    """Test disconnect monitoring when client actively disconnects."""
    req_id = "test_req"
    request = MagicMock(spec=Request)
    request.is_disconnected = AsyncMock(return_value=True)
    result_future = asyncio.Future()

    # Mock check_client_connection to return False (disconnected)
    with patch(
        "api_utils.client_connection.check_client_connection", new_callable=AsyncMock
    ) as mock_test:
        mock_test.return_value = False

        event, task, check_func = await setup_disconnect_monitoring(
            req_id, request, result_future
        )

        # Wait for task to process (threshold is 5 consecutive checks at 0.3s each)
        await asyncio.sleep(2.0)

        assert event.is_set()
        assert result_future.done()
        with pytest.raises(HTTPException) as exc:
            result_future.result()
        assert exc.value.status_code == 499

        # Verify check function raises error
        with pytest.raises(ClientDisconnectedError):
            check_func("test_stage")

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_setup_disconnect_monitoring_passive_disconnect():
    """Test disconnect monitoring when client passively disconnects (is_disconnected)."""
    req_id = "test_req"
    request = MagicMock(spec=Request)
    request.is_disconnected = AsyncMock(return_value=True)
    result_future = asyncio.Future()

    # Mock check_client_connection to return False, simulating that it detected the disconnect.
    with patch(
        "api_utils.client_connection.check_client_connection", new_callable=AsyncMock
    ) as mock_test:
        mock_test.return_value = False

        event, task, check_func = await setup_disconnect_monitoring(
            req_id, request, result_future
        )

        # Wait for task to process (threshold is 5 consecutive checks at 0.3s each)
        await asyncio.sleep(2.0)

        assert event.is_set()
        assert result_future.done()
        with pytest.raises(HTTPException) as exc:
            result_future.result()
        assert exc.value.status_code == 499

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_setup_disconnect_monitoring_exception():
    """Test disconnect monitoring handles exceptions."""
    req_id = "test_req"
    request = MagicMock(spec=Request)
    result_future = asyncio.Future()

    # Mock check_client_connection to raise exception
    with patch(
        "api_utils.client_connection.check_client_connection",
        side_effect=Exception("Monitor error"),
    ):
        event, task, check_func = await setup_disconnect_monitoring(
            req_id, request, result_future
        )

        # Wait for task to process
        await asyncio.sleep(0.1)

        assert event.is_set()
        assert result_future.done()
        with pytest.raises(HTTPException) as exc:
            result_future.result()
        assert exc.value.status_code == 500

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ============================================================================
# Edge Cases - check_client_connection
# ============================================================================


@pytest.mark.asyncio
async def test_check_client_connection_via_is_disconnected():
    """
    Test scenario: _receive timeout, but is_disconnected() returns True
    Expected: Return False (line 47)
    """
    req_id = "test_req"
    request = MagicMock(spec=Request)

    # _receive does not return disconnect immediately, but times out
    async def mock_receive():
        await asyncio.sleep(1)  # Will timeout in check
        return {"type": "http.request"}

    request._receive = mock_receive
    # is_disconnected() returns True
    request.is_disconnected = AsyncMock(return_value=True)

    # Execute
    result = await check_client_connection(req_id, request)

    # Verify: Return False (line 47 executed)
    assert result is False


@pytest.mark.asyncio
async def test_check_client_connection_outer_exception():
    """
    Test scenario: is_disconnected() throws exception
    Expected: Return False (lines 53-54)
    """
    req_id = "test_req"
    request = MagicMock(spec=Request)

    # _receive timeout
    async def mock_receive():
        await asyncio.sleep(1)
        return {"type": "http.request"}

    request._receive = mock_receive
    # is_disconnected() throws exception
    request.is_disconnected = AsyncMock(side_effect=Exception("is_disconnected error"))

    # Execute
    result = await check_client_connection(req_id, request)

    # Verify: Return False (lines 53-54 executed)
    assert result is False


# ============================================================================
# Edge Cases - setup_disconnect_monitoring
# ============================================================================


@pytest.mark.asyncio
async def test_setup_disconnect_monitoring_client_stays_connected():
    """
    Test scenario: Client stays connected, result_future completed by other task
    Expected: Monitoring task loops normally, executes sleep
    """
    req_id = "test_req"
    request = MagicMock(spec=Request)
    request.is_disconnected = AsyncMock(return_value=False)
    result_future = asyncio.Future()

    # Track check calls
    check_count = 0

    async def mock_check_connected(*args, **kwargs):
        nonlocal check_count
        check_count += 1
        if check_count >= 3:
            # Complete the future to stop the loop
            if not result_future.done():
                result_future.set_result({"status": "success"})
        return True  # Client stays connected

    with patch(
        "api_utils.client_connection.check_client_connection",
        new_callable=AsyncMock,
        side_effect=mock_check_connected,
    ):
        event, task, check_func = await setup_disconnect_monitoring(
            req_id, request, result_future
        )

        # Wait for multiple checks (0.3s sleep each in the monitoring loop)
        await asyncio.sleep(1.2)

        # Verify: Multiple checks performed
        assert check_count >= 3

        # Verify: future completed normally
        assert result_future.done()
        assert result_future.result() == {"status": "success"}

        # Verify: event not set (no disconnect)
        assert not event.is_set()

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_setup_disconnect_monitoring_task_cancelled():
    """
    Test scenario: Monitoring task cancelled
    Expected: CancelledError caught, task exits gracefully
    """
    req_id = "test_req"
    request = MagicMock(spec=Request)
    request.is_disconnected = AsyncMock(return_value=False)
    result_future = asyncio.Future()

    # Mock check to return True (connected), so it enters the sleep
    with patch(
        "api_utils.client_connection.check_client_connection",
        new_callable=AsyncMock,
        return_value=True,
    ):
        event, task, check_func = await setup_disconnect_monitoring(
            req_id, request, result_future
        )

        # Give it time to start one check cycle
        await asyncio.sleep(0.1)

        # Execute: Cancel task
        task.cancel()

        # Verify: Task cancelled
        # Task catches CancelledError and exits gracefully, will not re-throw
        try:
            await task
        except asyncio.CancelledError:
            # If it does raise, that's also fine
            pass

        # Verify: Task done
        assert task.done()

        # Verify: event not set (task cancelled, not disconnect)
        assert not event.is_set()


@pytest.mark.asyncio
async def test_check_client_disconnected_not_disconnected():
    """
    Test scenario: Call check_client_disconnected() but event not set
    Expected: Return False, no exception thrown
    """
    req_id = "test_req"
    request = MagicMock(spec=Request)
    request.is_disconnected = AsyncMock(return_value=False)
    result_future = asyncio.Future()

    # Mock check to keep client connected
    with patch(
        "api_utils.client_connection.check_client_connection",
        new_callable=AsyncMock,
        return_value=True,
    ):
        event, task, check_func = await setup_disconnect_monitoring(
            req_id, request, result_future
        )

        # Wait a bit but don't let it disconnect
        await asyncio.sleep(0.1)

        # Execute: Call check function
        result = check_func("test_stage")

        # Verify: Return False, no exception thrown
        assert result is False

        # Verify: event not set
        assert not event.is_set()

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
