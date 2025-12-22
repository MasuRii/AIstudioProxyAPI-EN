"""
Integration tests for queue FIFO (First-In-First-Out) ordering.

These tests use REAL asyncio.Queue from server_state to verify actual queue
behavior, ensuring requests are processed in the correct order.

Test Strategy:
- Use real_server_state fixture (real asyncio.Queue, real asyncio.Lock)
- Verify FIFO ordering is maintained
- Test concurrent request submission
- Verify queue processing order matches submission order

Coverage Target: Queue processing order integrity
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# Test stub for QueueManager used in these tests
class QueueManager:
    """Functional stub class for queue management in tests."""

    request_queue: Any = None
    processing_lock: Any = None
    logger: Any = None

    async def check_queue_disconnects(self) -> Any:
        """Logic for checking disconnects in the queue."""
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
                            if self.logger:
                                self.logger.error(
                                    f"[{item_req_id}] Error in disconnect check: {e}"
                                )
                items_to_requeue.append(item)
            except asyncio.QueueEmpty:
                break
        for item in items_to_requeue:
            await self.request_queue.put(item)


@pytest.mark.integration
class TestQueueFIFOOrdering:
    """Integration tests for queue FIFO ordering with real asyncio.Queue."""

    async def test_queue_processes_requests_in_fifo_order(self, real_server_state):
        """
        Test that queue processes requests in submission order (FIFO).

        Uses REAL asyncio.Queue to verify actual ordering behavior.
        """
        queue = real_server_state.request_queue
        processing_order = []

        # Create 5 requests
        requests = []
        for i in range(5):
            item = {
                "req_id": f"req-{i}",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
            }
            requests.append(item)
            await queue.put(item)

        # Process requests and track order
        while not queue.empty():
            item = await queue.get()
            processing_order.append(item["req_id"])
            queue.task_done()

        # Verify FIFO ordering
        expected_order = [f"req-{i}" for i in range(5)]
        assert processing_order == expected_order

    async def test_concurrent_submission_maintains_order(self, real_server_state):
        """
        Test that concurrent request submissions maintain submission order.

        Verifies queue.put() is thread-safe and maintains order.
        """
        queue = real_server_state.request_queue
        submission_log = []

        async def submit_request(req_id: str):
            """Submit a request and log submission."""
            submission_log.append(req_id)
            item = {
                "req_id": req_id,
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
            }
            await queue.put(item)
            # Small delay to simulate real submission timing
            await asyncio.sleep(0.01)

        # Submit 10 requests concurrently
        tasks = [asyncio.create_task(submit_request(f"req-{i}")) for i in range(10)]
        await asyncio.gather(*tasks)

        # Process and verify order matches submission
        processing_order = []
        while not queue.empty():
            item = await queue.get()
            processing_order.append(item["req_id"])

        # Processing order should match submission order
        assert processing_order == submission_log

    async def test_queue_with_mixed_priorities_still_fifo(self, real_server_state):
        """
        Test that even with different request types, FIFO is maintained.

        Different models, streaming vs non-streaming - all should be FIFO.
        """
        queue = real_server_state.request_queue

        # Create diverse request types
        requests = [
            {
                "req_id": "req-0-streaming",
                "request_data": MagicMock(stream=True, model="gemini-1.5-pro"),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
            },
            {
                "req_id": "req-1-non-streaming",
                "request_data": MagicMock(stream=False, model="gemini-1.5-pro"),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
            },
            {
                "req_id": "req-2-flash",
                "request_data": MagicMock(stream=True, model="gemini-1.5-flash"),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
            },
            {
                "req_id": "req-3-pro-large",
                "request_data": MagicMock(stream=False, model="gemini-1.5-pro"),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
            },
        ]

        # Add all requests
        for req in requests:
            await queue.put(req)

        # Process and verify order
        processing_order = []
        while not queue.empty():
            item = await queue.get()
            processing_order.append(item["req_id"])

        expected_order = [r["req_id"] for r in requests]
        assert processing_order == expected_order


@pytest.mark.integration
class TestQueueWithDisconnects:
    """Integration tests for queue behavior when clients disconnect."""

    async def test_cancelled_requests_maintain_queue_order(self, real_server_state):
        """
        Test that cancelled requests don't disrupt queue ordering.

        Cancelled items should be skipped but not affect FIFO order.
        """
        queue = real_server_state.request_queue
        queue_manager = QueueManager()
        queue_manager.request_queue = queue

        # Create 5 requests, mark 2nd and 4th as cancelled
        requests = []
        for i in range(5):
            item = {
                "req_id": f"req-{i}",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": i in [1, 3],  # Cancel req-1 and req-3
            }
            requests.append(item)
            await queue.put(item)

        # Process queue
        processed = []
        cancelled = []

        while not queue.empty():
            item = await queue.get()
            if item["cancelled"]:
                cancelled.append(item["req_id"])
            else:
                processed.append(item["req_id"])
            queue.task_done()

        # Verify cancelled items were detected
        assert cancelled == ["req-1", "req-3"]

        # Verify non-cancelled items processed in order
        assert processed == ["req-0", "req-2", "req-4"]

    async def test_check_queue_disconnects_preserves_order(self, real_server_state):
        """
        Test that check_queue_disconnects maintains FIFO order.

        When checking disconnects, items should be re-queued in same order.
        """
        queue = real_server_state.request_queue
        queue_manager = QueueManager()
        queue_manager.request_queue = queue
        queue_manager.logger = MagicMock()

        # Create 3 items, 2nd is disconnected
        item1 = {
            "req_id": "req-0",
            "http_request": MagicMock(),
            "cancelled": False,
            "result_future": asyncio.Future(),
        }
        item1["http_request"].is_disconnected = AsyncMock(return_value=False)

        item2 = {
            "req_id": "req-1",
            "http_request": MagicMock(),
            "cancelled": False,
            "result_future": asyncio.Future(),
        }
        item2["http_request"].is_disconnected = AsyncMock(return_value=True)

        item3 = {
            "req_id": "req-2",
            "http_request": MagicMock(),
            "cancelled": False,
            "result_future": asyncio.Future(),
        }
        item3["http_request"].is_disconnected = AsyncMock(return_value=False)

        # Add to queue
        await queue.put(item1)
        await queue.put(item2)
        await queue.put(item3)

        # Check disconnects
        await queue_manager.check_queue_disconnects()

        # Verify order maintained (disconnected item should be cancelled)
        assert item2["cancelled"] is True

        # Verify queue still has items in correct order
        order = []
        while not queue.empty():
            item = await queue.get()
            order.append(item["req_id"])

        assert order == ["req-0", "req-1", "req-2"]


@pytest.mark.integration
class TestQueuePerformance:
    """Performance tests for queue operations."""

    async def test_large_queue_maintains_fifo(self, real_server_state):
        """
        Test FIFO ordering with large queue (100 items).

        Verifies performance doesn't affect correctness.
        """
        queue = real_server_state.request_queue

        # Add 100 requests
        for i in range(100):
            item = {
                "req_id": f"req-{i:03d}",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
            }
            await queue.put(item)

        # Process all
        processing_order = []
        while not queue.empty():
            item = await queue.get()
            processing_order.append(item["req_id"])
            queue.task_done()

        # Verify all 100 in correct order
        expected_order = [f"req-{i:03d}" for i in range(100)]
        assert processing_order == expected_order

    async def test_queue_performance_with_concurrent_access(self, real_server_state):
        """
        Test queue maintains FIFO under concurrent access.

        Multiple tasks submitting and processing simultaneously.
        """
        queue = real_server_state.request_queue
        submitted = []
        processed = []
        submit_lock = asyncio.Lock()
        process_lock = asyncio.Lock()

        async def submitter(start_id: int, count: int):
            """Submit requests concurrently."""
            for i in range(count):
                req_id = f"req-{start_id + i}"
                async with submit_lock:
                    submitted.append(req_id)
                item = {
                    "req_id": req_id,
                    "request_data": MagicMock(),
                    "http_request": MagicMock(),
                    "result_future": asyncio.Future(),
                    "cancelled": False,
                }
                await queue.put(item)

        async def processor():
            """Process requests concurrently."""
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                    async with process_lock:
                        processed.append(item["req_id"])
                    queue.task_done()
                except asyncio.TimeoutError:
                    break

        # Start 3 submitters and 2 processors concurrently
        submitters = [
            asyncio.create_task(submitter(0, 10)),
            asyncio.create_task(submitter(10, 10)),
            asyncio.create_task(submitter(20, 10)),
        ]

        # Wait for all submissions
        await asyncio.gather(*submitters)

        # Start processors
        processors = [
            asyncio.create_task(processor()),
            asyncio.create_task(processor()),
        ]

        # Wait for all processing
        await asyncio.gather(*processors)

        # Verify all 30 items processed
        assert len(processed) == 30

        # Verify order matches submission
        assert processed == submitted


@pytest.mark.integration
class TestQueueRecovery:
    """Tests for queue recovery after errors."""

    async def test_queue_continues_after_processing_error(self, real_server_state):
        """
        Test that queue processing continues after error in one request.

        Error in req-1 should not affect req-2 processing order.
        """
        queue = real_server_state.request_queue
        processing_log = []

        # Add 3 requests
        items = []
        for i in range(3):
            item = {
                "req_id": f"req-{i}",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
            }
            items.append(item)
            await queue.put(item)

        # Process with error on req-1
        while not queue.empty():
            item = await queue.get()
            processing_log.append(item["req_id"])

            if item["req_id"] == "req-1":
                # Simulate processing error
                item["result_future"].set_exception(
                    Exception("Processing failed for req-1")
                )
            else:
                # Normal processing
                item["result_future"].set_result("Success")

            queue.task_done()

        # Verify all 3 processed in order despite error
        assert processing_log == ["req-0", "req-1", "req-2"]

        # Retrieve exceptions from futures to prevent warnings
        for item in items:
            if item["result_future"].done():
                try:
                    item["result_future"].exception()
                except Exception:
                    pass
