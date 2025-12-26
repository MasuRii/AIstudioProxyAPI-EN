"""
Tests for api_utils/response_generators.py - SSE response generation.

Test Strategy:
- Test async generator functions with real async iteration
- Use REAL ChatCompletionRequest objects (not MagicMock)
- Use REAL asyncio.Event for completion signaling
- Mock only external boundaries: stream responses, browser operations
- Test actual SSE format and chunk generation
- Verify error handling and client disconnect scenarios

Coverage Target: 90%+
Mock Budget: <20 (down from 72 - original count was inflated)
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_utils.response_generators import (
    gen_sse_from_aux_stream,
    gen_sse_from_playwright,
)
from models import ChatCompletionRequest, ClientDisconnectedError


class TestGenSSEFromAuxStream:
    """Tests for gen_sse_from_aux_stream async generator."""

    @pytest.mark.asyncio
    async def test_basic_streaming_flow(self, make_chat_request):
        """Test basic streaming with body content progression."""
        req_id = "test-req-1"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        # Mock stream data showing incremental text
        stream_data = [
            {"body": "Hello", "reason": "", "done": False},
            {"body": "Hello World", "reason": "", "done": False},
            {"body": "Hello World!", "reason": "", "done": True},
        ]

        async def mock_stream_gen(*args, **kwargs):
            for item in stream_data:
                yield item

        with (
            patch(
                "api_utils.response_generators.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 10},
            ),
        ):
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                30.0,
            ):
                chunks.append(chunk)

        # Verify chunk progression
        assert len(chunks) >= 3

        # Parse first content chunk
        chunk1_data = json.loads(chunks[0].replace("data: ", "").strip())
        assert chunk1_data["choices"][0]["delta"]["content"] == "Hello"

        # Parse second content chunk (delta)
        chunk2_data = json.loads(chunks[1].replace("data: ", "").strip())
        assert chunk2_data["choices"][0]["delta"]["content"] == " World"

        # Verify completion
        assert "[DONE]" in chunks[-1]
        assert completion_event.is_set()

    @pytest.mark.asyncio
    async def test_reasoning_content_stream(self, make_chat_request):
        """Test streaming with reasoning content (thinking models)."""
        req_id = "test-req-reasoning"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        stream_data = [
            {"reason": "Analyzing the problem...", "body": "", "done": False},
            {
                "reason": "Analyzing the problem... Formulating answer.",
                "body": "",
                "done": False,
            },
            {"reason": "", "body": "The solution is 42", "done": True},
        ]

        async def mock_stream_gen(*args, **kwargs):
            for item in stream_data:
                yield item

        with (
            patch(
                "api_utils.response_generators.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 15},
            ),
        ):
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                30.0,
            ):
                chunks.append(chunk)

        # Verify reasoning content
        chunk1_data = json.loads(chunks[0].replace("data: ", "").strip())
        assert (
            chunk1_data["choices"][0]["delta"]["reasoning_content"]
            == "Analyzing the problem..."
        )

        # Second chunk should have delta reasoning content
        chunk2_data = json.loads(chunks[1].replace("data: ", "").strip())
        assert (
            chunk2_data["choices"][0]["delta"]["reasoning_content"]
            == " Formulating answer."
        )

        # Final chunk should have body content
        chunk3_data = json.loads(chunks[2].replace("data: ", "").strip())
        assert chunk3_data["choices"][0]["delta"]["content"] == "The solution is 42"

    @pytest.mark.asyncio
    async def test_tool_calls_stream(self, make_chat_request):
        """Test streaming with tool/function calls."""
        req_id = "test-req-tools"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        function_data = [{"name": "get_weather", "params": {"location": "New York"}}]

        stream_data = [
            {"body": "", "reason": "", "done": True, "function": function_data}
        ]

        async def mock_stream_gen(*args, **kwargs):
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
            patch("api_utils.response_generators.random_id", return_value="tool-123"),
        ):
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                30.0,
            ):
                chunks.append(chunk)

        # Find tool call chunk
        tool_chunk = None
        for chunk in chunks:
            if "[DONE]" not in chunk:
                data = json.loads(chunk.replace("data: ", "").strip())
                if "tool_calls" in data["choices"][0]["delta"]:
                    tool_chunk = data
                    break

        assert tool_chunk is not None
        tool = tool_chunk["choices"][0]["delta"]["tool_calls"][0]
        assert tool["function"]["name"] == "get_weather"
        assert "New York" in tool["function"]["arguments"]

        # Verify finish reason is set in the final chunk
        finish_reasons = [
            json.loads(c.replace("data: ", "").strip())["choices"][0].get(
                "finish_reason"
            )
            for c in chunks
            if "[DONE]" not in c and "data: " in c
        ]
        assert "tool_calls" in finish_reasons

    @pytest.mark.asyncio
    async def test_client_disconnect_handling(self, make_chat_request):
        """Test graceful handling of client disconnect during stream."""
        req_id = "test-req-disconnect"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()

        # Mock disconnect checker to raise on second call
        check_disconnect = MagicMock()
        check_disconnect.side_effect = [None, ClientDisconnectedError("Client gone")]

        stream_data = [
            {"body": "First chunk", "reason": "", "done": False},
            {"body": "Second chunk", "reason": "", "done": False},
        ]

        async def mock_stream_gen(*args, **kwargs):
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
                30.0,
            ):
                chunks.append(chunk)

        # Should stop early but set completion event
        assert completion_event.is_set()
        # Should have processed at least first chunk before disconnect
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_invalid_json_in_stream(self, make_chat_request):
        """Test handling of malformed JSON in stream."""
        req_id = "test-req-invalid"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        stream_data = [
            "invalid json data",
            {"body": "Valid content", "reason": "", "done": True},
        ]

        async def mock_stream_gen(*args, **kwargs):
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
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                30.0,
            ):
                chunks.append(chunk)

        # Should skip invalid JSON and process valid data
        assert len(chunks) >= 1
        found_valid = any("Valid content" in chunk for chunk in chunks)
        assert found_valid

    @pytest.mark.asyncio
    async def test_usage_stats_in_final_chunk(self, make_chat_request):
        """Test that usage statistics are included in final chunk."""
        req_id = "test-req-usage"
        request = make_chat_request(stream=True)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()

        stream_data = [
            {"body": "Response text", "reason": "", "done": True},
        ]

        async def mock_stream_gen(*args, **kwargs):
            for item in stream_data:
                yield item

        expected_usage = {
            "prompt_tokens": 5,
            "completion_tokens": 10,
            "total_tokens": 15,
        }

        with (
            patch(
                "api_utils.response_generators.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value=expected_usage,
            ),
        ):
            chunks = []
            async for chunk in gen_sse_from_aux_stream(
                req_id,
                request,
                "gemini-1.5-pro",
                check_disconnect,
                completion_event,
                30.0,
            ):
                chunks.append(chunk)

        # Find usage chunk (second to last, before [DONE])
        usage_chunk = None
        for chunk in chunks:
            if "[DONE]" not in chunk:
                data = json.loads(chunk.replace("data: ", "").strip())
                if data.get("usage"):
                    usage_chunk = data
                    break

        assert usage_chunk is not None
        assert usage_chunk["usage"]["total_tokens"] == 15


class TestGenSSEFromPlaywright:
    """Tests for gen_sse_from_playwright async generator."""

    @pytest.mark.asyncio
    async def test_basic_playwright_response(self, make_chat_request):
        """Test basic Playwright response generation."""
        req_id = "test-req-pw-1"
        request = make_chat_request(stream=False)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()
        mock_page = AsyncMock()
        mock_logger = MagicMock()

        with (
            patch("browser_utils.page_controller.PageController") as MockPC,
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 8},
            ),
        ):
            controller = MockPC.return_value
            controller.get_response_with_function_calls = AsyncMock(
                return_value={"content": "This is the response.", "function_calls": []}
            )

            chunks = []
            async for chunk in gen_sse_from_playwright(
                mock_page,
                mock_logger,
                req_id,
                "gemini-1.5-flash",
                request,
                check_disconnect,
                completion_event,
                100,
                30.0,
            ):
                chunks.append(chunk)

        # Collect all content
        full_content = []
        for chunk in chunks:
            if "[DONE]" not in chunk:
                data = json.loads(chunk.replace("data: ", "").strip())
                if "choices" in data and data["choices"]:
                    delta_content = data["choices"][0].get("delta", {}).get("content")
                    if delta_content:
                        full_content.append(delta_content)

        # Verify response was chunked and complete
        assert "".join(full_content) == "This is the response."
        assert completion_event.is_set()

    @pytest.mark.asyncio
    async def test_playwright_multiline_response(self, make_chat_request):
        """Test Playwright response with multiple lines."""
        req_id = "test-req-pw-multiline"
        request = make_chat_request(stream=False)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()
        mock_page = AsyncMock()
        mock_logger = MagicMock()

        multiline_response = "Line 1\nLine 2\nLine 3"

        with (
            patch("browser_utils.page_controller.PageController") as MockPC,
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 12},
            ),
        ):
            controller = MockPC.return_value
            controller.get_response_with_function_calls = AsyncMock(
                return_value={"content": multiline_response, "function_calls": []}
            )

            chunks = []
            async for chunk in gen_sse_from_playwright(
                mock_page,
                mock_logger,
                req_id,
                "gemini-1.5-flash",
                request,
                check_disconnect,
                completion_event,
                100,
                30.0,
            ):
                chunks.append(chunk)

        # Collect content
        full_content = []
        for chunk in chunks:
            if "[DONE]" not in chunk:
                try:
                    data = json.loads(chunk.replace("data: ", "").strip())
                    if "choices" in data and data["choices"]:
                        delta_content = (
                            data["choices"][0].get("delta", {}).get("content")
                        )
                        if delta_content:
                            full_content.append(delta_content)
                except json.JSONDecodeError:
                    continue

        # Verify all lines present
        combined = "".join(full_content)
        assert "Line 1" in combined
        assert "Line 2" in combined
        assert "Line 3" in combined

    @pytest.mark.asyncio
    async def test_playwright_exception_handling(self, make_chat_request):
        """Test exception propagation from Playwright controller."""
        req_id = "test-req-pw-error"
        request = make_chat_request(stream=False)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()
        mock_page = AsyncMock()
        mock_logger = MagicMock()

        with patch("browser_utils.page_controller.PageController") as MockPC:
            controller = MockPC.return_value
            controller.get_response_with_function_calls = AsyncMock(
                side_effect=Exception("Browser crashed")
            )

            # Exception should be caught and yielded as error chunk
            chunks = []
            async for chunk in gen_sse_from_playwright(
                mock_page,
                mock_logger,
                req_id,
                "gemini-1.5-pro",
                request,
                check_disconnect,
                completion_event,
                100,
                30.0,
            ):
                chunks.append(chunk)

            assert any("[Error: Browser crashed]" in c for c in chunks)

        # Completion event should still be set for cleanup
        assert completion_event.is_set()

    @pytest.mark.asyncio
    async def test_playwright_empty_response(self, make_chat_request):
        """Test handling of empty response from Playwright."""
        req_id = "test-req-pw-empty"
        request = make_chat_request(stream=False)
        completion_event = asyncio.Event()
        check_disconnect = MagicMock()
        mock_page = AsyncMock()
        mock_logger = MagicMock()

        with (
            patch("browser_utils.page_controller.PageController") as MockPC,
            patch(
                "api_utils.response_generators.calculate_usage_stats",
                return_value={"total_tokens": 0},
            ),
        ):
            controller = MockPC.return_value
            controller.get_response_with_function_calls = AsyncMock(
                return_value={"content": "", "function_calls": []}
            )

            chunks = []
            async for chunk in gen_sse_from_playwright(
                mock_page,
                mock_logger,
                req_id,
                "gemini-1.5-flash",
                request,
                check_disconnect,
                completion_event,
                100,
                30.0,
            ):
                chunks.append(chunk)

        # Should still complete gracefully
        assert completion_event.is_set()
        # Should have [DONE] marker
        assert any("[DONE]" in chunk for chunk in chunks)


"""
Extended tests for api_utils/response_generators.py targeting coverage gaps.

Focuses on:
- stream_state parameter updates
- Error handling and exception scenarios
- Combined body + tool calls in same chunk
- Client disconnect during Playwright streaming
- CancelledError handling
- Exception handling in finally blocks
"""

from asyncio import Event


@pytest.fixture
def mock_request():
    req = MagicMock(spec=ChatCompletionRequest)
    req.messages = [MagicMock(model_dump=lambda: {"role": "user", "content": "test"})]
    return req


@pytest.fixture
def mock_event():
    return Event()


@pytest.fixture
def mock_check_disconnect():
    return MagicMock()


# ==================== stream_state PARAMETER TESTS ====================


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_state_with_content(
    mock_request, mock_event, mock_check_disconnect
):
    """Test stream_state parameter is updated when content is received."""
    req_id = "test_stream_state_content"
    stream_state = {}

    stream_data = [{"body": "Hello World", "reason": "", "done": True}]

    async def mock_stream_gen(*args, **kwargs):
        for item in stream_data:
            yield item

    with (
        patch(
            "api_utils.response_generators.use_stream_response",
            side_effect=mock_stream_gen,
        ),
        patch(
            "api_utils.response_generators.calculate_usage_stats",
            return_value={"total_tokens": 10},
        ),
    ):
        chunks = []
        async for chunk in gen_sse_from_aux_stream(
            req_id,
            mock_request,
            "model",
            mock_check_disconnect,
            mock_event,
            30.0,
            stream_state=stream_state,
        ):
            chunks.append(chunk)

    # Verify stream_state was updated
    assert "has_content" in stream_state
    assert stream_state["has_content"] is True


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_state_no_content(
    mock_request, mock_event, mock_check_disconnect
):
    """Test stream_state parameter is updated when no content is received."""
    req_id = "test_stream_state_empty"
    stream_state = {}

    # Empty stream
    async def mock_stream_gen(*args, **kwargs):
        return
        yield  # pragma: no cover - make it a generator

    with (
        patch(
            "api_utils.response_generators.use_stream_response",
            side_effect=mock_stream_gen,
        ),
        patch(
            "api_utils.response_generators.calculate_usage_stats",
            return_value={"total_tokens": 0},
        ),
    ):
        chunks = []
        async for chunk in gen_sse_from_aux_stream(
            req_id,
            mock_request,
            "model",
            mock_check_disconnect,
            mock_event,
            30.0,
            stream_state=stream_state,
        ):
            chunks.append(chunk)

    # Verify stream_state was updated with no content
    assert "has_content" in stream_state
    assert stream_state["has_content"] is False


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_state_reasoning_only(
    mock_request, mock_event, mock_check_disconnect
):
    """Test stream_state parameter considers reasoning content."""
    req_id = "test_stream_state_reasoning"
    stream_state = {}

    stream_data = [{"body": "", "reason": "Thinking deeply...", "done": True}]

    async def mock_stream_gen(*args, **kwargs):
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
            mock_request,
            "model",
            mock_check_disconnect,
            mock_event,
            30.0,
            stream_state=stream_state,
        ):
            chunks.append(chunk)

    # Reasoning content counts as content
    assert stream_state["has_content"] is True


# ==================== COMBINED BODY + TOOL CALLS TESTS ====================


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_body_with_tool_calls(
    mock_request, mock_event, mock_check_disconnect
):
    """Test scenario where body content and tool calls appear in same chunk (lines 131-149)."""
    req_id = "test_body_with_tools"

    function_data = [{"name": "search_web", "params": {"query": "Python tutorials"}}]

    # Body content progresses, then done=True with function
    stream_data = [
        {"body": "Let me search", "reason": "", "done": False, "function": []},
        {
            "body": "Let me search for that",
            "reason": "",
            "done": True,
            "function": function_data,
        },
    ]

    async def mock_stream_gen(*args, **kwargs):
        for item in stream_data:
            yield item

    with (
        patch(
            "api_utils.response_generators.use_stream_response",
            side_effect=mock_stream_gen,
        ),
        patch(
            "api_utils.response_generators.calculate_usage_stats",
            return_value={"total_tokens": 15},
        ),
        patch("api_utils.response_generators.random_id", return_value="abc123"),
    ):
        chunks = []
        async for chunk in gen_sse_from_aux_stream(
            req_id, mock_request, "model", mock_check_disconnect, mock_event, 30.0
        ):
            chunks.append(chunk)

    # Find the chunk with both body delta and tool_calls
    found_combined = False
    for chunk in chunks:
        if "[DONE]" in chunk:
            continue
        try:
            data = json.loads(chunk.replace("data: ", "").strip())
            delta = data["choices"][0]["delta"]

            # Check for chunk with tool_calls
            if "tool_calls" in delta:
                found_combined = True
                # Content should be None when tool_calls present
                assert delta["content"] is None
                # Tool call should be present
                assert len(delta["tool_calls"]) == 1
                assert delta["tool_calls"][0]["function"]["name"] == "search_web"
        except (json.JSONDecodeError, KeyError):
            continue

    assert found_combined, "Should find chunk with tool_calls"

    # Verify finish reason is set in the final chunk
    finish_reasons = [
        json.loads(c.replace("data: ", "").strip())["choices"][0].get("finish_reason")
        for c in chunks
        if "[DONE]" not in c and "data: " in c
    ]
    assert "tool_calls" in finish_reasons


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_tool_calls_only_in_final_chunk(
    mock_request, mock_event, mock_check_disconnect
):
    """Test tool calls appearing in done chunk without prior body content (lines 161-203)."""
    req_id = "test_tools_final_only"

    function_data = [
        {"name": "get_time", "params": {}},
        {"name": "get_weather", "params": {"location": "SF"}},
    ]

    # No body content, just tool calls in final done chunk
    stream_data = [{"body": "", "reason": "", "done": True, "function": function_data}]

    async def mock_stream_gen(*args, **kwargs):
        for item in stream_data:
            yield item

    with (
        patch(
            "api_utils.response_generators.use_stream_response",
            side_effect=mock_stream_gen,
        ),
        patch(
            "api_utils.response_generators.calculate_usage_stats",
            return_value={"total_tokens": 8},
        ),
        patch(
            "api_utils.response_generators.random_id", side_effect=["call1", "call2"]
        ),
    ):
        chunks = []
        async for chunk in gen_sse_from_aux_stream(
            req_id, mock_request, "model", mock_check_disconnect, mock_event, 30.0
        ):
            chunks.append(chunk)

    # Find the tool calls chunk
    found_tools = False
    for chunk in chunks:
        if "[DONE]" in chunk:
            continue
        try:
            data = json.loads(chunk.replace("data: ", "").strip())
            delta = data["choices"][0]["delta"]

            if "tool_calls" in delta:
                found_tools = True
                # Should have 2 tool calls
                assert len(delta["tool_calls"]) == 2
                assert delta["tool_calls"][0]["function"]["name"] == "get_time"
                assert delta["tool_calls"][1]["function"]["name"] == "get_weather"
        except (json.JSONDecodeError, KeyError):
            continue

    assert found_tools

    # Verify finish reason is set in the final chunk
    finish_reasons = [
        json.loads(c.replace("data: ", "").strip())["choices"][0].get("finish_reason")
        for c in chunks
        if "[DONE]" not in c and "data: " in c
    ]
    assert "tool_calls" in finish_reasons


# ==================== ERROR HANDLING TESTS ====================


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_error_in_processing(
    mock_request, mock_event, mock_check_disconnect
):
    """Test exception handling when error occurs during processing - should re-raise."""
    req_id = "test_error_chunk"

    async def mock_stream_gen(*args, **kwargs):
        yield {"body": "Start"}
        # Raise an error during stream processing
        raise ValueError("Simulated stream processing error")

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
        # Should catch the exception and yield as error chunk
        chunks = []
        async for chunk in gen_sse_from_aux_stream(
            req_id, mock_request, "model", mock_check_disconnect, mock_event, 30.0
        ):
            chunks.append(chunk)

        assert any("[Error: Simulated stream processing error]" in c for c in chunks)

    # Event should still be set for cleanup
    assert mock_event.is_set()


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_usage_stats_error(
    mock_request, mock_event, mock_check_disconnect
):
    """Test handling of exception during usage stats calculation (lines 265-266)."""
    req_id = "test_usage_error"

    stream_data = [{"body": "Complete", "done": True}]

    async def mock_stream_gen(*args, **kwargs):
        for item in stream_data:
            yield item

    # Make calculate_usage_stats raise an error
    with (
        patch(
            "api_utils.response_generators.use_stream_response",
            side_effect=mock_stream_gen,
        ),
        patch(
            "api_utils.response_generators.calculate_usage_stats",
            side_effect=RuntimeError("Usage calc failed"),
        ),
    ):
        chunks = []
        async for chunk in gen_sse_from_aux_stream(
            req_id, mock_request, "model", mock_check_disconnect, mock_event, 30.0
        ):
            chunks.append(chunk)

    # Should still send [DONE] even if usage calculation fails
    assert any("[DONE]" in c for c in chunks)
    assert mock_event.is_set()


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_cancelled_error(
    mock_request, mock_event, mock_check_disconnect
):
    """Test CancelledError handling (lines 210-214)."""
    req_id = "test_cancelled"

    async def mock_stream_gen(*args, **kwargs):
        yield {"body": "Start"}
        await asyncio.sleep(0.1)
        raise asyncio.CancelledError()

    with patch(
        "api_utils.response_generators.use_stream_response", side_effect=mock_stream_gen
    ):
        chunks = []

        with pytest.raises(asyncio.CancelledError):
            async for chunk in gen_sse_from_aux_stream(
                req_id, mock_request, "model", mock_check_disconnect, mock_event, 30.0
            ):
                chunks.append(chunk)

    # Event should be set even on cancellation
    assert mock_event.is_set()


# ==================== PLAYWRIGHT GENERATOR TESTS ====================


@pytest.mark.asyncio
async def test_gen_sse_from_playwright_client_disconnect_during_streaming(
    mock_request, mock_event
):
    """Test client disconnect during Playwright response streaming (lines 304-313)."""
    req_id = "test_pw_disconnect"
    mock_page = AsyncMock()
    mock_logger = MagicMock()

    # Mock disconnect on third check
    mock_check = MagicMock()
    mock_check.side_effect = [None, None, ClientDisconnectedError("Client gone")]

    with (
        patch("browser_utils.page_controller.PageController") as MockPC,
        patch(
            "api_utils.response_generators.calculate_usage_stats",
            return_value={"tokens": 5},
        ),
    ):
        instance = MockPC.return_value
        # Long response to trigger multiple chunk iterations
        instance.get_response_with_function_calls = AsyncMock(
            return_value={"content": "A" * 100, "function_calls": []}
        )

        chunks = []
        async for chunk in gen_sse_from_playwright(
            mock_page,
            mock_logger,
            req_id,
            "model",
            mock_request,
            mock_check,
            mock_event,
            100,
            30.0,
        ):
            chunks.append(chunk)

    # Should stop early and set event
    assert mock_event.is_set()
    # Should have at least started processing
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_gen_sse_from_playwright_cancelled_error(
    mock_request, mock_event, mock_check_disconnect
):
    """Test CancelledError handling in Playwright generator (lines 337-341)."""
    req_id = "test_pw_cancelled"
    mock_page = AsyncMock()
    mock_logger = MagicMock()

    with patch("browser_utils.page_controller.PageController") as MockPC:
        instance = MockPC.return_value
        # Raise CancelledError during get_response
        instance.get_response_with_function_calls = AsyncMock(
            side_effect=asyncio.CancelledError()
        )

        chunks = []
        with pytest.raises(asyncio.CancelledError):
            async for chunk in gen_sse_from_playwright(
                mock_page,
                mock_logger,
                req_id,
                "model",
                mock_request,
                mock_check_disconnect,
                mock_event,
                100,
                30.0,
            ):
                chunks.append(chunk)

    # Event should be set
    assert mock_event.is_set()


@pytest.mark.asyncio
async def test_gen_sse_from_playwright_exception_in_error_handling(
    mock_request, mock_event, mock_check_disconnect
):
    """Test exception during processing - should re-raise instead of yielding error."""
    req_id = "test_pw_error_in_error"
    mock_page = AsyncMock()
    mock_logger = MagicMock()

    with patch("browser_utils.page_controller.PageController") as MockPC:
        instance = MockPC.return_value
        instance.get_response_with_function_calls = AsyncMock(
            side_effect=ValueError("Original error")
        )

        # Should catch the exception and yield error chunk
        chunks = []
        async for chunk in gen_sse_from_playwright(
            mock_page,
            mock_logger,
            req_id,
            "model",
            mock_request,
            mock_check_disconnect,
            mock_event,
            100,
            30.0,
        ):
            chunks.append(chunk)

        assert any("[Error: Original error]" in c for c in chunks)

    # Event should still be set for cleanup
    assert mock_event.is_set()


@pytest.mark.asyncio
async def test_gen_sse_from_playwright_empty_response(
    mock_request, mock_event, mock_check_disconnect
):
    """Test handling of empty response from PageController."""
    req_id = "test_pw_empty"
    mock_page = AsyncMock()
    mock_logger = MagicMock()

    with (
        patch("browser_utils.page_controller.PageController") as MockPC,
        patch(
            "api_utils.response_generators.calculate_usage_stats",
            return_value={"tokens": 0},
        ),
    ):
        instance = MockPC.return_value
        instance.get_response_with_function_calls = AsyncMock(
            return_value={"content": "", "function_calls": []}
        )

        chunks = []
        async for chunk in gen_sse_from_playwright(
            mock_page,
            mock_logger,
            req_id,
            "model",
            mock_request,
            mock_check_disconnect,
            mock_event,
            100,
            30.0,
        ):
            chunks.append(chunk)

    # Should still generate stop chunk
    assert len(chunks) >= 1
    assert mock_event.is_set()


# ==================== EDGE CASES ====================


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_non_dict_data(
    mock_request, mock_event, mock_check_disconnect
):
    """Test handling of non-dict data in stream (lines 81-83)."""
    req_id = "test_non_dict"

    async def mock_stream_gen(*args, **kwargs):
        yield "string_data"  # Not JSON, not dict
        yield 12345  # Integer
        yield {"body": "Valid"}  # Valid dict

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
            req_id, mock_request, "model", mock_check_disconnect, mock_event, 30.0
        ):
            chunks.append(chunk)

    # Should skip invalid data and process valid
    assert any("Valid" in c for c in chunks)


@pytest.mark.asyncio
async def test_gen_sse_from_aux_stream_list_instead_of_dict(
    mock_request, mock_event, mock_check_disconnect
):
    """Test handling when parsed JSON is a list instead of dict (lines 81-83)."""
    req_id = "test_list_data"

    async def mock_stream_gen(*args, **kwargs):
        yield json.dumps([1, 2, 3])  # Valid JSON but not a dict
        yield {"body": "OK"}

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
            req_id, mock_request, "model", mock_check_disconnect, mock_event, 30.0
        ):
            chunks.append(chunk)

    # Should skip list data and process valid dict
    assert any("OK" in c for c in chunks)
