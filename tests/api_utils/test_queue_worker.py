"""
Tests for api_utils.queue_worker module.

Test Strategy:
- Unit tests: Test QueueManager methods individually
- Use REAL asyncio.Queue (not mocked) for queue behavior tests
- Use REAL asyncio.Lock for concurrency tests
- Mock only external boundaries: Browser/page (Playwright), network requests
- Use real helper function logic where possible
- Integration tests for FIFO ordering and disconnect during processing:
  See tests/integration/test_queue_fifo.py and test_client_disconnect_advanced.py

Coverage Target: 85%+
Mock Budget: <40 (down from 98)
"""

import asyncio
import time
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api_utils.context_types import QueueItem
from api_utils.queue_worker import QueueManager, queue_worker

# ==================== Test Classes ====================


class TestQueueManagerInitialization:
    """Tests for QueueManager initialization and globals setup."""

    @pytest.mark.asyncio
    async def test_initialize_globals_creates_new_objects_when_none(self):
        """Test that initialize_globals creates objects when server state is None."""
        queue_manager = QueueManager()

        mock_logger = MagicMock()

        with (
            patch("api_utils.server_state.state.request_queue", None),
            patch("api_utils.server_state.state.processing_lock", None),
            patch("api_utils.server_state.state.model_switching_lock", None),
            patch("api_utils.server_state.state.params_cache_lock", None),
            patch("api_utils.server_state.state.logger", mock_logger),
        ):
            queue_manager.initialize_globals()

            # Should create new instances
            assert queue_manager.request_queue is not None
            assert queue_manager.processing_lock is not None
            assert queue_manager.model_switching_lock is not None
            assert queue_manager.params_cache_lock is not None
            assert queue_manager.logger == mock_logger

    @pytest.mark.asyncio
    async def test_initialize_globals_uses_existing_objects(self):
        """Test that initialize_globals uses existing server state objects."""
        queue_manager = QueueManager()

        mock_queue = asyncio.Queue()
        mock_lock1 = asyncio.Lock()
        mock_lock2 = asyncio.Lock()
        mock_lock3 = asyncio.Lock()

        with (
            patch("api_utils.server_state.state.request_queue", mock_queue),
            patch("api_utils.server_state.state.processing_lock", mock_lock1),
            patch("api_utils.server_state.state.model_switching_lock", mock_lock2),
            patch("api_utils.server_state.state.params_cache_lock", mock_lock3),
        ):
            queue_manager.initialize_globals()

            # Should use existing instances
            assert queue_manager.request_queue == mock_queue
            assert queue_manager.processing_lock == mock_lock1
            assert queue_manager.model_switching_lock == mock_lock2
            assert queue_manager.params_cache_lock == mock_lock3


class TestStreamingDelay:
    """Tests for streaming request delay mechanism."""

    @pytest.mark.asyncio
    async def test_no_delay_for_non_streaming_request(self):
        """Non-streaming requests should not trigger delay."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        start_time = time.time()
        await queue_manager.handle_streaming_delay("req1", is_streaming_request=False)
        elapsed = time.time() - start_time

        assert elapsed < 0.1  # Should be immediate

    @pytest.mark.asyncio
    async def test_no_delay_when_last_request_not_streaming(self):
        """No delay when last request was not streaming."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()
        queue_manager.was_last_request_streaming = False

        start_time = time.time()
        await queue_manager.handle_streaming_delay("req2", is_streaming_request=True)
        elapsed = time.time() - start_time

        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_delay_for_sequential_streaming_requests(self):
        """Sequential streaming requests should have delay."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()
        queue_manager.was_last_request_streaming = True
        queue_manager.last_request_completion_time = time.time()

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await queue_manager.handle_streaming_delay(
                "req3", is_streaming_request=True
            )

            mock_sleep.assert_called_once()
            # Verify delay is between 0.5 and 1.0 seconds
            delay_arg = mock_sleep.call_args[0][0]
            assert 0.5 <= delay_arg <= 1.0


class TestQueueDisconnectDetection:
    """Tests for checking disconnected clients in queue."""

    @pytest.mark.asyncio
    async def test_check_queue_disconnects_marks_disconnected_requests(
        self, real_locks_mock_browser
    ):
        """Test that disconnected requests are marked as cancelled."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None

        # Create two items: one disconnected, one connected
        item1 = cast(
            QueueItem,
            {
                "req_id": "req1",
                "http_request": MagicMock(),
                "cancelled": False,
                "result_future": asyncio.Future(),
                "request_data": None,
                "enqueue_time": 0.0,
            },
        )
        item1["http_request"].is_disconnected = AsyncMock(return_value=True)

        item2 = cast(
            QueueItem,
            {
                "req_id": "req2",
                "http_request": MagicMock(),
                "cancelled": False,
                "result_future": asyncio.Future(),
                "request_data": None,
                "enqueue_time": 0.0,
            },
        )
        item2["http_request"].is_disconnected = AsyncMock(return_value=False)

        # Add to queue
        await queue_manager.request_queue.put(item1)
        await queue_manager.request_queue.put(item2)

        await queue_manager.check_queue_disconnects()

        # Verify item1 was cancelled
        assert item1["cancelled"] is True
        assert item1["result_future"].done()
        with pytest.raises(HTTPException) as exc:
            item1["result_future"].result()
        assert exc.value.status_code == 499

        # Verify item2 was not cancelled
        assert item2["cancelled"] is False
        assert not item2["result_future"].done()

    @pytest.mark.asyncio
    async def test_check_queue_disconnects_handles_exceptions(
        self, real_locks_mock_browser
    ):
        """Test that exceptions during disconnect check are handled gracefully."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None
        queue_manager.logger = MagicMock()

        item = cast(
            QueueItem,
            {
                "req_id": "req1",
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

        await queue_manager.request_queue.put(item)

        # Should not raise exception, just log error
        await queue_manager.check_queue_disconnects()

        # Item should still be in queue (re-queued after error)
        assert queue_manager.request_queue.qsize() == 1


class TestRequestProcessing:
    """Tests for core request processing logic."""

    @pytest.mark.asyncio
    async def test_process_request_skips_cancelled_requests(
        self, real_locks_mock_browser
    ):
        """Already cancelled requests should be skipped immediately."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None
        # Mock task_done since we're not using queue.get()
        queue_manager.request_queue.task_done = MagicMock()

        req_item = cast(
            QueueItem,
            {
                "req_id": "req1",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": True,  # Already cancelled
                "enqueue_time": 0.0,
            },
        )

        await queue_manager.process_request(req_item)

        # Should set 499 error in future
        assert req_item["result_future"].done()
        with pytest.raises(HTTPException) as exc:
            req_item["result_future"].result()
        assert exc.value.status_code == 499

    @pytest.mark.asyncio
    async def test_process_request_detects_early_disconnect(
        self, real_locks_mock_browser
    ):
        """Test client disconnect detection before acquiring lock."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None
        queue_manager.request_queue.task_done = MagicMock()  # Mock task_done
        queue_manager.processing_lock = real_locks_mock_browser.processing_lock

        req_item = cast(
            QueueItem,
            {
                "req_id": "req1",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        # Mock client as disconnected
        with patch(
            "api_utils.request_processor._check_client_connection",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await queue_manager.process_request(req_item)

        # Should return 499 error
        assert req_item["result_future"].done()
        with pytest.raises(HTTPException) as exc:
            req_item["result_future"].result()
        assert exc.value.status_code == 499

    @pytest.mark.asyncio
    async def test_process_request_fails_when_lock_missing(
        self, real_locks_mock_browser
    ):
        """Test failure when processing_lock is not initialized."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None
        queue_manager.request_queue.task_done = MagicMock()  # Mock task_done
        queue_manager.processing_lock = None  # Not initialized

        req_item = cast(
            QueueItem,
            {
                "req_id": "req1",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        with patch(
            "api_utils.request_processor._check_client_connection",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await queue_manager.process_request(req_item)

        # Should return 500 error
        assert req_item["result_future"].done()
        with pytest.raises(HTTPException) as exc:
            req_item["result_future"].result()
        assert exc.value.status_code == 500
        assert "Processing lock missing" in exc.value.detail

    @pytest.mark.asyncio
    async def test_process_request_successful_flow(self, real_locks_mock_browser):
        """Test successful request processing flow."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None
        queue_manager.request_queue.task_done = MagicMock()  # Mock task_done
        queue_manager.processing_lock = real_locks_mock_browser.processing_lock
        queue_manager.logger = MagicMock()

        req_item = cast(
            QueueItem,
            {
                "req_id": "req1",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )
        req_item["request_data"].stream = False

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch.object(
                queue_manager, "_execute_request_logic", new_callable=AsyncMock
            ) as mock_exec,
            patch.object(
                queue_manager, "_cleanup_after_processing", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            await queue_manager.process_request(req_item)

            # Verify processing flow
            mock_exec.assert_called_once()
            mock_cleanup.assert_called_once()
            assert queue_manager.was_last_request_streaming is False


class TestRecoveryMechanisms:
    """Tests for error recovery mechanisms (Tier 1, Tier 2, quota errors)."""

    @pytest.mark.asyncio
    async def test_tier1_recovery_page_refresh(self, real_locks_mock_browser):
        """Test Tier 1 recovery: Page refresh on first failure."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None
        queue_manager.request_queue.task_done = MagicMock()  # Mock task_done
        queue_manager.processing_lock = real_locks_mock_browser.processing_lock
        queue_manager.logger = MagicMock()

        req_item = cast(
            QueueItem,
            {
                "req_id": "req1",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch.object(
                queue_manager,
                "_execute_request_logic",
                new_callable=AsyncMock,
                side_effect=[Exception("First failure"), None],  # Fail then succeed
            ) as mock_exec,
            patch.object(
                queue_manager, "_refresh_page", new_callable=AsyncMock
            ) as mock_refresh,
            patch.object(
                queue_manager, "_cleanup_after_processing", new_callable=AsyncMock
            ),
        ):
            await queue_manager.process_request(req_item)

            # Should execute twice (initial + retry)
            assert mock_exec.call_count == 2
            # Should call refresh after first failure
            mock_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_tier2_recovery_profile_switch(self, real_locks_mock_browser):
        """Test Tier 2 recovery: Profile switch on second failure."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None
        queue_manager.request_queue.task_done = MagicMock()  # Mock task_done
        queue_manager.processing_lock = real_locks_mock_browser.processing_lock
        queue_manager.logger = MagicMock()

        req_item = cast(
            QueueItem,
            {
                "req_id": "req1",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch.object(
                queue_manager,
                "_execute_request_logic",
                new_callable=AsyncMock,
                side_effect=[
                    Exception("Fail 1"),
                    Exception("Fail 2"),
                    None,
                ],  # Fail twice then succeed
            ) as mock_exec,
            patch.object(
                queue_manager, "_refresh_page", new_callable=AsyncMock
            ) as mock_refresh,
            patch.object(
                queue_manager, "_switch_auth_profile", new_callable=AsyncMock
            ) as mock_switch,
            patch.object(
                queue_manager, "_cleanup_after_processing", new_callable=AsyncMock
            ),
        ):
            await queue_manager.process_request(req_item)

            # Should execute 3 times
            assert mock_exec.call_count == 3
            # Tier 1: Refresh after first failure
            mock_refresh.assert_called_once()
            # Tier 2: Profile switch after second failure
            mock_switch.assert_called_once()

    @pytest.mark.asyncio
    async def test_quota_error_immediate_profile_switch(self, real_locks_mock_browser):
        """Test immediate profile switch on quota error (429)."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None
        queue_manager.request_queue.task_done = MagicMock()  # Mock task_done
        queue_manager.processing_lock = real_locks_mock_browser.processing_lock
        queue_manager.logger = MagicMock()

        req_item = cast(
            QueueItem,
            {
                "req_id": "req1",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch.object(
                queue_manager,
                "_execute_request_logic",
                new_callable=AsyncMock,
                side_effect=[
                    Exception("429 Too Many Requests"),
                    None,
                ],  # Quota error then succeed
            ) as mock_exec,
            patch.object(
                queue_manager, "_refresh_page", new_callable=AsyncMock
            ) as mock_refresh,
            patch.object(
                queue_manager, "_switch_auth_profile", new_callable=AsyncMock
            ) as mock_switch,
            patch.object(
                queue_manager, "_cleanup_after_processing", new_callable=AsyncMock
            ),
        ):
            await queue_manager.process_request(req_item)

            # Should call profile switch immediately, skipping refresh
            assert mock_exec.call_count == 2
            mock_switch.assert_called_once()
            mock_refresh.assert_not_called()  # Skip refresh for quota errors

    @pytest.mark.asyncio
    async def test_recovery_exhausted_raises_exception(self, real_locks_mock_browser):
        """Test that all retries exhausted raises the last exception."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        queue_manager.processing_lock = real_locks_mock_browser.processing_lock
        queue_manager.logger = MagicMock()

        req_item = cast(
            QueueItem,
            {
                "req_id": "req1",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "result_future": asyncio.Future(),
                "cancelled": False,
                "enqueue_time": 0.0,
            },
        )

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch.object(
                queue_manager,
                "_execute_request_logic",
                new_callable=AsyncMock,
                side_effect=[
                    Exception("Fail 1"),
                    Exception("Fail 2"),
                    Exception("Fail 3"),
                ],  # All attempts fail
            ) as mock_exec,
            patch.object(
                queue_manager, "_refresh_page", new_callable=AsyncMock
            ) as mock_refresh,
            patch.object(
                queue_manager, "_switch_auth_profile", new_callable=AsyncMock
            ) as mock_switch,
            patch.object(
                queue_manager, "_cleanup_after_processing", new_callable=AsyncMock
            ),
        ):
            with pytest.raises(Exception) as exc:
                await queue_manager.process_request(req_item)

            assert "Fail 3" in str(exc.value)
            assert mock_exec.call_count == 3
            mock_refresh.assert_called_once()  # Tier 1
            mock_switch.assert_called_once()  # Tier 2


class TestExecuteRequestLogic:
    """Tests for _execute_request_logic method."""

    @pytest.mark.asyncio
    async def test_execute_request_streaming(self):
        """Test execute logic for streaming request."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        req_item = {
            "req_id": "req1",
            "request_data": MagicMock(),
            "http_request": MagicMock(),
            "result_future": asyncio.Future(),
        }

        mock_event = asyncio.Event()
        mock_btn_loc = MagicMock()
        mock_checker = MagicMock()

        with (
            patch(
                "api_utils._process_request_refactored",
                new_callable=AsyncMock,
                return_value=(mock_event, mock_btn_loc, mock_checker),
            ),
            patch.object(
                queue_manager, "_monitor_completion", new_callable=AsyncMock
            ) as mock_monitor,
        ):
            await queue_manager._execute_request_logic(
                req_item["req_id"],
                req_item["request_data"],
                req_item["http_request"],
                req_item["result_future"],
            )

            # Verify stored context
            assert queue_manager.current_completion_event == mock_event
            assert queue_manager.current_submit_btn_loc == mock_btn_loc

            # Verify monitor was called with streaming=True
            mock_monitor.assert_called_once()
            args = mock_monitor.call_args[0]
            assert args[6] is True  # current_request_was_streaming

    @pytest.mark.asyncio
    async def test_execute_request_non_streaming(self):
        """Test execute logic for non-streaming request."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        req_item = {
            "req_id": "req1",
            "request_data": MagicMock(),
            "http_request": MagicMock(),
            "result_future": asyncio.Future(),
        }

        with (
            patch(
                "api_utils._process_request_refactored",
                new_callable=AsyncMock,
                return_value=None,  # Non-streaming returns None
            ),
            patch.object(
                queue_manager, "_monitor_completion", new_callable=AsyncMock
            ) as mock_monitor,
        ):
            await queue_manager._execute_request_logic(
                req_item["req_id"],
                req_item["request_data"],
                req_item["http_request"],
                req_item["result_future"],
            )

            # Verify no streaming context stored
            assert queue_manager.current_completion_event is None

            # Verify monitor was called with streaming=False
            mock_monitor.assert_called_once()
            args = mock_monitor.call_args[0]
            assert args[6] is False

    @pytest.mark.asyncio
    async def test_execute_request_error_sets_future(self):
        """Test that errors during execution set the result_future."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        req_item = {
            "req_id": "req1",
            "request_data": MagicMock(),
            "http_request": MagicMock(),
            "result_future": asyncio.Future(),
        }

        with patch(
            "api_utils._process_request_refactored",
            new_callable=AsyncMock,
            side_effect=Exception("Processing failed"),
        ):
            # Should raise exception for retry mechanism
            with pytest.raises(Exception) as exc:
                await queue_manager._execute_request_logic(
                    req_item["req_id"],
                    req_item["request_data"],
                    req_item["http_request"],
                    req_item["result_future"],
                )

            assert "Processing failed" in str(exc.value)

            # Should also set future with HTTP exception
            assert req_item["result_future"].done()
            with pytest.raises(HTTPException) as http_exc:
                req_item["result_future"].result()
            assert http_exc.value.status_code == 500


class TestMonitorCompletion:
    """Tests for _monitor_completion method."""

    @pytest.mark.asyncio
    async def test_monitor_completion_streaming_success(self):
        """Test monitoring streaming request completion."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        req_id = "req1"
        http_request = MagicMock()
        result_future = asyncio.Future()
        completion_event = asyncio.Event()
        stream_state = {"has_content": True}

        # Set event immediately to simulate completion
        completion_event.set()

        with patch(
            "api_utils.client_connection.enhanced_disconnect_monitor",
            new_callable=AsyncMock,
            return_value=False,  # No disconnect
        ) as mock_monitor:
            await queue_manager._monitor_completion(
                req_id,
                http_request,
                result_future,
                completion_event,
                None,
                None,
                True,  # is_streaming
                stream_state,
            )

            # Should call disconnect monitor
            mock_monitor.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_completion_timeout(self):
        """Test timeout during completion monitoring."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        req_id = "req1"
        http_request = MagicMock()
        result_future = asyncio.Future()
        completion_event = asyncio.Event()  # Never set (timeout)

        with (
            patch(
                "api_utils.client_connection.enhanced_disconnect_monitor",
                new_callable=AsyncMock,
            ),
            patch(
                "asyncio.wait_for",
                new_callable=AsyncMock,
                side_effect=asyncio.TimeoutError,
            ),
        ):
            await queue_manager._monitor_completion(
                req_id,
                http_request,
                result_future,
                completion_event,
                None,
                None,
                True,
            )

            # Should set 504 timeout error
            assert result_future.done()
            with pytest.raises(HTTPException) as exc:
                result_future.result()
            assert exc.value.status_code == 504

    @pytest.mark.asyncio
    async def test_monitor_completion_empty_response_raises(self):
        """Test that empty response detection raises error."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        req_id = "req1"
        http_request = MagicMock()
        result_future = asyncio.Future()
        completion_event = asyncio.Event()
        stream_state = {"has_content": False}  # Empty response

        completion_event.set()

        with patch(
            "api_utils.client_connection.enhanced_disconnect_monitor",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(RuntimeError) as exc:
                await queue_manager._monitor_completion(
                    req_id,
                    http_request,
                    result_future,
                    completion_event,
                    None,
                    None,
                    True,
                    stream_state,
                )

            assert "Empty response" in str(exc.value) or "空响应" in str(exc.value)


class TestCleanup:
    """Tests for cleanup methods."""

    @pytest.mark.asyncio
    async def test_cleanup_after_processing(self, mock_playwright_stack):
        """Test cleanup after request processing."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()
        queue_manager.current_submit_btn_loc = MagicMock()
        queue_manager.current_client_disco_checker = MagicMock()

        _, _, _, page = mock_playwright_stack
        req_id = "req1"

        mock_controller = MagicMock()
        mock_controller.clear_chat_history = AsyncMock()

        with (
            patch("api_utils.clear_stream_queue", new_callable=AsyncMock) as mock_clear,
            patch("server.page_instance", page),
            patch("server.is_page_ready", True),
            patch(
                "browser_utils.page_controller.PageController",
                return_value=mock_controller,
            ),
        ):
            await queue_manager._cleanup_after_processing(req_id)

            # Verify cleanup actions
            mock_clear.assert_called_once()
            mock_controller.clear_chat_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_handles_exceptions(self):
        """Test that cleanup handles exceptions gracefully."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        req_id = "req1"

        with patch(
            "api_utils.clear_stream_queue",
            new_callable=AsyncMock,
            side_effect=Exception("Cleanup failed"),
        ):
            # Should not raise exception, just log error
            await queue_manager._cleanup_after_processing(req_id)

            queue_manager.logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_handle_post_stream_button(self, mock_playwright_stack):
        """Test handling post-stream button."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        _, _, _, page = mock_playwright_stack
        req_id = "req1"
        submit_btn_loc = MagicMock()
        checker = MagicMock()
        event = asyncio.Event()

        mock_controller = MagicMock()
        mock_controller.ensure_generation_stopped = AsyncMock()

        with (
            patch("server.page_instance", page),
            patch(
                "browser_utils.page_controller.PageController",
                return_value=mock_controller,
            ),
        ):
            await queue_manager._handle_post_stream_button(
                req_id, submit_btn_loc, checker, event
            )

            mock_controller.ensure_generation_stopped.assert_called_once_with(checker)

    @pytest.mark.asyncio
    async def test_handle_post_stream_button_no_page(self):
        """Test handling when page is None."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        with patch("server.page_instance", None):
            # Should log warning and return without error
            await queue_manager._handle_post_stream_button(
                "req1", MagicMock(), MagicMock(), asyncio.Event()
            )

            queue_manager.logger.warning.assert_called()


class TestRefreshAndProfileSwitch:
    """Tests for page refresh and profile switching."""

    @pytest.mark.asyncio
    async def test_refresh_page(self, mock_playwright_stack):
        """Test page refresh functionality."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        _, _, _, page = mock_playwright_stack

        with patch("api_utils.server_state.state.page_instance", page):
            await queue_manager._refresh_page("req1")

            page.reload.assert_called_once()
            page.wait_for_selector.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_page_no_instance_raises(self):
        """Test that refresh raises error when page is None."""
        queue_manager = QueueManager()
        queue_manager.logger = MagicMock()

        with patch("server.page_instance", None):
            with pytest.raises(RuntimeError):
                await queue_manager._refresh_page("req1")


class TestQueueWorkerMainLoop:
    """Tests for queue_worker main loop function."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_queue_worker_initializes_and_runs(self):
        """Test that queue_worker initializes manager and starts processing."""
        with patch("api_utils.queue_worker.QueueManager") as MockManager:
            mock_instance = MockManager.return_value
            mock_instance.logger = MagicMock()

            # Mock queue for diagnostics
            mock_queue = MagicMock()
            mock_queue.qsize.return_value = 0
            mock_instance.request_queue = mock_queue

            # Run once then cancel
            mock_instance.check_queue_disconnects = AsyncMock()
            mock_instance.get_next_request = AsyncMock(
                side_effect=asyncio.CancelledError
            )

            try:
                await queue_worker()
            except asyncio.CancelledError:
                pass

            # Verify initialization
            mock_instance.initialize_globals.assert_called_once()
            mock_instance.check_queue_disconnects.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_queue_worker_handles_exceptions(self):
        """Test exception handling in main loop."""
        with patch("api_utils.queue_worker.QueueManager") as MockManager:
            mock_instance = MockManager.return_value
            mock_instance.logger = MagicMock()

            mock_queue = MagicMock()
            mock_queue.qsize.return_value = 0
            mock_instance.request_queue = mock_queue

            # Raise exception then cancel
            mock_instance.check_queue_disconnects = AsyncMock(
                side_effect=[Exception("Loop error"), asyncio.CancelledError]
            )

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                try:
                    await queue_worker()
                except asyncio.CancelledError:
                    pass

                # Should log error and sleep before retry
                mock_instance.logger.error.assert_called()
                mock_sleep.assert_called()


class TestGetNextRequest:
    """Tests for get_next_request method."""

    @pytest.mark.asyncio
    async def test_get_next_request_timeout_returns_none(self, real_locks_mock_browser):
        """Test that timeout returns None."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue

        with patch(
            "asyncio.wait_for",
            new_callable=AsyncMock,
            side_effect=asyncio.TimeoutError,
        ):
            result = await queue_manager.get_next_request()
            assert result is None

    @pytest.mark.asyncio
    async def test_get_next_request_success(self, real_locks_mock_browser):
        """Test successful request retrieval."""
        queue_manager = QueueManager()
        queue_manager.request_queue = real_locks_mock_browser.request_queue
        assert queue_manager.request_queue is not None

        item = cast(
            QueueItem,
            {
                "req_id": "req1",
                "request_data": MagicMock(),
                "http_request": MagicMock(),
                "cancelled": False,
                "result_future": asyncio.Future(),
                "enqueue_time": 0.0,
            },
        )
        await queue_manager.request_queue.put(item)

        result = await queue_manager.get_next_request()
        assert result == item
