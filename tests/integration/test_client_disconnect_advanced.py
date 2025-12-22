"""
Advanced integration tests for client disconnect detection during request processing.

These tests use REAL asyncio primitives to verify disconnect detection works
correctly in real-world async scenarios with actual timing and concurrency.

Test Strategy:
- Use real_server_state fixture (real asyncio.Lock, asyncio.Queue, asyncio.Event)
- Mock only external boundaries (browser, HTTP request)
- Test disconnect detection at various stages of processing
- Verify proper cleanup and resource release

Coverage Target: Disconnect detection integrity and resource cleanup
"""

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from api_utils.context_types import QueueItem


# Test stub for QueueManager used in these tests
class QueueManager:
    """Functional stub class for queue management in tests."""

    request_queue: Any = None
    processing_lock: Any = None
    logger: Any = None

    async def process_request(self, item: QueueItem) -> Any:
        """Call real process_request with item details."""
        from api_utils.request_processor import process_request

        return await process_request(
            item["req_id"],
            item["request_data"],
            item["http_request"],
            item["result_future"],
        )

    async def check_queue_disconnects(self) -> Any:
        """Stub check_queue_disconnects method."""
        from api_utils.client_connection import check_client_connection
        from api_utils.error_utils import client_disconnected

        queue_size = self.request_queue.qsize()
        items_to_requeue = []
        for _ in range(queue_size):
            try:
                item = self.request_queue.get_nowait()
                item_req_id = item.get("req_id")
                if not item.get("cancelled", False):
                    item_http_req = item.get("http_request")
                    if item_http_req:
                        try:
                            if not await check_client_connection(
                                item_req_id, item_http_req
                            ):
                                item["cancelled"] = True
                                item_fut = item.get("result_future")
                                if item_fut and not item_fut.done():
                                    item_fut.set_exception(
                                        client_disconnected(
                                            item_req_id,
                                            "Client disconnected while queued.",
                                        )
                                    )
                        except Exception as e:
                            self.logger.error(
                                f"[{item_req_id}] Error in disconnect check: {e}"
                            )
                items_to_requeue.append(item)
            except asyncio.QueueEmpty:
                break
        for item in items_to_requeue:
            await self.request_queue.put(item)


@pytest.mark.integration
class TestClientDisconnectDuringQueueWait:
    """Tests for disconnect detection while request waits in queue."""

    async def test_disconnect_detected_before_processing_starts(
        self, real_server_state
    ):
        """
        Test client disconnect is detected before request starts processing.

        Uses real asyncio.Lock to simulate lock contention scenario.
        """
        queue = real_server_state.request_queue
        lock = real_server_state.processing_lock
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.processing_lock = lock
        queue_manager.logger = MagicMock()

        # Mock task_done since we call process_request directly without queue.get()
        queue.task_done = MagicMock()

        # Create first request that holds the lock
        async def hold_lock_request():
            async with lock:
                # Hold lock for 0.5 seconds
                await asyncio.sleep(0.5)

        # Start first request (holds lock)
        lock_holder = asyncio.create_task(hold_lock_request())

        try:
            # Wait to ensure lock is acquired
            await asyncio.sleep(0.05)

            # Create second request that will wait for lock
            req_item = cast(
                QueueItem,
                {
                    "req_id": "waiting-req",
                    "request_data": MagicMock(),
                    "http_request": MagicMock(),
                    "result_future": asyncio.Future(),
                    "cancelled": False,
                    "enqueue_time": 0.0,
                },
            )

            # Client disconnects immediately
            req_item["http_request"].is_disconnected = AsyncMock(return_value=True)

            # Try to process (should detect disconnect before acquiring lock)
            with patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=False,
            ):
                await queue_manager.process_request(req_item)

            # Verify disconnect was detected and 499 error set
            assert req_item["result_future"].done()
            with pytest.raises(HTTPException) as exc:
                req_item["result_future"].result()
            assert exc.value.status_code == 499

            # Clear the exception from the future to prevent warning
            try:
                req_item["result_future"].exception()
            except Exception:
                pass

        finally:
            # Cleanup: cancel and wait for lock holder to finish
            lock_holder.cancel()
            try:
                await lock_holder
            except asyncio.CancelledError:
                pass

    async def test_multiple_disconnects_in_queue(self, real_server_state):
        """
        Test multiple client disconnects while waiting in queue.

        Verifies check_queue_disconnects works with real asyncio.Queue.
        """
        queue = real_server_state.request_queue
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.logger = MagicMock()

        # Create 5 requests: 1st, 3rd, 5th are disconnected
        disconnect_map = {0: True, 1: False, 2: True, 3: False, 4: True}
        items = []

        for i in range(5):
            item = cast(
                QueueItem,
                {
                    "req_id": f"req-{i}",
                    "http_request": MagicMock(),
                    "cancelled": False,
                    "result_future": asyncio.Future(),
                    "request_data": None,
                    "enqueue_time": 0.0,
                },
            )
            item["http_request"].is_disconnected = AsyncMock(
                return_value=disconnect_map[i]
            )
            items.append(item)
            await queue.put(item)

        # Check disconnects
        await queue_manager.check_queue_disconnects()

        # Verify disconnected items were cancelled
        assert items[0]["cancelled"] is True
        assert items[1]["cancelled"] is False
        assert items[2]["cancelled"] is True
        assert items[3]["cancelled"] is False
        assert items[4]["cancelled"] is True

        # Verify all futures for disconnected items are done with 499
        for i in [0, 2, 4]:
            assert items[i]["result_future"].done()
            with pytest.raises(HTTPException) as exc:
                items[i]["result_future"].result()
            assert exc.value.status_code == 499

        # Clear exceptions from futures to prevent warnings
        for i in [0, 2, 4]:
            try:
                items[i]["result_future"].exception()
            except Exception:
                pass


@pytest.mark.integration
class TestClientDisconnectDuringProcessing:
    """Tests for disconnect detection during active request processing."""

    async def test_disconnect_during_lock_acquisition(self, real_server_state):
        """
        Test disconnect detected while waiting to acquire processing_lock.

        Simulates scenario where client disconnects during lock contention.
        """
        queue = real_server_state.request_queue
        lock = real_server_state.processing_lock
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.processing_lock = lock
        queue_manager.logger = MagicMock()

        # Mock task_done since we call process_request directly without queue.get()
        queue.task_done = MagicMock()

        disconnect_tracker = {"value": False}

        # Hold lock with first task
        async def lock_holder():
            async with lock:
                await asyncio.sleep(0.3)

        lock_task = asyncio.create_task(lock_holder())
        await asyncio.sleep(0.05)  # Ensure lock is held

        # Create request that will disconnect while waiting for lock
        req_item = cast(
            QueueItem,
            {
                "req_id": "disconnect-req",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        # Simulate delayed disconnect (after initial check but before lock acquired)
        async def disconnect_checker(*args):
            """First check passes, second check (inside lock) fails."""
            if disconnect_tracker["value"]:
                return False  # Disconnected
            else:
                disconnect_tracker["value"] = True
                return True  # Still connected

        with patch(
            "api_utils.request_processor._check_client_connection",
            new_callable=AsyncMock,
            side_effect=disconnect_checker,
        ):
            await queue_manager.process_request(req_item)

        # Should detect disconnect and return 499
        assert req_item["result_future"].done()
        with pytest.raises(HTTPException) as exc:
            req_item["result_future"].result()
        assert exc.value.status_code == 499

        # Clear exception to prevent warning
        try:
            req_item["result_future"].exception()
        except Exception:
            pass

        await lock_task

    async def test_disconnect_during_streaming_response(self, real_server_state):
        """
        Test disconnect detection during streaming response generation.

        Simplified test: verify disconnect is detected and 499 error is set.
        """
        queue = real_server_state.request_queue
        lock = real_server_state.processing_lock
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.processing_lock = lock
        queue_manager.logger = MagicMock()

        # Mock task_done since we call process_request directly without queue.get()
        queue.task_done = MagicMock()

        req_item = cast(
            QueueItem,
            {
                "req_id": "streaming-req",
                "request_data": MagicMock(stream=True),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        # Simulate disconnect after initial connection check
        disconnect_calls = [False, True]  # First call passes, second fails

        async def check_disconnect(*args):
            if disconnect_calls:
                return not disconnect_calls.pop(0)  # Invert for disconnect detection
            return True

        req_item["http_request"].is_disconnected = AsyncMock(
            side_effect=check_disconnect
        )

        # Mock check connection to trigger disconnect path
        with patch(
            "api_utils.request_processor._check_client_connection",
            new_callable=AsyncMock,
            side_effect=[True, False],  # Connected then disconnected
        ):
            await queue_manager.process_request(req_item)

        # Verify disconnect error was set
        assert req_item["result_future"].done()
        with pytest.raises(HTTPException) as exc:
            req_item["result_future"].result()
        assert exc.value.status_code == 499

        # Clean up future exception
        try:
            req_item["result_future"].exception()
        except Exception:
            pass


@pytest.mark.integration
class TestClientDisconnectRaceConditions:
    """Tests for race conditions between disconnect detection and processing."""

    async def test_concurrent_disconnect_checks_no_race(self, real_server_state):
        """
        Test that concurrent disconnect checks don't race.

        Multiple requests checking disconnect status simultaneously.
        """
        queue = real_server_state.request_queue
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.logger = MagicMock()

        # Create 10 concurrent requests
        items = []
        for i in range(10):
            item = cast(
                QueueItem,
                {
                    "req_id": f"concurrent-{i}",
                    "http_request": MagicMock(),
                    "cancelled": False,
                    "result_future": asyncio.Future(),
                    "request_data": None,
                    "enqueue_time": 0.0,
                },
            )
            # Half disconnected, half connected
            item["http_request"].is_disconnected = AsyncMock(return_value=i % 2 == 0)
            items.append(item)
            await queue.put(item)

        # Check disconnects (concurrent operations)
        await queue_manager.check_queue_disconnects()

        # Verify correct items marked as cancelled
        for i in range(10):
            if i % 2 == 0:
                assert items[i]["cancelled"] is True
                assert items[i]["result_future"].done()
            else:
                assert items[i]["cancelled"] is False

    async def test_disconnect_after_future_already_set(self, real_server_state):
        """
        Test disconnect check when result_future is already done.

        Verifies no race condition when future is set by processing
        before disconnect check happens.
        """
        queue = real_server_state.request_queue
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.logger = MagicMock()

        item = cast(
            QueueItem,
            {
                "req_id": "already-done",
                "http_request": MagicMock(),
                "cancelled": False,
                "result_future": asyncio.Future(),
                "request_data": None,
                "enqueue_time": 0.0,
            },
        )

        # Set future BEFORE disconnect check
        item["result_future"].set_result(
            JSONResponse(content={"message": "Already completed"})
        )

        # Now try to mark as disconnected
        item["http_request"].is_disconnected = AsyncMock(return_value=True)

        await queue.put(item)
        await queue_manager.check_queue_disconnects()

        # Should still be marked cancelled, but future should have original result
        assert item["cancelled"] is True
        result = item["result_future"].result()
        assert isinstance(result, JSONResponse)
        import json

        assert json.loads(bytes(result.body).decode()) == {
            "message": "Already completed"
        }


@pytest.mark.integration
class TestClientDisconnectCleanup:
    """Tests for proper cleanup after client disconnect."""

    async def test_cleanup_called_even_on_disconnect(self, real_server_state):
        """
        Test that resources are released when client disconnects.

        Simplified test: verify lock is released and future has error.
        """
        queue = real_server_state.request_queue
        lock = real_server_state.processing_lock
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.processing_lock = lock
        queue_manager.logger = MagicMock()

        # Mock task_done since we call process_request directly without queue.get()
        queue.task_done = MagicMock()

        req_item = cast(
            QueueItem,
            {
                "req_id": "cleanup-test",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        # Mock check connection to trigger disconnect path
        with patch(
            "api_utils.request_processor._check_client_connection",
            new_callable=AsyncMock,
            side_effect=[True, False],  # Connected then disconnected
        ):
            await queue_manager.process_request(req_item)

        # Verify disconnect was handled
        assert req_item["result_future"].done()
        with pytest.raises(HTTPException) as exc:
            req_item["result_future"].result()
        assert exc.value.status_code == 499

        # Verify lock was released (cleanup successful)
        assert not lock.locked()

        # Clean up future exception
        try:
            req_item["result_future"].exception()
        except Exception:
            pass

    async def test_lock_released_on_disconnect(self, real_server_state):
        """
        Test that processing_lock is released when client disconnects.

        Critical for preventing deadlocks when clients disconnect.
        """
        lock = real_server_state.processing_lock
        queue = real_server_state.request_queue
        queue_manager = QueueManager()
        queue_manager.processing_lock = lock
        queue_manager.request_queue = queue
        queue_manager.logger = MagicMock()

        # Mock task_done since we call process_request directly without queue.get()
        queue.task_done = MagicMock()

        req_item = cast(
            QueueItem,
            {
                "req_id": "lock-release-test",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        # Simulate disconnect inside lock
        with patch(
            "api_utils.request_processor._check_client_connection",
            new_callable=AsyncMock,
            side_effect=[True, False],  # Disconnect inside lock
        ):
            await queue_manager.process_request(req_item)

        # Verify lock is released (can be acquired immediately)
        lock_acquired = lock.locked()
        assert not lock_acquired  # Lock should be released

        # Verify we can acquire it
        async with lock:
            assert lock.locked()
        assert not lock.locked()  # Released after context exit

        # Clean up future if it has exception
        if req_item["result_future"].done():
            try:
                req_item["result_future"].exception()
            except Exception:
                pass


@pytest.mark.integration
class TestClientDisconnectEdgeCases:
    """Tests for edge cases in disconnect detection."""

    async def test_disconnect_check_exception_handled(self, real_server_state):
        """
        Test that exceptions during disconnect check are handled gracefully.

        Network errors during is_disconnected() should not crash queue.
        """
        queue = real_server_state.request_queue
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.logger = MagicMock()

        # Create item with failing disconnect check
        item = cast(
            QueueItem,
            {
                "req_id": "error-check",
                "http_request": MagicMock(),
                "cancelled": False,
                "result_future": asyncio.Future(),
                "request_data": None,
                "enqueue_time": 0.0,
            },
        )
        item["http_request"].is_disconnected = AsyncMock(
            side_effect=Exception("Connection check failed")
        )

        await queue.put(item)

        # Should not raise, just log error
        await queue_manager.check_queue_disconnects()

        # Item should still be in queue
        assert queue.qsize() == 1

        # Error should be logged
        queue_manager.logger.error.assert_called()

    async def test_rapid_disconnect_reconnect_scenario(self, real_server_state):
        """
        Test rapid disconnect/reconnect scenario.

        Client disconnects then reconnects quickly - last state wins.
        """
        queue = real_server_state.request_queue
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.logger = MagicMock()

        disconnect_state = {"calls": 0}

        # Simulate alternating disconnect states
        async def alternating_disconnect(*args):
            disconnect_state["calls"] += 1
            # Odd calls = disconnected, even = connected
            return disconnect_state["calls"] % 2 == 1

        item = cast(
            QueueItem,
            {
                "req_id": "rapid-disconnect",
                "http_request": MagicMock(),
                "cancelled": False,
                "result_future": asyncio.Future(),
                "request_data": None,
                "enqueue_time": 0.0,
            },
        )
        item["http_request"].is_disconnected = AsyncMock(
            side_effect=alternating_disconnect
        )

        await queue.put(item)

        # First check: disconnected
        await queue_manager.check_queue_disconnects()
        assert item["cancelled"] is True

        # Put back and check again: connected (but already cancelled)
        await queue.put(item)
        await queue_manager.check_queue_disconnects()

        # Should remain cancelled (can't un-cancel)
        assert item["cancelled"] is True
