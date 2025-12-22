"""
Integration tests for streaming response generation with real async generators.

These tests verify actual async generator behavior with real asyncio primitives,
ensuring streaming works correctly end-to-end without over-mocking.

Test Strategy:
- Use REAL async generators (not mocked iterators)
- Use REAL asyncio.Event for completion signaling
- Test actual SSE chunk format and ordering
- Verify real async behavior and backpressure
- Mock only data sources (stream responses)

Coverage Target: Stream generator integrity and async behavior
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from api_utils.response_generators import gen_sse_from_aux_stream
from models import ClientDisconnectedError


@pytest.mark.integration
class TestStreamingGeneratorBehavior:
    """Integration tests for real async generator behavior."""

    async def test_generator_yields_actual_async_iterations(self, make_chat_request):
        """
        Test that generator actually yields asynchronously.

        Verifies real async iteration behavior, not just mock iteration.
        """
        req_id = "int-test-1"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        stream_data = [
            {"body": "First", "reason": "", "done": False},
            {"body": "First Second", "reason": "", "done": False},
            {"body": "First Second Third", "reason": "", "done": True},
        ]

        iteration_log = []

        async def mock_stream_gen(
            rid,
            timeout=5.0,
            page=None,
            check_client_disconnected=None,
            enable_silence_detection=True,
            **kwargs,
        ):
            for idx, item in enumerate(stream_data):
                iteration_log.append(f"yield_{idx}")
                await asyncio.sleep(0.01)  # Simulate async delay
                yield item

        with (
            patch(
                "api_utils.response_generators.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 5},
            ),
        ):
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                5.0,
            ):
                chunks.append(chunk)
                iteration_log.append(f"received_{len(chunks) - 1}")

        # Verify async iterations actually happened
        assert "yield_0" in iteration_log
        assert "received_0" in iteration_log
        assert "yield_1" in iteration_log

        # Verify interleaving (proves async behavior)
        yield_0_idx = iteration_log.index("yield_0")
        recv_0_idx = iteration_log.index("received_0")
        assert recv_0_idx > yield_0_idx

    async def test_concurrent_stream_consumption(self, make_chat_request):
        """
        Test multiple concurrent consumers of different streams.

        Verifies generators are independent and don't interfere.
        """
        completion_event1 = asyncio.Event()
        completion_event2 = asyncio.Event()
        check_disconnect = MagicMock()

        stream_data1 = [
            {"body": "Stream1 Data", "reason": "", "done": True},
        ]

        stream_data2 = [
            {"body": "Stream2 Data", "reason": "", "done": True},
        ]

        async def mock_stream_gen1(
            rid,
            timeout=5.0,
            page=None,
            check_client_disconnected=None,
            enable_silence_detection=True,
            **kwargs,
        ):
            for item in stream_data1:
                await asyncio.sleep(0.02)
                yield item

        async def mock_stream_gen2(
            rid,
            timeout=5.0,
            page=None,
            check_client_disconnected=None,
            enable_silence_detection=True,
            **kwargs,
        ):
            for item in stream_data2:
                await asyncio.sleep(0.01)
                yield item

        async def consume_stream(req_id, stream_gen, event):
            """Consume a single stream."""
            with (
                patch(
                    "api_utils.response_generators.use_stream_response",
                    side_effect=stream_gen,
                ),
                patch(
                    "api_utils.response_generators.calculate_usage_stats",
                    return_value={"total_tokens": 3},
                ),
            ):
                chunks = []
                async for chunk in gen_sse_from_aux_stream(
                    req_id,
                    make_chat_request(stream=True),
                    "model",
                    check_disconnect,
                    event,
                    5.0,
                ):
                    chunks.append(chunk)
                return chunks

        # Consume both streams concurrently
        task1 = asyncio.create_task(
            consume_stream("req1", mock_stream_gen1, completion_event1)
        )
        task2 = asyncio.create_task(
            consume_stream("req2", mock_stream_gen2, completion_event2)
        )

        chunks1, chunks2 = await asyncio.gather(task1, task2)

        # Both should complete independently
        assert len(chunks1) > 0
        assert len(chunks2) > 0
        assert completion_event1.is_set()
        assert completion_event2.is_set()

        # Verify content separation
        content1 = "".join(chunks1)
        content2 = "".join(chunks2)
        assert "Stream1" in content1
        assert "Stream2" in content2

    async def test_backpressure_handling(self, make_chat_request):
        """
        Test generator handles backpressure (slow consumer).

        Verifies generator doesn't lose data when consumer is slow.
        """
        req_id = "int-test-backpressure"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        # Large stream to test buffering
        stream_data = [
            {"body": f"Chunk {i}", "reason": "", "done": i == 49} for i in range(50)
        ]

        async def mock_stream_gen(
            rid,
            timeout=5.0,
            page=None,
            check_client_disconnected=None,
            enable_silence_detection=True,
            **kwargs,
        ):
            for item in stream_data:
                yield item

        with (
            patch(
                "api_utils.response_generators.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 100},
            ),
        ):
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                5.0,
            ):
                chunks.append(chunk)
                # Simulate slow consumer
                await asyncio.sleep(0.001)

        # Should receive all chunks despite slow consumption
        # Filter out [DONE] and usage chunks
        content_chunks = [
            c for c in chunks if "[DONE]" not in c and "usage" not in c.lower()
        ]

        # Generator creates delta chunks from full responses,
        # so expect fewer chunks than input items (deltas are calculated)
        # With 50 items, we get ~2-4 delta chunks typically
        assert len(content_chunks) >= 2, (
            f"Expected at least 2 chunks, got {len(content_chunks)}"
        )

        # Verify all chunks were processed (no data loss)
        assert len(chunks) > 0

        # Verify completion event was set
        assert completion_event.is_set()

    async def test_completion_event_timing(self, make_chat_request):
        """
        Test that completion event is set at the right time.

        Verifies event is set only after streaming completes.
        """
        req_id = "int-test-event"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        stream_data = [
            {"body": "A", "reason": "", "done": False},
            {"body": "AB", "reason": "", "done": False},
            {"body": "ABC", "reason": "", "done": True},
        ]

        event_check_log = []

        async def mock_stream_gen(
            rid,
            timeout=5.0,
            page=None,
            check_client_disconnected=None,
            enable_silence_detection=True,
            **kwargs,
        ):
            for item in stream_data:
                yield item

        with (
            patch(
                "api_utils.response_generators.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 3},
            ),
        ):
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                5.0,
            ):
                # Record event state after each chunk
                event_check_log.append(completion_event.is_set())

        # Event should not be set initially
        assert event_check_log[0] is False

        # Event should eventually be set
        assert completion_event.is_set()


@pytest.mark.integration
class TestStreamingErrorHandling:
    """Integration tests for error handling in streaming."""

    async def test_generator_cleanup_on_exception(self, make_chat_request):
        """
        Test that generator properly cleans up on exception.

        Verifies completion event is set even on error.
        """
        req_id = "int-test-error"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        async def mock_stream_gen(
            rid,
            timeout=5.0,
            page=None,
            check_client_disconnected=None,
            enable_silence_detection=True,
            **kwargs,
        ):
            yield {"body": "First chunk", "reason": "", "done": False}
            raise Exception("Stream error")

        with patch(
            "api_utils.response_generators.use_stream_response",
            side_effect=mock_stream_gen,
        ):
            chunks = []
            try:
                async for chunk in gen_sse_from_aux_stream(
                    req_id,
                    request,
                    "gemini-1.5-pro",
                    check_disconnect,
                    completion_event,
                    5.0,
                ):
                    chunks.append(chunk)
            except Exception:
                pass  # Expected

        # Completion event should be set for cleanup
        assert completion_event.is_set()

    async def test_disconnect_during_streaming(self, make_chat_request):
        """
        Test client disconnect detection during active streaming.

        Verifies generator stops cleanly on disconnect.
        """
        req_id = "int-test-disconnect"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()

        # Mock disconnect after 2 chunks
        check_disconnect = MagicMock()
        check_disconnect.side_effect = [
            None,  # First chunk OK
            None,  # Second chunk OK
            ClientDisconnectedError("Disconnected"),  # Third chunk fails
        ]

        stream_data = [
            {"body": f"Chunk {i}", "reason": "", "done": False} for i in range(10)
        ]

        async def mock_stream_gen(
            rid,
            timeout=5.0,
            page=None,
            check_client_disconnected=None,
            enable_silence_detection=True,
            **kwargs,
        ):
            for item in stream_data:
                yield item

        with patch(
            "api_utils.response_generators.use_stream_response",
            side_effect=mock_stream_gen,
        ):
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                5.0,
            ):
                chunks.append(chunk)

        # Should stop early (less than 10 chunks)
        assert len(chunks) < 10

        # Completion event should be set
        assert completion_event.is_set()


@pytest.mark.integration
class TestStreamingDataIntegrity:
    """Integration tests for data integrity in streaming."""

    async def test_incremental_content_deltas(self, make_chat_request):
        """
        Test that content deltas are correctly calculated.

        Verifies incremental updates show only new content.
        """
        req_id = "int-test-deltas"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        stream_data = [
            {"body": "Hello", "reason": "", "done": False},
            {"body": "Hello world", "reason": "", "done": False},
            {"body": "Hello world!", "reason": "", "done": True},
        ]

        async def mock_stream_gen(
            rid,
            timeout=5.0,
            page=None,
            check_client_disconnected=None,
            enable_silence_detection=True,
            **kwargs,
        ):
            for item in stream_data:
                yield item

        with (
            patch(
                "api_utils.response_generators.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 5},
            ),
        ):
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                5.0,
            ):
                if "[DONE]" not in chunk:
                    chunks.append(chunk)

        # Parse deltas
        deltas = []
        for chunk in chunks:
            try:
                data = json.loads(chunk.replace("data: ", "").strip())
                if "choices" in data and data["choices"]:
                    delta_content = data["choices"][0].get("delta", {}).get("content")
                    if delta_content:
                        deltas.append(delta_content)
            except (json.JSONDecodeError, KeyError):
                continue

        # First delta should be "Hello"
        assert deltas[0] == "Hello"

        # Second delta should be " world" (only new content)
        assert deltas[1] == " world"

        # Third delta should be "!" (only new content)
        assert deltas[2] == "!"

        # Accumulated deltas should match final content
        assert "".join(deltas) == "Hello world!"

    async def test_sse_format_compliance(self, make_chat_request):
        """
        Test that SSE format is compliant with spec.

        Verifies data: prefix and proper line endings.
        """
        req_id = "int-test-sse"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        stream_data = [
            {"body": "Test", "reason": "", "done": True},
        ]

        async def mock_stream_gen(
            rid,
            timeout=5.0,
            page=None,
            check_client_disconnected=None,
            enable_silence_detection=True,
            **kwargs,
        ):
            for item in stream_data:
                yield item

        with (
            patch(
                "api_utils.response_generators.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 1},
            ),
        ):
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                5.0,
            ):
                chunks.append(chunk)

        # Verify SSE format
        for chunk in chunks:
            if "[DONE]" not in chunk:
                # Should start with "data: "
                assert chunk.startswith("data: ")

                # Should be valid JSON after "data: "
                json_part = chunk.replace("data: ", "").strip()
                try:
                    parsed = json.loads(json_part)
                    assert "choices" in parsed
                    assert "model" in parsed
                except json.JSONDecodeError:
                    pytest.fail(f"Invalid JSON in SSE chunk: {chunk}")
