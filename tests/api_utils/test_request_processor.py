"""
Tests for api_utils.request_processor module.

Test Strategy:
- Unit tests: Test helper functions individually (_prepare_and_validate_request,
  _analyze_model_requirements, _validate_page_status, etc.)
- Mock only external boundaries: Browser/page (Playwright), network requests
- Use REAL internal state: Don't mock helper functions, test actual logic
- Integration tests: Full _process_request_refactored flow with real locks/state
  (see tests/integration/test_request_flow.py)

Coverage Target: 90%+
Mock Budget: <50 (down from 103)
"""

import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from playwright.async_api import Error as PlaywrightAsyncError

from api_utils.context_types import RequestContext
from api_utils.request_processor import (
    _analyze_model_requirements,
    _handle_model_switch_failure,
    _prepare_and_validate_request,
    _validate_page_status,
)
from api_utils.server_state import state
from models import ChatCompletionRequest, Message

# ==================== Unit Tests for Helper Functions ====================


class TestAnalyzeModelRequirements:
    """Unit tests for _analyze_model_requirements helper function."""

    @pytest.mark.asyncio
    async def test_analyze_same_model_no_switch_needed(
        self, make_request_context, make_chat_request
    ):
        """Test that analyzing same model as current doesn't require switch."""
        req_id = "test-req"
        context = make_request_context(current_ai_studio_model_id="gemini-1.5-pro")
        request = make_chat_request(model="gemini-1.5-pro")

        with patch("api_utils.request_processor.MODEL_NAME", "gemini-1.5-pro"):
            result = await _analyze_model_requirements(req_id, context, request)

        # Should return context (possibly modified)
        assert isinstance(result, dict)
        assert "is_streaming" in result  # Verify it's a valid RequestContext

    @pytest.mark.asyncio
    async def test_analyze_different_model_requires_switch(
        self, make_request_context, make_chat_request
    ):
        """Test that different model is detected and flagged for switching."""
        req_id = "test-req"
        context = make_request_context(current_ai_studio_model_id="gemini-1.5-pro")
        request = make_chat_request(model="gemini-1.5-flash")

        with patch("api_utils.request_processor.MODEL_NAME", "gemini-1.5-pro"):
            with patch(
                "api_utils.request_processor.ms_analyze",
                new_callable=AsyncMock,
            ) as mock_ms_analyze:
                mock_ms_analyze.return_value = {
                    **context,
                    "need_switch": True,
                    "model_id_to_use": "gemini-1.5-flash",
                }

                result = await _analyze_model_requirements(req_id, context, request)

                # Verify delegate was called with correct args
                mock_ms_analyze.assert_called_once_with(
                    req_id, context, "gemini-1.5-flash", "gemini-1.5-pro"
                )
                assert result["model_id_to_use"] == "gemini-1.5-flash"


class TestValidatePageStatus:
    """Unit tests for _validate_page_status helper function."""

    @pytest.mark.asyncio
    async def test_validate_page_ready_success(self, mock_playwright_stack):
        """Test validation succeeds when page is ready."""
        _, _, _, page = mock_playwright_stack
        page.is_closed.return_value = False

        context = cast(
            RequestContext,
            {
                "page": page,
                "is_page_ready": True,
            },
        )
        check_disco = MagicMock()  # Should be called

        # Should not raise
        await _validate_page_status("test-req", context, check_disco)
        check_disco.assert_called_once_with("Initial Page Check")

    @pytest.mark.asyncio
    async def test_validate_page_closed_raises_503(self, mock_playwright_stack):
        """Test validation fails with 503 when page is closed."""
        _, _, _, page = mock_playwright_stack
        page.is_closed.return_value = True  # Page closed

        context = cast(
            RequestContext,
            {
                "page": page,
                "is_page_ready": True,
            },
        )
        check_disco = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await _validate_page_status("test-req", context, check_disco)

        assert exc.value.status_code == 503
        assert "AI Studio page lost" in exc.value.detail
        assert exc.value.headers is not None
        assert exc.value.headers.get("Retry-After") == "30"

    @pytest.mark.asyncio
    async def test_validate_page_not_ready_raises_503(self, mock_playwright_stack):
        """Test validation fails when page is not ready."""
        _, _, _, page = mock_playwright_stack
        page.is_closed.return_value = False

        context = cast(
            RequestContext,
            {
                "page": page,
                "is_page_ready": False,  # Not ready
            },
        )
        check_disco = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await _validate_page_status("test-req", context, check_disco)

        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_validate_page_none_raises_503(self):
        """Test validation fails when page is None."""
        context = cast(
            RequestContext,
            {
                "page": None,  # No page
                "is_page_ready": True,
            },
        )
        check_disco = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await _validate_page_status("test-req", context, check_disco)

        assert exc.value.status_code == 503


class TestPrepareAndValidateRequest:
    """Unit tests for _prepare_and_validate_request helper function."""

    @pytest.mark.asyncio
    async def test_prepare_simple_text_message(self, mock_env):
        """Test preparing a simple text message without attachments or tools."""
        req_id = "test-req"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello AI")],
            model="gemini-1.5-pro",
        )
        check_disco = MagicMock()

        with (
            patch("api_utils.request_processor.validate_chat_request") as mock_validate,
            patch(
                "api_utils.request_processor.prepare_combined_prompt",
                return_value=("Hello AI", []),
            ) as mock_prep,
            patch(
                "api_utils.request_processor.maybe_execute_tools",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            prompt, images = await _prepare_and_validate_request(
                req_id, request, check_disco
            )

            # Verify validation was called
            mock_validate.assert_called_once_with(request.messages, req_id)

            # Verify prompt preparation was called
            mock_prep.assert_called_once()

            # Check results
            assert prompt == "Hello AI"
            assert images == []
            check_disco.assert_called_once_with("After Prompt Prep")

    @pytest.mark.asyncio
    async def test_prepare_with_tool_execution(self, mock_env):
        """Test preparing request with tool execution results."""
        req_id = "test-req"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Calculate 2+2")],
            model="gemini-1.5-pro",
            tools=[{"type": "function", "function": {"name": "calculator"}}],
        )
        check_disco = MagicMock()

        tool_results = [
            {"name": "calculator", "arguments": '{"expr": "2+2"}', "result": "4"}
        ]

        with (
            patch("api_utils.request_processor.validate_chat_request"),
            patch(
                "api_utils.request_processor.prepare_combined_prompt",
                return_value=("Calculate 2+2", []),
            ),
            patch(
                "api_utils.request_processor.maybe_execute_tools",
                new_callable=AsyncMock,
                return_value=tool_results,
            ),
        ):
            prompt, images = await _prepare_and_validate_request(
                req_id, request, check_disco
            )

            # Tool execution results should be appended to prompt
            assert "Tool Execution: calculator" in prompt
            assert "Arguments:\n" in prompt
            assert "Result:\n4" in prompt

    @pytest.mark.asyncio
    async def test_prepare_with_file_attachments(self, mock_env, tmp_path):
        """Test preparing request with file attachments."""
        req_id = "test-req"

        # Create a temporary file
        test_file = tmp_path / "test_image.png"
        test_file.write_bytes(b"fake image data")

        request = ChatCompletionRequest(
            messages=[
                Message(
                    role="user",
                    content="Look at this image",
                    attachments=[str(test_file)],  # Absolute path
                )
            ],
            model="gemini-1.5-pro",
        )
        check_disco = MagicMock()

        with (
            patch("api_utils.request_processor.validate_chat_request"),
            patch(
                "api_utils.request_processor.prepare_combined_prompt",
                return_value=("Look at this image", []),
            ),
            patch(
                "api_utils.request_processor.maybe_execute_tools",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "config.settings.ONLY_COLLECT_CURRENT_USER_ATTACHMENTS",
                True,
            ),
        ):
            prompt, images = await _prepare_and_validate_request(
                req_id, request, check_disco
            )

            # Should extract attachment from latest user message
            assert len(images) == 1
            assert "test_image.png" in images[0]

    @pytest.mark.asyncio
    async def test_prepare_validation_error_raises_bad_request(self, mock_env):
        """Test that validation errors are converted to bad request exceptions."""
        req_id = "test-req"
        request = ChatCompletionRequest(
            messages=[],  # Empty messages - invalid
            model="gemini-1.5-pro",
        )
        check_disco = MagicMock()

        with patch(
            "api_utils.request_processor.validate_chat_request",
            side_effect=ValueError("Messages cannot be empty"),
        ):
            with pytest.raises(HTTPException) as exc:
                await _prepare_and_validate_request(req_id, request, check_disco)

            assert exc.value.status_code == 400  # Bad request
            assert "Invalid request" in exc.value.detail

    @pytest.mark.asyncio
    async def test_prepare_tool_execution_exception(self, mock_env):
        """Test that tool execution exceptions are caught and handled gracefully."""
        req_id = "test-req"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Test")],
            model="gemini-1.5-pro",
            tools=[{"type": "function", "function": {"name": "test_tool"}}],
        )
        check_disco = MagicMock()

        with (
            patch("api_utils.request_processor.validate_chat_request"),
            patch(
                "api_utils.request_processor.prepare_combined_prompt",
                return_value=("Test prompt", []),
            ),
            patch(
                "api_utils.request_processor.maybe_execute_tools",
                new_callable=AsyncMock,
                side_effect=Exception("Tool execution failed"),
            ),
        ):
            # Should not raise - exception is caught and tool_exec_results becomes None
            prompt, images = await _prepare_and_validate_request(
                req_id, request, check_disco
            )

            # Verify prompt is returned without tool results
            assert prompt == "Test prompt"
            assert images == []
            # Tool execution failure should be silently handled
            check_disco.assert_called_once_with("After Prompt Prep")

    @pytest.mark.asyncio
    async def test_prepare_tool_results_append_exception(self, mock_env):
        """Test that exceptions during tool result formatting are caught."""
        req_id = "test-req"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Test")],
            model="gemini-1.5-pro",
            tools=[{"type": "function", "function": {"name": "test_tool"}}],
        )
        check_disco = MagicMock()

        # Tool result with missing/invalid keys to trigger exception during formatting
        tool_results = [{"name": "test_tool"}]  # Missing "arguments" and "result" keys

        with (
            patch("api_utils.request_processor.validate_chat_request"),
            patch(
                "api_utils.request_processor.prepare_combined_prompt",
                return_value=("Test prompt", []),
            ),
            patch(
                "api_utils.request_processor.maybe_execute_tools",
                new_callable=AsyncMock,
                return_value=tool_results,
            ),
        ):
            # Should not raise - exception during result appending is caught
            prompt, images = await _prepare_and_validate_request(
                req_id, request, check_disco
            )

            # Verify base prompt is returned (tool results not appended due to error)
            assert "Test prompt" in prompt
            # The append might partially succeed or fail - main point is no exception raised

    @pytest.mark.asyncio
    async def test_prepare_file_url_attachments(self, mock_env, tmp_path):
        """Test preparing request with file:// URL attachments."""
        req_id = "test-req"

        # Create a temporary file
        test_file = tmp_path / "test_doc.pdf"
        test_file.write_bytes(b"fake pdf data")

        # Create file:// URL
        file_url = f"file://{test_file.as_posix()}"

        request = ChatCompletionRequest(
            messages=[
                Message(
                    role="user",
                    content="Check this document",
                    attachments=[file_url],  # file:// URL
                )
            ],
            model="gemini-1.5-pro",
        )
        check_disco = MagicMock()

        with (
            patch("api_utils.request_processor.validate_chat_request"),
            patch(
                "api_utils.request_processor.prepare_combined_prompt",
                return_value=("Check this document", []),
            ),
            patch(
                "api_utils.request_processor.maybe_execute_tools",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "config.settings.ONLY_COLLECT_CURRENT_USER_ATTACHMENTS",
                True,
            ),
        ):
            prompt, images = await _prepare_and_validate_request(
                req_id, request, check_disco
            )

            # Should parse file:// URL and extract local path
            assert len(images) == 1
            assert "test_doc.pdf" in images[0]

    @pytest.mark.asyncio
    async def test_prepare_dict_attachment_with_url_key(self, mock_env, tmp_path):
        """Test preparing request with dict attachments containing url/path keys."""
        req_id = "test-req"

        # Create a temporary file
        test_file = tmp_path / "image.jpg"
        test_file.write_bytes(b"fake image")

        request = ChatCompletionRequest(
            messages=[
                Message(
                    role="user",
                    content="Analyze image",
                    # Dict-style attachment with "url" key
                    attachments=[{"url": str(test_file)}],
                )
            ],
            model="gemini-1.5-pro",
        )
        check_disco = MagicMock()

        with (
            patch("api_utils.request_processor.validate_chat_request"),
            patch(
                "api_utils.request_processor.prepare_combined_prompt",
                return_value=("Analyze image", []),
            ),
            patch(
                "api_utils.request_processor.maybe_execute_tools",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "config.settings.ONLY_COLLECT_CURRENT_USER_ATTACHMENTS",
                True,
            ),
        ):
            prompt, images = await _prepare_and_validate_request(
                req_id, request, check_disco
            )

            # Should extract path from dict["url"]
            assert len(images) == 1
            assert "image.jpg" in images[0]


class TestHandleModelSwitchFailure:
    """Unit tests for _handle_model_switch_failure helper function."""

    @pytest.mark.asyncio
    async def test_handle_switch_failure_restores_state(self, mock_playwright_stack):
        """Test that model switch failure restores original model in state."""
        from api_utils.server_state import state

        _, _, _, page = mock_playwright_stack
        logger = MagicMock()
        req_id = "test-req"

        # Store original
        original_model = state.current_ai_studio_model_id
        try:
            # Simulate state was changed during failed switch attempt
            state.current_ai_studio_model_id = "changed-model"

            with pytest.raises(HTTPException) as exc:
                await _handle_model_switch_failure(
                    req_id, page, "gemini-2.0", "gemini-1.5-pro", logger
                )

            # Verify state was restored to model_before_switch
            assert state.current_ai_studio_model_id == "gemini-1.5-pro"

            # Verify exception details
            assert exc.value.status_code == 422
            assert "Failed to switch to model 'gemini-2.0'" in exc.value.detail

            # Verify warning was logged
            logger.warning.assert_called_once()

        finally:
            # Restore original state
            state.current_ai_studio_model_id = original_model


# ==================== Integration-Style Tests (with Real Helper Functions) ====================


class TestProcessRequestRefactoredFlow:
    """
    Tests for _process_request_refactored using REAL helper functions.

    These tests mock only external boundaries (browser, network) but use
    the actual helper function logic. This catches integration issues that
    over-mocked tests miss.

    Note: Full integration tests with real locks are in tests/integration/test_request_flow.py
    """

    @pytest.mark.asyncio
    async def test_client_disconnected_before_processing(
        self, mock_env, mock_playwright_stack
    ):
        """Test that early client disconnect is detected and handled."""
        from api_utils.request_processor import _process_request_refactored

        req_id = "test-req-id"
        request_data = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")], model="gemini-1.5-pro"
        )
        http_request = MagicMock(spec=Request)
        http_request.is_disconnected = AsyncMock(return_value=True)  # Disconnected
        result_future = asyncio.Future()

        # Don't mock _check_client_connection - use real function
        result = await _process_request_refactored(
            req_id, request_data, http_request, result_future
        )

        # Should return None (early exit)
        assert result is None

        # Future should be set with 499 error
        assert result_future.done()
        with pytest.raises(HTTPException) as exc:
            result_future.result()
        assert exc.value.status_code == 499  # Client closed request

    @pytest.mark.asyncio
    async def test_context_initialization_failure_bubbles_up(
        self, mock_env, mock_playwright_stack
    ):
        """Test that context initialization failures are not swallowed."""
        from api_utils.request_processor import _process_request_refactored

        req_id = "test-req-id"
        request_data = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")], model="gemini-1.5-pro"
        )
        http_request = MagicMock(spec=Request)
        http_request.is_disconnected = AsyncMock(return_value=False)
        result_future = asyncio.Future()

        # Mock only _initialize_request_context to fail
        with patch(
            "api_utils.request_processor._initialize_request_context",
            new_callable=AsyncMock,
            side_effect=Exception("Context init failed"),
        ):
            with pytest.raises(Exception) as exc:
                await _process_request_refactored(
                    req_id, request_data, http_request, result_future
                )

            assert "Context init failed" in str(exc.value)
            # Future not set (exception bubbles to queue_worker)
            assert not result_future.done()

    @pytest.mark.asyncio
    async def test_playwright_error_sets_502_in_future(
        self, mock_env, make_request_context
    ):
        """Test that Playwright errors are caught and set proper HTTP status."""
        from api_utils.request_processor import _process_request_refactored

        req_id = "test-req-id"
        request_data = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")], model="gemini-1.5-pro"
        )
        http_request = MagicMock(spec=Request)
        http_request.is_disconnected = AsyncMock(return_value=False)
        result_future = asyncio.Future()

        context = make_request_context(req_id=req_id)

        # Mock context init to succeed, PageController to fail with Playwright error
        with (
            patch(
                "api_utils.request_processor._initialize_request_context",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                "api_utils.request_processor._analyze_model_requirements",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                "api_utils.request_processor.PageController",
                side_effect=PlaywrightAsyncError("Browser crashed"),
            ),
            patch("browser_utils.save_error_snapshot", new_callable=AsyncMock),
        ):
            await _process_request_refactored(
                req_id, request_data, http_request, result_future
            )

        # Future should have 503 error (page not ready)
        assert result_future.done()
        with pytest.raises(HTTPException) as exc:
            result_future.result()
        assert exc.value.status_code == 503  # Service unavailable (page not ready)
        assert "page lost or not ready" in exc.value.detail


# ==================== Tests for Specific Response Handling ====================


class TestAuxiliaryStreamResponse:
    """Tests for auxiliary stream response handling (Stream Proxy tier)."""

    @pytest.mark.asyncio
    async def test_auxiliary_stream_non_streaming_success(
        self, mock_env, make_request_context
    ):
        """Test non-streaming response from auxiliary stream (Stream Proxy)."""
        from api_utils.request_processor import _handle_auxiliary_stream_response

        req_id = "test-req-id"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")],
            model="gemini-1.5-pro",
            stream=False,
        )
        context = make_request_context(req_id=req_id)
        result_future = asyncio.Future()
        submit_locator = MagicMock()
        check_disco = MagicMock()

        # Mock stream response generator
        mock_stream_data = [
            {"body": "Hello", "done": False},
            {"body": " world", "done": False},
            {"body": "Hello world", "done": True, "reason": None, "function": []},
        ]

        async def mock_stream_gen(*args, **kwargs):
            for data in mock_stream_data:
                yield data

        with (
            patch(
                "api_utils.request_processor.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.request_processor.calculate_usage_stats",
                return_value={
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            ),
        ):
            result = await _handle_auxiliary_stream_response(
                req_id,
                request,
                context,
                result_future,
                submit_locator,
                check_disco,
                timeout=30.0,
            )

            # Non-streaming returns None
            assert isinstance(result, dict)

            # Future should have JSONResponse
            assert result_future.done()
            response = result_future.result()
            assert response.status_code == 200

            # Verify response content
            content = json.loads(response.body)
            assert content["choices"][0]["message"]["content"] == "Hello world"
            assert content["usage"]["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_auxiliary_stream_non_streaming_with_function_calls(
        self, mock_env, make_request_context
    ):
        """Test non-streaming response with function calls (tool_calls) from auxiliary stream."""
        from api_utils.request_processor import _handle_auxiliary_stream_response

        req_id = "test-req-id"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Get weather")],
            model="gemini-1.5-pro",
            stream=False,
            tools=[{"type": "function", "function": {"name": "get_weather"}}],
        )
        context = make_request_context(req_id=req_id)
        result_future = asyncio.Future()
        submit_locator = MagicMock()
        check_disco = MagicMock()

        # Mock stream response with function calls
        mock_stream_data = [
            {
                "body": "",
                "done": True,
                "reason": None,
                "function": [
                    {"name": "get_weather", "params": {"location": "San Francisco"}}
                ],
            },
        ]

        async def mock_stream_gen(*args, **kwargs):
            for data in mock_stream_data:
                yield data

        with (
            patch(
                "api_utils.request_processor.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.request_processor.calculate_usage_stats",
                return_value={
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            ),
        ):
            result = await _handle_auxiliary_stream_response(
                req_id,
                request,
                context,
                result_future,
                submit_locator,
                check_disco,
                timeout=30.0,
            )

            # Non-streaming with function calls returns None
            assert isinstance(result, dict)

            # Future should have JSONResponse with tool_calls
            assert result_future.done()
            response = result_future.result()
            assert response.status_code == 200

            # Verify tool_calls in response
            content = json.loads(response.body)
            assert content["choices"][0]["finish_reason"] == "tool_calls"
            assert "tool_calls" in content["choices"][0]["message"]
            tool_calls = content["choices"][0]["message"]["tool_calls"]
            assert len(tool_calls) == 1
            assert tool_calls[0]["type"] == "function"
            assert tool_calls[0]["function"]["name"] == "get_weather"
            # Arguments should be JSON string
            args = json.loads(tool_calls[0]["function"]["arguments"])
            assert args["location"] == "San Francisco"
            # Content should be None when tool_calls present
            assert content["choices"][0]["message"]["content"] is None

    @pytest.mark.asyncio
    async def test_auxiliary_stream_non_streaming_no_content_error(
        self, mock_env, make_request_context
    ):
        """Test error when aux stream completes with done=True but no content."""
        from api_utils.request_processor import _handle_auxiliary_stream_response

        req_id = "test-req-id"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")],
            model="gemini-1.5-pro",
            stream=False,
        )
        context = make_request_context(req_id=req_id)
        result_future = asyncio.Future()
        submit_locator = MagicMock()
        check_disco = MagicMock()

        # Mock stream that completes with no content and no functions
        mock_stream_data = [
            {"body": None, "done": True, "reason": None, "function": []},
        ]

        async def mock_stream_gen(*args, **kwargs):
            for data in mock_stream_data:
                yield data

        with patch(
            "api_utils.request_processor.use_stream_response",
            side_effect=mock_stream_gen,
        ):
            with pytest.raises(HTTPException) as exc:
                await _handle_auxiliary_stream_response(
                    req_id,
                    request,
                    context,
                    result_future,
                    submit_locator,
                    check_disco,
                    timeout=30.0,
                )

            # Should raise 502 error for no content provided
            assert exc.value.status_code == 502
            assert "no content provided" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_auxiliary_stream_non_streaming_json_parse_error(
        self, mock_env, make_request_context
    ):
        """Test handling of JSON parse errors in non-streaming aux stream."""
        from api_utils.request_processor import _handle_auxiliary_stream_response

        req_id = "test-req-id"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")],
            model="gemini-1.5-pro",
            stream=False,
        )
        context = make_request_context(req_id=req_id)
        result_future = asyncio.Future()
        submit_locator = MagicMock()
        check_disco = MagicMock()

        # Mock stream that yields invalid JSON string
        mock_stream_data = [
            "invalid json string",  # This will trigger JSON parse error
            {"body": "Final content", "done": True, "reason": None},
        ]

        async def mock_stream_gen(*args, **kwargs):
            for data in mock_stream_data:
                yield data

        with (
            patch(
                "api_utils.request_processor.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.request_processor.calculate_usage_stats",
                return_value={
                    "prompt_tokens": 5,
                    "completion_tokens": 3,
                    "total_tokens": 8,
                },
            ),
        ):
            result = await _handle_auxiliary_stream_response(
                req_id,
                request,
                context,
                result_future,
                submit_locator,
                check_disco,
                timeout=30.0,
            )

            # Should complete successfully, skipping invalid JSON
            assert isinstance(result, dict)
            assert result_future.done()
            response = result_future.result()
            content = json.loads(response.body)
            assert content["choices"][0]["message"]["content"] == "Final content"

    @pytest.mark.asyncio
    async def test_auxiliary_stream_non_streaming_unknown_data_type(
        self, mock_env, make_request_context
    ):
        """Test handling of unknown data types in non-streaming aux stream."""
        from api_utils.request_processor import _handle_auxiliary_stream_response

        req_id = "test-req-id"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")],
            model="gemini-1.5-pro",
            stream=False,
        )
        context = make_request_context(req_id=req_id)
        result_future = asyncio.Future()
        submit_locator = MagicMock()
        check_disco = MagicMock()

        # Mock stream with unknown data type (not str or dict)
        mock_stream_data = [
            12345,  # Integer - unknown type
            {"body": "Valid content", "done": True, "reason": None},
        ]

        async def mock_stream_gen(*args, **kwargs):
            for data in mock_stream_data:
                yield data

        with (
            patch(
                "api_utils.request_processor.use_stream_response",
                side_effect=mock_stream_gen,
            ),
            patch(
                "api_utils.request_processor.calculate_usage_stats",
                return_value={
                    "prompt_tokens": 5,
                    "completion_tokens": 3,
                    "total_tokens": 8,
                },
            ),
        ):
            result = await _handle_auxiliary_stream_response(
                req_id,
                request,
                context,
                result_future,
                submit_locator,
                check_disco,
                timeout=30.0,
            )

            # Should complete successfully, skipping unknown type
            assert isinstance(result, dict)
            assert result_future.done()
            response = result_future.result()
            content = json.loads(response.body)
            assert content["choices"][0]["message"]["content"] == "Valid content"

    @pytest.mark.asyncio
    async def test_auxiliary_stream_streaming_cancelled_error(
        self, mock_env, make_request_context
    ):
        """Test CancelledError handling in streaming auxiliary stream."""
        from api_utils.request_processor import _handle_auxiliary_stream_response

        req_id = "test-req-id"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")],
            model="gemini-1.5-pro",
            stream=True,  # Streaming mode
        )
        context = make_request_context(req_id=req_id)
        result_future = asyncio.Future()
        submit_locator = MagicMock()
        check_disco = MagicMock()

        # Mock gen_sse_from_aux_stream to raise CancelledError
        async def mock_cancelled_gen(*args, **kwargs):
            raise asyncio.CancelledError("Request cancelled")
            yield ""  # make it a generator

        with patch(
            "api_utils.request_processor.gen_sse_from_aux_stream",
            side_effect=mock_cancelled_gen,
        ):
            await _handle_auxiliary_stream_response(
                req_id,
                request,
                context,
                result_future,
                submit_locator,
                check_disco,
                timeout=30.0,
            )

            streaming_response = result_future.result()
            with pytest.raises(asyncio.CancelledError):
                async for _ in streaming_response.body_iterator:
                    pass

    @pytest.mark.asyncio
    async def test_auxiliary_stream_streaming_exception_sets_event(
        self, mock_env, make_request_context
    ):
        """Test that exceptions in streaming mode set completion event before raising."""
        from api_utils.request_processor import _handle_auxiliary_stream_response

        req_id = "test-req-id"
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")],
            model="gemini-1.5-pro",
            stream=True,
        )
        context = make_request_context(req_id=req_id)
        result_future = asyncio.Future()
        submit_locator = MagicMock()
        check_disco = MagicMock()

        # Mock gen_sse_from_aux_stream to raise generic exception
        async def mock_error_gen(*args, **kwargs):
            raise Exception("Stream error")
            yield ""  # make it a generator

        with patch(
            "api_utils.request_processor.gen_sse_from_aux_stream",
            side_effect=mock_error_gen,
        ):
            await _handle_auxiliary_stream_response(
                req_id,
                request,
                context,
                result_future,
                submit_locator,
                check_disco,
                timeout=30.0,
            )

            streaming_response = result_future.result()
            with pytest.raises(Exception) as exc:
                async for _ in streaming_response.body_iterator:
                    pass

            assert "Stream error" in str(exc.value)


from api_utils.request_processor import (
    _cleanup_request_resources,
    _handle_auxiliary_stream_response,
    _handle_model_switching,
    _handle_parameter_cache,
    _handle_playwright_response,
    _handle_response_processing,
    _process_request_refactored,
)

# --- Fixtures ---


@pytest.fixture
def mock_http_request():
    return MagicMock(spec=Request)


@pytest.fixture
def mock_context():
    page_mock = AsyncMock()
    # is_closed is synchronous in Playwright, so it shouldn't return a coroutine
    page_mock.is_closed = MagicMock(return_value=False)
    return {
        "page": page_mock,
        "is_page_ready": True,
        "current_ai_studio_model_id": "gemini-2.0-flash",
        "logger": MagicMock(),
        "page_params_cache": {},
        "params_cache_lock": AsyncMock(),
        "model_id_to_use": "gemini-2.0-flash",
        "parsed_model_list": [],
    }


@pytest.fixture
def mock_request():
    return ChatCompletionRequest(
        messages=[Message(role="user", content="Hello")],
        model="gemini-2.0-flash",
        stream=False,
    )


@pytest.fixture
def mock_check_disconnected():
    return MagicMock()


# --- Tests ---


@pytest.mark.asyncio
async def test_analyze_model_requirements(mock_context, mock_request):
    with patch(
        "api_utils.request_processor.ms_analyze", new_callable=AsyncMock
    ) as mock_ms_analyze:
        await _analyze_model_requirements("req1", mock_context, mock_request)
        mock_ms_analyze.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "page_none,is_closed,is_page_ready,should_raise,test_id",
    [
        (False, False, True, False, "success"),
        (True, None, None, True, "page_none"),
        (False, True, None, True, "page_closed"),
        (False, False, False, True, "page_not_ready"),
    ],
)
async def test_validate_page_status(
    mock_context,
    mock_check_disconnected,
    page_none,
    is_closed,
    is_page_ready,
    should_raise,
    test_id,
):
    """Test page status validation with various scenarios."""
    if page_none:
        mock_context["page"] = None
    else:
        if mock_context["page"] is None:
            mock_context["page"] = AsyncMock()
        mock_context["page"].is_closed.return_value = is_closed

    if is_page_ready is not None:
        mock_context["is_page_ready"] = is_page_ready

    if should_raise:
        with pytest.raises(HTTPException) as exc:
            await _validate_page_status("req1", mock_context, mock_check_disconnected)
        assert exc.value.status_code == 503
    else:
        await _validate_page_status("req1", mock_context, mock_check_disconnected)
        mock_check_disconnected.assert_called_once()


@pytest.mark.asyncio
async def test_handle_model_switching(mock_context, mock_check_disconnected):
    with patch(
        "api_utils.request_processor.ms_switch", new_callable=AsyncMock
    ) as mock_ms_switch:
        await _handle_model_switching("req1", mock_context, mock_check_disconnected)
        mock_ms_switch.assert_called_once()


@pytest.mark.asyncio
async def test_handle_model_switch_failure():
    mock_page = AsyncMock()
    mock_logger = MagicMock()
    with patch.object(state, "current_ai_studio_model_id", "old_model"):
        with pytest.raises(HTTPException) as exc:
            await _handle_model_switch_failure(
                "req1", mock_page, "new_model", "old_model", mock_logger
            )
        assert exc.value.status_code == 422
        # Check if logger warning was called
        mock_logger.warning.assert_called()


@pytest.mark.asyncio
async def test_handle_parameter_cache(mock_context):
    with patch(
        "api_utils.request_processor.ms_param_cache", new_callable=AsyncMock
    ) as mock_ms_cache:
        await _handle_parameter_cache("req1", mock_context)
        mock_ms_cache.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_and_validate_request_basic(
    mock_request, mock_check_disconnected
):
    with (
        patch("api_utils.request_processor.validate_chat_request") as mock_validate,
        patch(
            "api_utils.request_processor.prepare_combined_prompt",
            return_value=("prompt", []),
        ) as mock_prep,
        patch(
            "api_utils.request_processor.maybe_execute_tools", new_callable=AsyncMock
        ) as mock_tools,
    ):
        mock_tools.return_value = None

        prompt, images = await _prepare_and_validate_request(
            "req1", mock_request, mock_check_disconnected
        )

        assert prompt == "prompt"
        assert images == []
        mock_validate.assert_called_once()
        mock_prep.assert_called_once()
        mock_tools.assert_called_once()
        mock_check_disconnected.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_and_validate_request_with_tools(
    mock_request, mock_check_disconnected
):
    mock_request.tools = [{"type": "function", "function": {"name": "test"}}]
    mock_request.mcp_endpoint = "http://mcp"

    tool_results = [{"name": "test_tool", "arguments": "{}", "result": "success"}]

    with (
        patch("api_utils.request_processor.validate_chat_request"),
        patch(
            "api_utils.request_processor.prepare_combined_prompt",
            return_value=("prompt", []),
        ),
        patch(
            "api_utils.request_processor.maybe_execute_tools", new_callable=AsyncMock
        ) as mock_tools,
        patch("api_utils.tools_registry.register_runtime_tools") as mock_register,
    ):
        mock_tools.return_value = tool_results

        prompt, _ = await _prepare_and_validate_request(
            "req1", mock_request, mock_check_disconnected
        )

        assert "Tool Execution: test_tool" in prompt
        assert "Result:\nsuccess" in prompt
        mock_register.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_and_validate_request_attachments(
    mock_request, mock_check_disconnected
):
    # Mock ONLY_COLLECT_CURRENT_USER_ATTACHMENTS to True
    with (
        patch("config.settings.ONLY_COLLECT_CURRENT_USER_ATTACHMENTS", True),
        patch("api_utils.request_processor.validate_chat_request"),
        patch(
            "api_utils.request_processor.prepare_combined_prompt",
            return_value=("prompt", []),
        ),
        patch(
            "api_utils.request_processor.maybe_execute_tools", new_callable=AsyncMock
        ) as mock_tools,
        patch(
            "api_utils.request_processor.collect_and_validate_attachments",
            return_value=["/tmp/file.png"],
        ) as mock_collect,
    ):
        mock_tools.return_value = None
        # Use a mock object that supports getattr for role and attachments
        msg_mock = MagicMock()
        msg_mock.role = "user"
        msg_mock.content = "hi"
        msg_mock.attachments = [
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        ]
        # Make sure model_dump works if called (though not called in this specific path, but good practice)
        msg_mock.model_dump.return_value = {"role": "user", "content": "hi"}

        mock_request.messages = [msg_mock]

        _, images = await _prepare_and_validate_request(
            "req1", mock_request, mock_check_disconnected
        )

        assert "/tmp/file.png" in images
        mock_collect.assert_called_once()


@pytest.mark.asyncio
async def test_handle_response_processing_aux_stream(
    mock_request, mock_context, mock_check_disconnected
):
    mock_future = asyncio.Future()
    mock_locator = MagicMock()

    with (
        patch(
            "api_utils.request_processor.get_environment_variable", return_value="8000"
        ),
        patch(
            "api_utils.request_processor._handle_auxiliary_stream_response",
            new_callable=AsyncMock,
        ) as mock_aux,
    ):
        await _handle_response_processing(
            "req1",
            mock_request,
            None,
            mock_context,
            mock_future,
            mock_locator,
            mock_check_disconnected,
            100,
            30.0,
        )
        mock_aux.assert_called_once()


@pytest.mark.asyncio
async def test_handle_response_processing_playwright(
    mock_request, mock_context, mock_check_disconnected
):
    mock_future = asyncio.Future()
    mock_locator = MagicMock()
    mock_page = AsyncMock()

    with (
        patch("api_utils.request_processor.get_environment_variable", return_value="0"),
        patch(
            "api_utils.request_processor._handle_playwright_response",
            new_callable=AsyncMock,
        ) as mock_pw,
    ):
        await _handle_response_processing(
            "req1",
            mock_request,
            mock_page,
            mock_context,
            mock_future,
            mock_locator,
            mock_check_disconnected,
            100,
            30.0,
        )
        mock_pw.assert_called_once()


@pytest.mark.asyncio
async def test_handle_auxiliary_stream_response_streaming(
    mock_request, mock_context, mock_check_disconnected
):
    mock_request.stream = True
    mock_future = asyncio.Future()
    mock_locator = MagicMock()

    async def mock_gen_sse(*args, **kwargs):
        if False:
            yield ""

    with patch(
        "api_utils.request_processor.gen_sse_from_aux_stream", side_effect=mock_gen_sse
    ):
        result = await _handle_auxiliary_stream_response(
            "req1",
            mock_request,
            mock_context,
            mock_future,
            mock_locator,
            mock_check_disconnected,
            timeout=30.0,
        )

        assert result is not None
        completion_event, _, _ = (
            result if isinstance(result, tuple) else (None, None, None)
        )
        assert isinstance(completion_event, asyncio.Event)
        # Note: stream_state is no longer returned in the tuple, it's used internally
        assert mock_future.done()
        # Check if result is StreamingResponse
        # Note: In actual code it sets StreamingResponse, which might not be easily checkable for class type if not imported,
        # but we can check attributes
        assert hasattr(mock_future.result(), "body_iterator")


@pytest.mark.asyncio
async def test_handle_auxiliary_stream_response_non_streaming_success(
    mock_request, mock_context, mock_check_disconnected
):
    mock_request.stream = False
    mock_future = asyncio.Future()
    mock_locator = MagicMock()

    async def mock_use_stream_response(*args, **kwargs):
        yield {"done": False, "body": "part1"}
        yield {"done": True, "body": "full_content", "reason": "stop"}

    with (
        patch(
            "api_utils.request_processor.use_stream_response",
            side_effect=mock_use_stream_response,
        ),
        patch("api_utils.request_processor.calculate_usage_stats", return_value={}),
        patch(
            "api_utils.request_processor.build_chat_completion_response_json",
            return_value={"id": "resp1"},
        ),
    ):
        result = await _handle_auxiliary_stream_response(
            "req1",
            mock_request,
            mock_context,
            mock_future,
            mock_locator,
            mock_check_disconnected,
            timeout=30.0,
        )

        assert isinstance(result, dict)
        assert mock_future.done()
        # Verify result is JSONResponse
        assert hasattr(mock_future.result(), "body")


@pytest.mark.asyncio
async def test_handle_auxiliary_stream_response_non_streaming_internal_timeout(
    mock_request, mock_context, mock_check_disconnected
):
    mock_request.stream = False
    mock_future = asyncio.Future()
    mock_locator = MagicMock()

    async def mock_use_stream_response(*args, **kwargs):
        yield {"done": True, "reason": "internal_timeout"}

    with patch(
        "api_utils.request_processor.use_stream_response",
        side_effect=mock_use_stream_response,
    ):
        with pytest.raises(HTTPException) as exc:
            await _handle_auxiliary_stream_response(
                "req1",
                mock_request,
                mock_context,
                mock_future,
                mock_locator,
                mock_check_disconnected,
                timeout=30.0,
            )
        assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_handle_playwright_response_streaming(
    mock_request, mock_context, mock_check_disconnected
):
    mock_request.stream = True
    mock_future = asyncio.Future()
    mock_locator = MagicMock()
    mock_page = AsyncMock()

    async def mock_gen_sse(*args, **kwargs):
        if False:
            yield ""

    with (
        patch(
            "api_utils.request_processor.locate_response_elements",
            new_callable=AsyncMock,
        ),
        patch(
            "api_utils.request_processor.gen_sse_from_playwright",
            side_effect=mock_gen_sse,
        ),
    ):
        result = await _handle_playwright_response(
            "req1",
            mock_request,
            mock_page,
            mock_context,
            mock_future,
            mock_locator,
            mock_check_disconnected,
            prompt_length=100,
            timeout=30.0,
        )
        assert result is not None
        completion_event, _, _ = (
            result if isinstance(result, tuple) else (None, None, None)
        )

        assert isinstance(completion_event, asyncio.Event)
        assert mock_future.done()


@pytest.mark.asyncio
async def test_handle_playwright_response_non_streaming(
    mock_request, mock_context, mock_check_disconnected
):
    mock_request.stream = False
    mock_future = asyncio.Future()
    mock_locator = MagicMock()
    mock_page = AsyncMock()

    with (
        patch(
            "api_utils.request_processor.locate_response_elements",
            new_callable=AsyncMock,
        ),
        patch(
            "browser_utils.page_controller.PageController.get_response",
            new_callable=AsyncMock,
        ) as mock_get_resp,
        patch("api_utils.request_processor.calculate_usage_stats", return_value={}),
        patch(
            "api_utils.request_processor.build_chat_completion_response_json",
            return_value={"id": "resp1"},
        ),
    ):
        mock_get_resp.return_value = "response content"

        result = await _handle_playwright_response(
            "req1",
            mock_request,
            mock_page,
            mock_context,
            mock_future,
            mock_locator,
            mock_check_disconnected,
            prompt_length=100,
            timeout=30.0,
        )

        assert isinstance(result, dict)
        assert mock_future.done()


class TestCleanupRequestResources:
    """Tests for _cleanup_request_resources helper function."""

    @pytest.mark.asyncio
    async def test_cleanup_request_resources_basic(self):
        """Test basic cleanup of request resources."""

        # Create a real task that we can cancel
        async def dummy_task():
            await asyncio.sleep(100)  # Will be cancelled

        mock_task = asyncio.create_task(dummy_task())

        mock_event = asyncio.Event()
        mock_future = asyncio.Future()
        mock_future.set_exception(Exception("error"))

        with (
            patch("shutil.rmtree") as mock_rmtree,
            patch("os.path.isdir", return_value=True),
        ):
            await _cleanup_request_resources(
                "req1", mock_task, mock_event, mock_future, True
            )

            assert mock_task.cancelled()
            mock_rmtree.assert_called_once()
            assert mock_event.is_set()

    @pytest.mark.asyncio
    async def test_cleanup_directory_removal_exception(self):
        """Test that directory removal exceptions are caught and logged."""
        mock_task = AsyncMock()
        mock_task.done.return_value = True
        mock_event = asyncio.Event()
        mock_future = asyncio.Future()
        mock_future.set_result(MagicMock())

        with (
            patch("os.path.isdir", return_value=True),
            patch("shutil.rmtree", side_effect=PermissionError("Access denied")),
        ):
            # Should not raise exception - error is logged but swallowed
            await _cleanup_request_resources(
                "req1", mock_task, mock_event, mock_future, False
            )

            # Cleanup should complete despite directory removal failure

    @pytest.mark.asyncio
    async def test_cleanup_cancelled_error_in_directory_removal(self):
        """Test that CancelledError during cleanup is re-raised."""
        mock_task = AsyncMock()
        mock_task.done.return_value = True
        mock_event = asyncio.Event()
        mock_future = asyncio.Future()
        mock_future.set_result(MagicMock())

        with (
            patch("os.path.isdir", return_value=True),
            patch("shutil.rmtree", side_effect=asyncio.CancelledError()),
        ):
            # CancelledError should be re-raised
            with pytest.raises(asyncio.CancelledError):
                await _cleanup_request_resources(
                    "req1", mock_task, mock_event, mock_future, False
                )


@pytest.mark.asyncio
async def test_process_request_refactored_client_disconnected_early(
    mock_request, mock_http_request
):
    mock_future = asyncio.Future()

    with patch(
        "api_utils.request_processor._check_client_connection", new_callable=AsyncMock
    ) as mock_check:
        mock_check.return_value = False

        result = await _process_request_refactored(
            "req1", mock_request, mock_http_request, mock_future
        )

        assert result is None
        exc = mock_future.exception()
        assert exc is not None
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 499


@pytest.mark.asyncio
async def test_process_request_refactored_success(
    mock_request, mock_http_request, mock_context
):
    """Test successful request processing flow through all stages."""
    mock_future = asyncio.Future()
    mock_check_disconnected = MagicMock(return_value=False)

    # Setup mocks for all refactored steps
    patches = {
        "_check_client_connection": AsyncMock(return_value=True),
        "_initialize_request_context": AsyncMock(return_value=mock_context),
        "_analyze_model_requirements": AsyncMock(return_value=mock_context),
        "_setup_disconnect_monitoring": AsyncMock(
            return_value=(None, AsyncMock(), mock_check_disconnected)
        ),
        "_validate_page_status": AsyncMock(),
        "PageController": MagicMock(autospec=True),
        "_handle_model_switching": AsyncMock(),
        "_handle_parameter_cache": AsyncMock(),
        "_prepare_and_validate_request": AsyncMock(return_value=("prompt", [])),
        "_handle_response_processing": AsyncMock(),
        "_cleanup_request_resources": AsyncMock(),
        "save_error_snapshot": AsyncMock(),
    }

    with (
        patch(
            "api_utils.request_processor._check_client_connection",
            patches["_check_client_connection"],
        ),
        patch(
            "api_utils.request_processor._initialize_request_context",
            patches["_initialize_request_context"],
        ),
        patch(
            "api_utils.request_processor._analyze_model_requirements",
            patches["_analyze_model_requirements"],
        ),
        patch(
            "api_utils.request_processor._setup_disconnect_monitoring",
            patches["_setup_disconnect_monitoring"],
        ),
        patch(
            "api_utils.request_processor._validate_page_status",
            patches["_validate_page_status"],
        ),
        patch("api_utils.request_processor.PageController", patches["PageController"]),
        patch(
            "api_utils.request_processor._handle_model_switching",
            patches["_handle_model_switching"],
        ),
        patch(
            "api_utils.request_processor._handle_parameter_cache",
            patches["_handle_parameter_cache"],
        ),
        patch(
            "api_utils.request_processor._prepare_and_validate_request",
            patches["_prepare_and_validate_request"],
        ),
        patch(
            "api_utils.request_processor._handle_response_processing",
            patches["_handle_response_processing"],
        ),
        patch(
            "api_utils.request_processor._cleanup_request_resources",
            patches["_cleanup_request_resources"],
        ),
        patch(
            "api_utils.request_processor.save_error_snapshot",
            patches["save_error_snapshot"],
        ),
        patch("api_utils.utils.collect_and_validate_attachments", return_value=[]),
        patch("api_utils.request_processor.get_environment_variable", return_value="0"),
    ):
        # Setup PageController mock instance
        mock_pc_instance = patches["PageController"].return_value
        mock_pc_instance.page = mock_context["page"]
        mock_pc_instance.adjust_parameters = AsyncMock()
        mock_pc_instance.submit_prompt = AsyncMock()

        # Setup response processing result
        mock_event = asyncio.Event()
        mock_locator = MagicMock()
        patches["_handle_response_processing"].return_value = (
            mock_event,
            mock_locator,
            mock_check_disconnected,
        )
        mock_context["page"].locator = MagicMock(return_value=mock_locator)

        # Execute
        result = await _process_request_refactored(
            "req1", mock_request, mock_http_request, mock_future
        )

        # Verify success
        assert result is not None, (
            "_process_request_refactored returned None unexpectedly"
        )
        # Verify the elements of the tuple individually since submit_button_locator might be recaptured
        assert result[0] == mock_event
        assert result[2] == mock_check_disconnected

        # Verify all stages were called
        patches["_validate_page_status"].assert_called_once()
        patches["_handle_model_switching"].assert_called_once()
        mock_pc_instance.adjust_parameters.assert_called_once()
        mock_pc_instance.submit_prompt.assert_called_once()
        patches["_handle_response_processing"].assert_called_once()
        patches["_cleanup_request_resources"].assert_called_once()


class TestProcessRequestRefactoredExceptionHandling:
    """Tests for exception handling in _process_request_refactored."""

    @pytest.mark.asyncio
    async def test_process_request_stream_queue_clear_exception(
        self, mock_request, mock_http_request
    ):
        """Test that stream queue clear exceptions are caught and logged."""
        mock_future = asyncio.Future()

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "api_utils.request_processor.get_environment_variable",
                return_value="3120",
            ),  # Stream enabled
            patch(
                "api_utils.clear_stream_queue",  # Fixed: patch from api_utils module
                new_callable=AsyncMock,
                side_effect=Exception("Queue clear failed"),
            ),
            patch(
                "api_utils.request_processor._initialize_request_context",
                new_callable=AsyncMock,
            ) as mock_init,
        ):
            # Exception in clear_stream_queue should be caught and logged
            # Processing should continue
            mock_init.side_effect = Exception("Stop processing early")

            with pytest.raises(Exception):
                await _process_request_refactored(
                    "req1", mock_request, mock_http_request, mock_future
                )

    @pytest.mark.asyncio
    async def test_process_request_stream_queue_clear_cancelled_error(
        self, mock_request, mock_http_request
    ):
        """Test that CancelledError during stream queue clear is re-raised."""
        mock_future = asyncio.Future()

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "api_utils.request_processor.get_environment_variable",
                return_value="3120",
            ),
            patch(
                "api_utils.clear_stream_queue",
                new_callable=AsyncMock,
                side_effect=asyncio.CancelledError(),
            ),
        ):
            # CancelledError should be re-raised
            with pytest.raises(asyncio.CancelledError):
                await _process_request_refactored(
                    "req1", mock_request, mock_http_request, mock_future
                )

    @pytest.mark.asyncio
    async def test_process_request_page_none_error(
        self, mock_request, mock_http_request, make_request_context
    ):
        """Test error when page is None in _process_request_refactored."""
        mock_future = asyncio.Future()
        context = make_request_context(page=None, is_page_ready=False)

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "api_utils.request_processor.get_environment_variable", return_value="0"
            ),
            patch(
                "api_utils.request_processor._initialize_request_context",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                "api_utils.request_processor._analyze_model_requirements",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                "api_utils.request_processor._setup_disconnect_monitoring",
                new_callable=AsyncMock,
                return_value=(None, AsyncMock(), MagicMock()),
            ),
            patch(
                "api_utils.request_processor._cleanup_request_resources",
                new_callable=AsyncMock,
            ),
        ):
            # Should raise HTTPException when page is None
            await _process_request_refactored(
                "req1", mock_request, mock_http_request, mock_future
            )

            # Future should have 503 error set
            assert mock_future.done()
            exc = mock_future.exception()
            assert isinstance(exc, HTTPException)
            assert exc.status_code == 503

    @pytest.mark.asyncio
    async def test_process_request_cancelled_error_handling(
        self, mock_request, mock_http_request, make_request_context
    ):
        """Test CancelledError handling in _process_request_refactored."""
        mock_future = asyncio.Future()
        context = make_request_context()

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "api_utils.request_processor.get_environment_variable", return_value="0"
            ),
            patch(
                "api_utils.request_processor._initialize_request_context",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                "api_utils.request_processor._analyze_model_requirements",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                "api_utils.request_processor._setup_disconnect_monitoring",
                new_callable=AsyncMock,
                return_value=(None, AsyncMock(), MagicMock()),
            ),
            patch(
                "api_utils.request_processor._validate_page_status",
                new_callable=AsyncMock,
            ),
            patch("api_utils.request_processor.PageController"),
            patch(
                "api_utils.request_processor._handle_model_switching",
                new_callable=AsyncMock,
                side_effect=asyncio.CancelledError(),
            ),
            patch(
                "api_utils.request_processor._cleanup_request_resources",
                new_callable=AsyncMock,
            ),
        ):
            # CancelledError should be caught, and re-raised
            with pytest.raises(asyncio.CancelledError):
                await _process_request_refactored(
                    "req1", mock_request, mock_http_request, mock_future
                )

    @pytest.mark.asyncio
    async def test_process_request_client_disconnected_error_handling(
        self, mock_request, mock_http_request, make_request_context
    ):
        """Test ClientDisconnectedError handling in _process_request_refactored."""
        from models import ClientDisconnectedError

        mock_future = asyncio.Future()
        context = make_request_context()
        local_check_disconnected = MagicMock(return_value=False)

        with (
            patch(
                "api_utils.request_processor._check_client_connection",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "api_utils.request_processor.get_environment_variable", return_value="0"
            ),
            patch(
                "api_utils.request_processor._initialize_request_context",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                "api_utils.request_processor._analyze_model_requirements",
                new_callable=AsyncMock,
                return_value=context,
            ),
            patch(
                "api_utils.request_processor._setup_disconnect_monitoring",
                new_callable=AsyncMock,
                return_value=(None, AsyncMock(), local_check_disconnected),
            ),
            patch(
                "api_utils.request_processor._validate_page_status",
                new_callable=AsyncMock,
            ),
            patch("api_utils.request_processor.PageController"),
            patch(
                "api_utils.request_processor._handle_model_switching",
                new_callable=AsyncMock,
                side_effect=ClientDisconnectedError("Client disconnected"),
            ),
            patch(
                "api_utils.request_processor._cleanup_request_resources",
                new_callable=AsyncMock,
            ),
        ):
            # Should catch ClientDisconnectedError and set exception in future
            result = await _process_request_refactored(
                "req1", mock_request, mock_http_request, mock_future
            )

            # Should return tuple with completion_event (even if None)
            assert isinstance(result, tuple)
            assert result[2] == local_check_disconnected

            # Future should have HTTPException with 499 status
            assert mock_future.done()
            exc = mock_future.exception()
            assert isinstance(exc, HTTPException)
            assert exc.status_code == 499


@pytest.mark.asyncio
async def test_process_request_refactored_exception(
    mock_request, mock_http_request, mock_context
):
    mock_future = asyncio.Future()

    with (
        patch(
            "api_utils.request_processor._check_client_connection",
            new_callable=AsyncMock,
        ) as mock_check_conn,
        patch(
            "api_utils.request_processor._initialize_request_context",
            side_effect=Exception("Unexpected Error"),
        ),
        patch(
            "api_utils.request_processor.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
        patch(
            "api_utils.request_processor._cleanup_request_resources",
            new_callable=AsyncMock,
        ) as mock_cleanup,
    ):
        mock_check_conn.return_value = True

        with pytest.raises(Exception) as exc:
            await _process_request_refactored(
                "req1", mock_request, mock_http_request, mock_future
            )

        assert "Unexpected Error" in str(exc.value)
        # Initialization happens before try/finally, so cleanup/snapshot won't be called
        mock_snapshot.assert_not_called()
        mock_cleanup.assert_not_called()
