from typing import Any, Dict, List, cast
from unittest.mock import AsyncMock, patch

import pytest

from api_utils.utils import (
    _extract_json_from_text,
    _get_latest_user_text,
    collect_and_validate_attachments,
    generate_sse_stop_chunk_with_usage,
    maybe_execute_tools,
    prepare_combined_prompt,
)
from models import FunctionCall, Message, MessageContentItem, ToolCall


@pytest.fixture
def mock_tools_registry():
    with (
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools") as mock_reg,
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
    ):
        yield mock_reg, mock_exec


@pytest.fixture
def mock_logger():
    with patch("logging.getLogger") as mock:
        yield mock.return_value


@pytest.fixture
def mock_file_utils():
    """Fixture providing mocked file utility functions for cross-platform testing."""
    with (
        patch("api_utils.utils_ext.files.extract_data_url_to_local") as mock_extract,
        patch("api_utils.utils_ext.files.save_blob_to_local") as mock_save,
        # Patch exists globally to avoid conflicts between multiple module-level patches
        patch("os.path.exists") as mock_exists,
        patch(
            "api_utils.utils_ext.prompts.extract_data_url_to_local"
        ) as mock_extract_prompts,
        patch("api_utils.utils_ext.prompts.save_blob_to_local") as mock_save_prompts,
    ):
        # Configure all mocks to behave consistently
        mock_exists.return_value = True

        # Link prompts mocks to files mocks
        mock_extract_prompts.side_effect = lambda *args, **kwargs: mock_extract(
            *args, **kwargs
        )
        mock_save_prompts.side_effect = lambda *args, **kwargs: mock_save(
            *args, **kwargs
        )

        yield mock_extract, mock_save, mock_exists


def test_prepare_combined_prompt_basic(mock_logger):
    """Test basic text message formatting."""
    messages = [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi there"),
    ]
    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "User:\nHello" in prompt
    assert "Assistant:\nHi there" in prompt
    assert len(files) == 0


def test_prepare_combined_prompt_system(mock_logger):
    """Test system prompt handling."""
    messages = [
        Message(role="system", content="Be helpful"),
        Message(role="user", content="Hi"),
    ]
    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "System Instructions:\nBe helpful" in prompt
    assert "User:\nHi" in prompt
    # System message should not be repeated in conversation history if processed
    assert prompt.count("Be helpful") == 1


def test_prepare_combined_prompt_tools(mock_logger):
    """Test tool definitions injection."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object"},
            },
        }
    ]
    messages = [Message(role="user", content="Weather?")]

    prompt, files = prepare_combined_prompt(
        messages, "req1", tools=tools, tool_choice="auto"
    )

    assert "Available Tools Catalog:" in prompt
    assert "- Function: get_weather" in prompt
    assert "Parameter Schema:" in prompt


def test_prepare_combined_prompt_multimodal_image(mock_file_utils, mock_logger):
    """Test image url processing."""
    mock_extract, _, _ = mock_file_utils
    mock_extract.return_value = "/tmp/image.png"

    # Use dicts for Pydantic parsing
    content_item = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,...", "detail": "high"},
    }

    messages = [
        Message(role="user", content=cast(List[MessageContentItem], [content_item]))
    ]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/tmp/image.png" in files
    assert "[Image Details: detail=high]" in prompt


def test_prepare_combined_prompt_multimodal_dict(mock_file_utils, mock_logger):
    """Test dictionary content processing."""
    mock_extract, _, _ = mock_file_utils
    mock_extract.return_value = "/tmp/image.png"

    content = [
        {"type": "text", "text": "Look at this"},
        {"type": "image_url", "image_url": {"url": "data:image...", "detail": "low"}},
    ]

    messages = [Message(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "Look at this" in prompt
    assert "/tmp/image.png" in files
    assert "[Image Details: detail=low]" in prompt


def test_prepare_combined_prompt_audio(mock_file_utils, mock_logger):
    """Test audio input processing."""
    _, mock_save, _ = mock_file_utils
    mock_save.return_value = "/tmp/audio.mp3"

    content_item = {
        "type": "input_audio",
        "input_audio": {
            "data": "SGVsbG8=",  # Valid base64 "Hello"
            "mime_type": "audio/mp3",
        },
    }

    messages = [
        Message(role="user", content=cast(List[MessageContentItem], [content_item]))
    ]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/tmp/audio.mp3" in files


def test_prepare_combined_prompt_tool_calls(mock_logger):
    """Test tool call visualization."""
    tool_call = ToolCall(
        id="call1",
        type="function",
        function=FunctionCall(name="get_weather", arguments='{"city": "Paris"}'),
    )

    messages = [Message(role="assistant", content=None, tool_calls=[tool_call])]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "Request function call: get_weather" in prompt
    assert '"city": "Paris"' in prompt


def test_prepare_combined_prompt_tool_results(mock_logger):
    """Test tool result inclusion."""
    messages = [Message(role="tool", content="Sunny", tool_call_id="call1")]

    prompt, _ = prepare_combined_prompt(messages, "req1")

    assert "Tool result (tool_call_id=call1):" in prompt
    assert "Sunny" in prompt


def test_extract_json_from_text():
    """Test JSON extraction from text."""
    text = 'Here is some json: {"key": "value"} end.'
    result = _extract_json_from_text(text)
    assert result == '{"key": "value"}'

    text_no_json = "Just text"
    assert _extract_json_from_text(text_no_json) is None

    text_invalid = "Bad json { key: value }"
    assert _extract_json_from_text(text_invalid) is None


def test_get_latest_user_text():
    """Test extracting latest user text."""
    messages = [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi"),
        Message(role="user", content="World"),
    ]
    assert _get_latest_user_text(messages) == "World"

    # Test with list content
    content = [{"type": "text", "text": "Part1"}, {"type": "text", "text": "Part2"}]
    messages = [Message(role="user", content=cast(List[MessageContentItem], content))]
    assert _get_latest_user_text(messages) == "Part1\nPart2"


@pytest.mark.asyncio
async def test_maybe_execute_tools(mock_tools_registry, mock_logger):
    """Test explicit tool execution logic."""
    _, mock_exec = mock_tools_registry
    mock_exec.return_value = "success"

    tools = [{"type": "function", "function": {"name": "test_func"}}]
    tool_choice = {"type": "function", "function": {"name": "test_func"}}

    messages = [Message(role="user", content='Call test_func with {"arg": 1}')]

    results = await maybe_execute_tools(messages, tools, tool_choice)

    assert results is not None
    assert len(results) == 1
    assert results[0]["name"] == "test_func"
    assert results[0]["result"] == "success"

    # Verify arguments extraction (simple JSON in text)
    # The current implementation of maybe_execute_tools tries to find JSON in user text
    mock_exec.assert_called_once()
    call_args = mock_exec.call_args[0]  # (name, args, tool_def)
    assert call_args[0] == "test_func"
    assert call_args[1] == '{"arg": 1}'  # It passes the extracted JSON string


def test_collect_and_validate_attachments(mock_file_utils, mock_logger):
    """Test attachment collection and validation."""
    mock_extract, _, mock_exists = mock_file_utils
    mock_exists.return_value = True
    mock_extract.return_value = "/tmp/data.png"

    # Mock request object
    class MockMessage:
        def __init__(self, role, content, attachments=None):
            self.role = role
            self.content = content
            self.attachments = attachments or []

    class MockRequest:
        attachments = ["/tmp/existing.png", {"url": "data:image/png..."}]
        messages = [
            MockMessage(role="user", content="text", attachments=["/tmp/msg_att.png"])
        ]

    req = MockRequest()
    initial_list = ["/tmp/initial.png"]

    result = collect_and_validate_attachments(req, "req1", initial_list)

    assert "/tmp/initial.png" in result
    assert "/tmp/existing.png" in result
    assert "/tmp/data.png" in result
    assert "/tmp/msg_att.png" in result


def test_generate_sse_stop_chunk_with_usage():
    """Test SSE stop chunk generation with usage."""
    with patch("api_utils.utils.generate_sse_stop_chunk") as mock_gen:
        mock_gen.return_value = "SSE_CHUNK"
        res = generate_sse_stop_chunk_with_usage("req1", "model", {"tokens": 10})
        assert res == "SSE_CHUNK"
        mock_gen.assert_called_with("req1", "model", "stop", {"tokens": 10})


def test_prepare_combined_prompt_complex_dict(mock_file_utils, mock_logger):
    """Test complex dictionary with attachments."""
    mock_extract, _, _ = mock_file_utils
    mock_extract.return_value = "/tmp/file.pdf"

    content = {
        "text": "Analyze this",
        "attachments": [{"url": "data:application/pdf..."}],
    }

    # Use model_construct to bypass validation for test purposes if needed,
    # or ensure content structure matches what Pydantic expects if possible.
    # Given the utils.py code handles dict content, we bypass Pydantic check here.
    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "Analyze this" in prompt
    assert "/tmp/file.pdf" in files


def test_prepare_combined_prompt_local_files(mock_file_utils, mock_logger):
    """Test local file paths."""
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    content = [{"type": "image_url", "image_url": {"url": "file:///c:/test.png"}}]

    messages = [Message(role="user", content=cast(List[MessageContentItem], content))]

    prompt, files = prepare_combined_prompt(messages, "req1")

    # URL decoding might happen, on windows /c:/test.png -> /c:/test.png or c:\test.png
    # The code uses unquote(parsed.path)
    # file:///c:/test.png -> path is /c:/test.png
    assert len(files) == 1
    assert files[0].endswith("test.png")


def test_prepare_combined_prompt_system_message_ordering(mock_logger):
    """Test that system messages are processed and placed correctly."""
    messages = [
        Message(role="user", content="User 1"),
        Message(role="system", content="System 1"),
        Message(role="assistant", content="Assistant 1"),
        Message(role="system", content="System 2"),
    ]
    prompt, _ = prepare_combined_prompt(messages, "req1")

    # Based on utils.py:
    # 1. Finds first system message ("System 1") and uses it.
    # 2. Skips subsequent system messages ("System 2").

    assert "User:\nUser 1" in prompt
    assert "System Instructions:\nSystem 1" in prompt
    assert "Assistant:\nAssistant 1" in prompt

    # System 2 should be skipped
    assert "System 2" not in prompt

    # Check ordering
    # System prompt is prepended to the first message usually or handled separately
    # In utils.py, it is added to combined_parts BEFORE iterating other messages.
    # So "System 1" should appear before "User 1"

    idx_s1 = prompt.find("System Instructions:\nSystem 1")
    idx_u1 = prompt.find("User:\nUser 1")
    idx_a1 = prompt.find("Assistant:\nAssistant 1")

    assert idx_s1 < idx_u1
    assert idx_u1 < idx_a1


def test_prepare_combined_prompt_complex_attachments_url_schemes(
    mock_file_utils, mock_logger
):
    """Test various URL schemes in attachments."""
    mock_extract, _, mock_exists = mock_file_utils
    mock_exists.return_value = True
    mock_extract.side_effect = lambda url, **kwargs: f"/tmp/{url.split('/')[-1]}"

    content = {
        "text": "Check these",
        "attachments": [
            {"url": "http://example.com/http.pdf"},
            {"url": "https://example.com/https.jpg"},
            {"url": "file:///c:/local.txt"},
        ],
    }

    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    # utils.py ignores http/https for attachments, only takes data:, file:, or absolute paths
    assert len(files) == 1

    # file:///c:/local.txt -> unquoted path.
    local_file_found = any("local.txt" in f for f in files)
    assert local_file_found


def test_prepare_combined_prompt_input_audio_data_url(mock_file_utils, mock_logger):
    """Test input audio with data URL."""
    mock_extract, mock_save, _ = mock_file_utils
    # utils.py uses extract_data_url_to_local for data: URLs
    mock_extract.return_value = "/tmp/audio_data.mp3"

    content_item = {
        "type": "input_audio",
        "input_audio": {"data": "data:audio/mp3;base64,SGVsbG8=", "format": "mp3"},
    }

    messages = [
        Message(role="user", content=cast(List[MessageContentItem], [content_item]))
    ]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/tmp/audio_data.mp3" in files


def test_prepare_combined_prompt_input_video_processing(mock_file_utils, mock_logger):
    """Test input video processing with various formats."""
    mock_extract, mock_save, mock_exists = mock_file_utils
    mock_exists.return_value = True

    # 1. Video URL (data:)
    mock_extract.return_value = "/tmp/video1.mp4"
    item1 = {
        "type": "input_video",
        "input_video": {"url": "data:video/mp4;base64,AAAA"},
    }

    # 2. Video raw base64 data
    mock_save.return_value = "/tmp/video2.mp4"
    item2 = {
        "type": "input_video",
        "input_video": {
            "data": "BBBB",  # Raw base64
            "mime_type": "video/mp4",
            "format": "mp4",
        },
    }

    # 3. Local file URL
    item3 = {"type": "input_video", "input_video": {"url": "file:///c:/video3.mp4"}}

    messages = [
        Message(
            role="user", content=cast(List[MessageContentItem], [item1, item2, item3])
        )
    ]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/tmp/video1.mp4" in files
    assert "/tmp/video2.mp4" in files
    # file:///c:/video3.mp4 -> /c:/video3.mp4 (unquoted)
    # Windows path handling in test environment might vary, checking endswith
    assert any(f.endswith("video3.mp4") for f in files)

    # Check that extract and save were called
    mock_extract.assert_called()
    mock_save.assert_called()


def test_prepare_combined_prompt_complex_nested_dict(
    mock_file_utils, mock_logger, tmp_path
):
    """Test nested dictionary content with specific attachment keys.

    Uses platform-appropriate paths via tmp_path fixture for cross-platform compatibility.
    """
    mock_extract, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    # Create actual temp files for cross-platform path handling
    img_file = tmp_path / "img1.png"
    doc_file = tmp_path / "doc1.pdf"
    img_file.touch()
    doc_file.touch()

    content = {
        "text": "Look at these files",
        "images": [{"url": f"file://{img_file}"}],  # Platform-appropriate file URL
        "files": [{"path": str(doc_file)}],  # Platform-appropriate absolute path
        "media": [{"url": "data:video..."}],  # data url
    }

    mock_extract.return_value = str(tmp_path / "media.mp4")

    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "Look at these files" in prompt
    assert str(tmp_path / "media.mp4") in files
    assert any(f.endswith("img1.png") for f in files)
    assert any(f.endswith("doc1.pdf") for f in files)


@pytest.mark.asyncio
async def test_maybe_execute_tools_choice_logic(mock_tools_registry, mock_logger):
    """Test tool_choice logic (none, auto, specific)."""
    _, mock_exec = mock_tools_registry

    tools = [{"type": "function", "function": {"name": "func1"}}]
    messages = [Message(role="user", content="call func1")]

    # 1. Choice = 'none' -> returns None
    res = await maybe_execute_tools(messages, tools, "none")
    assert res is None

    # 2. Choice = 'auto' with 1 tool -> executes
    messages_with_json = [Message(role="user", content='call func1 {"arg": 1}')]

    mock_exec.return_value = "res1"
    res = await maybe_execute_tools(messages_with_json, tools, "auto")
    assert res is not None
    assert res[0]["name"] == "func1"

    # 3. Choice = specific name
    res = await maybe_execute_tools(messages_with_json, tools, "func1")
    assert res is not None
    assert res[0]["name"] == "func1"

    # 4. Choice = dict
    res = await maybe_execute_tools(
        messages_with_json, tools, {"type": "function", "function": {"name": "func1"}}
    )
    assert res is not None
    assert res[0]["name"] == "func1"


def test_collect_and_validate_attachments_error_handling(mock_file_utils, mock_logger):
    """Test error handling in attachment collection."""

    # Force an error during property access or iteration
    class BrokenMessage:
        @property
        def attachments(self):
            raise ValueError("Broken")

    class MockRequest:
        messages = [BrokenMessage()]

    initial_list = []
    # Should not raise exception, just log warning
    result = collect_and_validate_attachments(MockRequest(), "req1", initial_list)
    assert result == []


def test_prepare_combined_prompt_tool_result_list_content(mock_logger):
    """Test tool result with list content."""
    content = [{"type": "text", "text": "Result Part 1"}, "Result Part 2"]
    # Use model_construct to bypass strict Pydantic validation for mixed content types
    messages = [
        Message.model_construct(role="tool", content=content, tool_call_id="call1")
    ]

    prompt, _ = prepare_combined_prompt(messages, "req1")

    assert "Result Part 1" in prompt
    assert "Result Part 2" in prompt


def test_prepare_combined_prompt_malformed_tool_args(mock_logger):
    """Test malformed JSON in tool call arguments."""
    tool_call = ToolCall(
        id="call1",
        type="function",
        function=FunctionCall(name="func1", arguments="{bad_json"),
    )
    messages = [Message(role="assistant", content=None, tool_calls=[tool_call])]

    prompt, _ = prepare_combined_prompt(messages, "req1")

    # Should fall back to raw string
    assert "{bad_json" in prompt


def test_prepare_combined_prompt_unknown_content_type(mock_logger):
    """Test unknown content type warning."""

    class UnknownType:
        def __str__(self):
            return "UnknownObj"

    # Bypass Pydantic validation
    messages = [Message.model_construct(role="user", content=UnknownType())]

    prompt, _ = prepare_combined_prompt(messages, "req1")

    assert "UnknownObj" in prompt


def test_prepare_combined_prompt_invalid_base64(mock_file_utils, mock_logger):
    """Test invalid base64 in audio/video input."""
    _, mock_save, _ = mock_file_utils
    mock_save.return_value = None

    item = {
        "type": "input_audio",
        "input_audio": {"data": "InvalidBase64!!!", "mime_type": "audio/mp3"},
    }

    messages = [Message(role="user", content=cast(List[MessageContentItem], [item]))]

    # Should not crash, just ignore or log error
    prompt, files = prepare_combined_prompt(messages, "req1")

    assert len(files) == 0


@pytest.mark.asyncio
async def test_maybe_execute_tools_existing_tool_message(
    mock_tools_registry, mock_logger
):
    """Test maybe_execute_tools returns None if tool result already exists."""
    messages = [
        Message(role="user", content="call func"),
        Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="1",
                    type="function",
                    function=FunctionCall(name="f", arguments="{}"),
                )
            ],
        ),
        Message(role="tool", content="result", tool_call_id="1"),
    ]

    res = await maybe_execute_tools(messages, [], "auto")
    assert res is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_no_choice(mock_tools_registry, mock_logger):
    """Test maybe_execute_tools returns None if tool_choice is None."""
    messages = [Message(role="user", content="call func")]
    res = await maybe_execute_tools(messages, [], None)
    assert res is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_execution_error(mock_tools_registry, mock_logger):
    """Test maybe_execute_tools handles execution errors gracefully."""
    _, mock_exec = mock_tools_registry
    mock_exec.side_effect = Exception("Execution failed")

    tools = [{"type": "function", "function": {"name": "func1"}}]
    messages = [Message(role="user", content='call func1 {"arg": 1}')]

    res = await maybe_execute_tools(messages, tools, "func1")
    assert res is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_fallback_args(mock_tools_registry, mock_logger):
    """Test maybe_execute_tools uses empty dict when no JSON found."""
    _, mock_exec = mock_tools_registry
    mock_exec.return_value = "res"

    tools = [{"type": "function", "function": {"name": "func1"}}]
    # No JSON in content
    messages = [Message(role="user", content="call func1")]

    res = await maybe_execute_tools(messages, tools, "func1")

    assert res is not None
    assert res[0]["arguments"] == "{}"
    mock_exec.assert_called_with("func1", "{}")


def test_prepare_combined_prompt_tool_choice_string(mock_logger):
    """Test tool choice injection with specific string name."""
    tools = [{"type": "function", "function": {"name": "my_tool"}}]
    messages = [Message(role="user", content="hi")]

    # tool_choice as string name
    prompt, _ = prepare_combined_prompt(
        messages, "req1", tools=tools, tool_choice="my_tool"
    )

    assert "Recommended function to use: my_tool" in prompt


def test_prepare_combined_prompt_tool_choice_dict(mock_logger):
    """Test tool choice injection with dictionary."""
    tools = [{"type": "function", "function": {"name": "my_tool"}}]
    messages = [Message(role="user", content="hi")]

    # tool_choice as dict
    tool_choice = {"type": "function", "function": {"name": "my_tool"}}
    prompt, _ = prepare_combined_prompt(
        messages, "req1", tools=tools, tool_choice=tool_choice
    )

    assert "Recommended function to use: my_tool" in prompt


def test_prepare_combined_prompt_tools_error(mock_logger):
    """Test error handling during tools processing."""

    class BadTool:
        def get(self, k):
            raise ValueError("Bad tool")

    tools = [BadTool()]
    messages = [Message(role="user", content="hi")]

    # Should not crash
    prompt, _ = prepare_combined_prompt(
        messages, "req1", tools=cast(List[Dict[str, Any]], tools)
    )
    assert "User:\nhi" in prompt


def test_prepare_combined_prompt_empty_content(mock_logger):
    """Test message with None content."""
    messages = [Message.model_construct(role="user", content=None)]
    prompt, _ = prepare_combined_prompt(messages, "req1")

    # If it's the only message and content is None/empty, it is skipped.
    assert prompt == ""


def test_prepare_combined_prompt_tool_result_list_exception(mock_logger):
    """Test tool result list processing exception handling."""

    class BadItem:
        def __str__(self):
            raise ValueError("Cannot stringify")

    messages = [
        Message.model_construct(role="tool", content=[BadItem()], tool_call_id="1")
    ]

    prompt, _ = prepare_combined_prompt(messages, "req1")
    # It should fall back to str(msg.content) in the except block
    assert "tool_call_id=1" in prompt


def test_collect_and_validate_attachments_top_level(mock_file_utils, mock_logger):
    """Test top level attachments in request."""
    mock_extract, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    class MockRequest:
        attachments = ["/tmp/top1.png", {"url": "file:///c:/top2.png"}]
        messages = []

    req = MockRequest()
    result = collect_and_validate_attachments(req, "req1", [])

    assert "/tmp/top1.png" in result
    assert any("top2.png" in f for f in result)


def test_collect_and_validate_attachments_initial_filter(mock_file_utils, mock_logger):
    """Test filtering of initial image list."""
    _, _, mock_exists = mock_file_utils

    # mock_exists side effect to filter
    def side_effect(path):
        return path == "/exists.png"

    mock_exists.side_effect = side_effect

    initial = ["/exists.png", "/missing.png", "relative.png"]

    # Need request object
    class MockRequest:
        messages = []

    result = collect_and_validate_attachments(MockRequest(), "req1", initial)

    assert "/exists.png" in result
    assert "/missing.png" not in result
    assert "relative.png" not in result


def test_prepare_combined_prompt_tool_fallback_name(mock_logger):
    """Test tool definition fallback when function is not a dict."""
    # Case: function is string, name is in top level
    tools = [{"function": "not_a_dict", "name": "fallback_tool"}]
    messages = [Message(role="user", content="hi")]

    prompt, _ = prepare_combined_prompt(messages, "req1", tools=tools)

    assert "- Function: fallback_tool" in prompt


def test_prepare_combined_prompt_tool_params_unserializable(mock_logger):
    """Test tool params that cannot be serialized."""

    class NoJson:
        def __str__(self):
            return "NoJson"

    # Use model_construct or just dict if tools is list of dicts
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bad_params",
                "parameters": NoJson(),  # json.dumps will fail
            },
        }
    ]
    messages = [Message(role="user", content="hi")]

    prompt, _ = prepare_combined_prompt(messages, "req1", tools=tools)

    # Should contain function name but skip params
    assert "- Function: bad_params" in prompt
    assert "Parameter Schema:" not in prompt


def test_prepare_combined_prompt_empty_system_message(mock_logger):
    """Test empty system message handling."""
    messages = [
        Message(role="system", content=""),  # Empty content
        Message(role="user", content="Hi"),
    ]
    prompt, _ = prepare_combined_prompt(messages, "req1")

    assert "System Instructions:" not in prompt
    assert "User:\nHi" in prompt


def test_prepare_combined_prompt_item_type_exception(mock_logger):
    """Test exception when accessing item.type."""

    class BadItem:
        @property
        def type(self):
            raise ValueError("No type")

        def __str__(self):
            return "BadItemStr"

    messages = [Message.model_construct(role="user", content=[BadItem()])]

    prompt, _ = prepare_combined_prompt(messages, "req1")

    # Should swallow exception and ignore the item
    assert "BadItemStr" not in prompt
    # Since content is effectively empty and it's the only message, it should be skipped entirely
    assert prompt == ""


def test_prepare_combined_prompt_object_file_url(mock_file_utils, mock_logger):
    """Test object-style content with file_url/media_url."""
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    class UrlObj:
        def __init__(self, url):
            self.url = url

    class ItemWithFileUrl:
        type = "file_url"
        file_url = UrlObj("file:///c:/file.txt")

    class ItemWithMediaUrl:
        type = "media_url"
        media_url = UrlObj("file:///c:/media.mp4")

    messages = [
        Message.model_construct(
            role="user", content=[ItemWithFileUrl(), ItemWithMediaUrl()]
        )
    ]

    prompt, files = prepare_combined_prompt(messages, "req1")

    # Check if files were added
    assert any("file.txt" in f for f in files)
    assert any("media.mp4" in f for f in files)


def test_prepare_combined_prompt_non_existent_local_file(mock_file_utils, mock_logger):
    """Test non-existent local file URL."""
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = False  # Not exists

    item = {"type": "file_url", "file_url": {"url": "file:///c:/missing.txt"}}
    messages = [Message(role="user", content=cast(List[MessageContentItem], [item]))]

    prompt, files = prepare_combined_prompt(messages, "req1")

    # Should not be in files list
    assert len(files) == 0


def test_collect_and_validate_attachments_detailed(
    mock_file_utils, mock_logger, tmp_path
):
    """Test detailed attachment collection logic including top-level and various message keys.

    Uses tmp_path for platform-compatible paths.
    """
    mock_extract, _, mock_exists = mock_file_utils

    # Create actual temp files for cross-platform path handling
    valid_initial = tmp_path / "valid_initial.png"
    valid_top_level = tmp_path / "valid_top_level.png"
    valid_file_url = tmp_path / "valid_file_url.txt"
    valid_image = tmp_path / "valid_image.png"
    valid_file = tmp_path / "valid_file.pdf"
    valid_media = tmp_path / "valid_media.mp4"
    missing_initial = tmp_path / "missing_initial.png"
    missing = tmp_path / "missing.png"

    # Create "valid" files, leave "missing" files uncreated
    valid_initial.touch()
    valid_top_level.touch()
    valid_file_url.touch()
    valid_image.touch()
    valid_file.touch()
    valid_media.touch()

    # Mock file existence based on actual file existence
    def side_effect(path):
        from pathlib import Path

        # Handle string paths and Path objects
        path_str = str(path)
        # Check if it looks like one of our temp files that we created/didn't create
        if str(tmp_path) in path_str:
            return Path(path_str).exists()
        return True  # Default to True for other files logic might check

    mock_exists.side_effect = side_effect
    mock_exists.return_value = None  # Clear return_value so side_effect is used

    mock_extract.side_effect = lambda url, **kwargs: f"/tmp/{url.split('/')[-1]}"

    # Mock request object with various attachment fields
    class MockRequest:
        attachments = [
            str(valid_top_level),
            str(missing),
            {"url": "data:image/png;base64,data1"},
            {"url": f"file://{valid_file_url}"},
            "",  # Empty string
            None,  # None
            {"url": ""},  # Empty URL in dict
        ]
        messages = [
            Message.model_construct(
                role="user",
                content="msg1",
                images=[str(valid_image)],
                files=[{"path": str(valid_file)}],
                media=[f"file://{valid_media}"],
            )
        ]

    req = MockRequest()
    initial_list = [str(valid_initial), str(missing_initial)]

    result = collect_and_validate_attachments(req, "req1", initial_list)

    # Check initial list filtering
    assert str(valid_initial) in result
    assert str(missing_initial) not in result

    # Check top-level attachments
    assert str(valid_top_level) in result
    assert str(missing) not in result
    # data: URL -> extracted (mock extract returns /tmp/...)
    assert mock_extract.called

    # Check message-level attachments
    assert str(valid_image) in result
    assert str(valid_file) in result
    # file:// -> unquoted path
    assert any("valid_media.mp4" in f for f in result)


def test_prepare_combined_prompt_tool_edge_cases(mock_logger):
    """Test edge cases for tool definitions and choice."""
    # Malformed tool definition (missing function)
    tools = [
        {"type": "function"},  # Missing function dict
        {"name": "direct_name_tool"},  # Old style direct dict
    ]

    # Tool choice that doesn't match any tool
    tool_choice = "non_existent_tool"

    messages = [Message(role="user", content="Hi")]

    prompt, _ = prepare_combined_prompt(
        messages, "req1", tools=tools, tool_choice=tool_choice
    )

    # Should handle malformed tool gracefully (skip or partial log)
    # "direct_name_tool" might be processed if logic allows (it does: t.get('name'))
    assert "Function: direct_name_tool" in prompt

    # tool_choice "non_existent_tool" might still be suggested if logic just appends it
    assert "Recommended function to use: non_existent_tool" in prompt


def test_prepare_combined_prompt_content_pydantic_objects(mock_file_utils, mock_logger):
    """Test content items as objects (simulating Pydantic models) instead of dicts."""
    mock_extract, mock_save, _ = mock_file_utils
    mock_save.return_value = "/tmp/saved.mp3"

    class InputAudio:
        data = "SGVsbG8="  # Valid base64 "Hello"
        mime_type = "audio/mp3"
        format = "mp3"

    class ContentItem:
        type = "input_audio"
        input_audio = InputAudio()

    messages = [Message.model_construct(role="user", content=[ContentItem()])]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/tmp/saved.mp3" in files


def test_prepare_combined_prompt_empty_url_strings(mock_logger):
    """Test content items with empty URL strings."""
    content = [
        {"type": "image_url", "image_url": {"url": ""}},
        {"type": "image_url", "image_url": {"url": "   "}},
        {"type": "text", "text": "Valid Text"},
    ]

    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "Valid Text" in prompt
    assert len(files) == 0


def test_prepare_combined_prompt_fallback_str_content(mock_logger):
    """Test fallback when content is not string/list/dict (e.g. None or unexpected type)."""
    # None content handled in loop start usually, but let's try weird type
    messages = [Message.model_construct(role="user", content=12345)]

    prompt, _ = prepare_combined_prompt(messages, "req1")

    # Should convert to string
    assert "12345" in prompt


def test_prepare_combined_prompt_input_image_with_detail(mock_file_utils, mock_logger):
    """Test input_image object with detail field (lines 234-244)."""
    mock_extract, _, _ = mock_file_utils
    mock_extract.return_value = "/tmp/input_image.png"

    class InputImage:
        url = "data:image/png;base64,iVBORw0KGgo="
        detail = "high"

    class ContentItem:
        type = "image_url"

        def __init__(self):
            self.input_image = InputImage()

    messages = [Message.model_construct(role="user", content=[ContentItem()])]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/tmp/input_image.png" in files
    assert "[Image Details: detail=high]" in prompt


def test_prepare_combined_prompt_dict_image_url_with_detail(
    mock_file_utils, mock_logger
):
    """Test dict image_url with detail field (lines 266-268)."""
    mock_extract, _, _ = mock_file_utils
    mock_extract.return_value = "/tmp/image_detail.png"

    # Dict structure with nested image_url dict containing detail
    content = [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,ABC123", "detail": "auto"},
        }
    ]

    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/tmp/image_detail.png" in files
    assert "[Image Details: detail=auto]" in prompt


def test_prepare_combined_prompt_audio_absolute_path(
    mock_file_utils, mock_logger, tmp_path
):
    """Test audio with absolute path (lines 427-431).

    Uses tmp_path for platform-compatible paths.
    """
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    # Create actual temp file for cross-platform path handling
    audio_file = tmp_path / "test.mp3"
    audio_file.touch()

    # Absolute path for audio
    content_item = {
        "type": "input_audio",
        "input_audio": {"url": str(audio_file)},
    }

    messages = [
        Message(role="user", content=cast(List[MessageContentItem], [content_item]))
    ]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert str(audio_file) in files


def test_prepare_combined_prompt_video_absolute_path(mock_file_utils, mock_logger):
    """Test video with absolute path (lines 427-431)."""
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    # Absolute path for video
    content_item = {
        "type": "input_video",
        "input_video": {"url": "/home/user/video.mp4"},
    }

    messages = [
        Message(role="user", content=cast(List[MessageContentItem], [content_item]))
    ]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/home/user/video.mp4" in files


def test_get_latest_user_text_dict_non_text_type(mock_logger):
    """Test _get_latest_user_text with dict items that are not text type (lines 666-671)."""
    messages = [
        Message.model_construct(
            role="user",
            content=[
                {"type": "image", "url": "image.png"},  # Not text type
                {"type": "audio", "data": "..."},  # Not text type
                {"type": "text", "text": "Valid text"},
            ],
        )
    ]

    result = _get_latest_user_text(messages)

    # Should only extract text items
    assert result == "Valid text"


def test_get_latest_user_text_dict_content_empty(mock_logger):
    """Test _get_latest_user_text with dict content that has no text (lines 680-681)."""
    # Dict content with no text field
    messages = [
        Message.model_construct(role="user", content={"attachments": ["file.pdf"]})
    ]

    result = _get_latest_user_text(messages)

    assert result == ""


def test_get_latest_user_text_no_user_message(mock_logger):
    """Test _get_latest_user_text with no user messages (lines 680-681)."""
    messages = [
        Message(role="assistant", content="Hello"),
        Message(role="system", content="System"),
    ]

    result = _get_latest_user_text(messages)

    assert result == ""


@pytest.mark.asyncio
async def test_maybe_execute_tools_auto_single_tool_name_fallback(
    mock_tools_registry, mock_logger
):
    """Test maybe_execute_tools with auto choice, single tool, name at top level (lines 726-728)."""
    _, mock_exec = mock_tools_registry
    mock_exec.return_value = "success"

    # Tool with name at top level, no function dict
    tools = [{"name": "top_level_func"}]
    tool_choice = "auto"

    messages = [Message(role="user", content='call it {"arg": 1}')]

    results = await maybe_execute_tools(messages, tools, tool_choice)

    assert results is not None
    assert results[0]["name"] == "top_level_func"


@pytest.mark.asyncio
async def test_maybe_execute_tools_required_single_tool(
    mock_tools_registry, mock_logger
):
    """Test maybe_execute_tools with 'required' choice (lines 717-728)."""
    _, mock_exec = mock_tools_registry
    mock_exec.return_value = "result"

    tools = [{"type": "function", "function": {"name": "required_func"}}]
    tool_choice = "required"

    messages = [Message(role="user", content='{"x": 1}')]

    results = await maybe_execute_tools(messages, tools, tool_choice)

    assert results is not None
    assert results[0]["name"] == "required_func"


def test_prepare_combined_prompt_tool_params_json_dumps_error(mock_logger):
    """Test tool params that raise exception during json.dumps (lines 96-97)."""

    class UnserializableParams:
        """Object that cannot be JSON serialized."""

        def __iter__(self):
            raise TypeError("Cannot iterate")

    # Create tool with unserializable parameters
    tools = [
        {
            "type": "function",
            "function": {"name": "bad_tool", "parameters": UnserializableParams()},
        }
    ]

    messages = [Message(role="user", content="hi")]

    # Should not crash, just skip params serialization
    prompt, _ = prepare_combined_prompt(messages, "req1", tools=tools)

    # Tool name should still be present
    assert "- Function: bad_tool" in prompt
    # But params should be skipped due to exception


def test_collect_and_validate_attachments_empty_url_handling(
    mock_file_utils, mock_logger, tmp_path
):
    """Test attachment collection with empty URL strings (lines 802, 831, 834).

    Uses tmp_path for platform-compatible paths.
    """
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    # Create actual temp files for cross-platform path handling
    valid_png = tmp_path / "valid.png"
    valid_image = tmp_path / "valid_image.png"
    valid_file = tmp_path / "valid_file.pdf"
    valid_png.touch()
    valid_image.touch()
    valid_file.touch()

    class MockRequest:
        attachments = [
            "",  # Empty string
            "   ",  # Whitespace only
            {"url": ""},  # Empty URL in dict
            {"url": "   "},  # Whitespace URL in dict
            str(valid_png),  # Valid path
        ]
        messages = [
            Message.model_construct(
                role="user",
                content="test",
                images=["", str(valid_image)],
                files=[{"path": ""}, {"path": str(valid_file)}],
            )
        ]

    req = MockRequest()
    result = collect_and_validate_attachments(req, "req1", [])

    # Only valid paths should be included
    assert str(valid_png) in result
    assert str(valid_image) in result
    assert str(valid_file) in result

    # Empty strings should be filtered out
    assert "" not in result
    assert "   " not in result


def test_prepare_combined_prompt_dict_input_image_with_detail(
    mock_file_utils, mock_logger
):
    """Test dict input_image structure with detail field (lines 271-282)."""
    mock_extract, _, _ = mock_file_utils
    mock_extract.return_value = "/tmp/input_img_detail.png"

    content = [
        {
            "type": "image_url",
            "input_image": {
                "url": "data:image/png;base64,XYZ",
                "detail": "low",
            },
        }
    ]

    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/tmp/input_img_detail.png" in files
    assert "[Image Details: detail=low]" in prompt


def test_prepare_combined_prompt_dict_content_file_field(
    mock_file_utils, mock_logger, tmp_path
):
    """Test dict content with generic 'file' field (lines 313-322).

    Uses tmp_path for platform-compatible paths.
    """
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    # Create actual temp file for cross-platform path handling
    file_path = tmp_path / "from_file_field.png"
    file_path.touch()

    content = [
        {
            "type": "image_url",
            "file": {"url": str(file_path)},
        }
    ]

    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert str(file_path) in files


def test_prepare_combined_prompt_dict_content_file_path(mock_file_utils, mock_logger):
    """Test dict content with file.path field (lines 318-322)."""
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    content = [
        {
            "type": "file_url",
            "file": {"path": "/absolute/path/file.pdf"},
        }
    ]

    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/absolute/path/file.pdf" in files


def test_prepare_combined_prompt_object_url_attribute(
    mock_file_utils, mock_logger, tmp_path
):
    """Test content item with direct url attribute (lines 249-250).

    Uses tmp_path for platform-compatible paths.
    """
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    # Create actual temp file for cross-platform path handling
    url_path = tmp_path / "direct_url.png"
    url_path.touch()

    class UrlItem:
        type = "image_url"
        url = str(url_path)

    messages = [Message.model_construct(role="user", content=[UrlItem()])]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert str(url_path) in files


def test_prepare_combined_prompt_dict_attachments_nested_input_image(
    mock_file_utils, mock_logger
):
    """Test dict content attachments with nested input_image (lines 496-502)."""
    mock_extract, _, _ = mock_file_utils
    mock_extract.return_value = "/tmp/nested_input.png"

    content = {
        "text": "Check attachment",
        "attachments": [
            {"input_image": {"url": "data:image/png;base64,NESTED"}},
        ],
    }

    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "Check attachment" in prompt
    assert "/tmp/nested_input.png" in files


def test_prepare_combined_prompt_content_item_input_image_string(
    mock_file_utils, mock_logger, tmp_path
):
    """Test content item with input_image as string (lines 283-284).

    Uses tmp_path for platform-compatible paths.
    """
    _, _, mock_exists = mock_file_utils
    mock_exists.return_value = True

    # Create actual temp file for cross-platform path handling
    img_path = tmp_path / "string_input_image.png"
    img_path.touch()

    # This tests the case where item has input_image as a string directly
    content = [
        {
            "type": "image_url",
            "input_image": str(img_path),  # String, not dict
        }
    ]

    messages = [Message.model_construct(role="user", content=content)]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert str(img_path) in files


def test_prepare_combined_prompt_audio_video_data_base64(mock_file_utils, mock_logger):
    """Test audio/video with raw base64 data not starting with 'data:' (lines 446-459)."""
    _, mock_save, _ = mock_file_utils
    mock_save.return_value = "/tmp/base64_audio.mp3"

    content_item = {
        "type": "input_audio",
        "input_audio": {
            "data": "SGVsbG8gV29ybGQ=",  # Not starting with "data:"
            "mime_type": "audio/mp3",
            "format": "mp3",
        },
    }

    messages = [
        Message(role="user", content=cast(List[MessageContentItem], [content_item]))
    ]

    prompt, files = prepare_combined_prompt(messages, "req1")

    assert "/tmp/base64_audio.mp3" in files
    mock_save.assert_called_once()


def test_prepare_combined_prompt_tool_result_no_tool_call_id(mock_logger):
    """Test tool result without tool_call_id (lines 579-586)."""
    messages = [Message.model_construct(role="tool", content="Result without ID")]

    prompt, _ = prepare_combined_prompt(messages, "req1")

    # Should still include content, but no tool_call_id line
    assert "Result without ID" in prompt
    assert "tool_call_id=" not in prompt


def test_prepare_combined_prompt_assistant_empty_with_tool_calls(mock_logger):
    """Test assistant message with no content but has tool_calls (line 614)."""
    tool_call = ToolCall(
        id="call1",
        type="function",
        function=FunctionCall(name="func", arguments="{}"),
    )

    messages = [
        Message(role="assistant", content="", tool_calls=[tool_call])  # Empty content
    ]

    prompt, _ = prepare_combined_prompt(messages, "req1")

    assert "Request function call: func" in prompt

    prompt, _ = prepare_combined_prompt(messages, "req1")

    # Should include tool call visualization even with empty content
    assert "Request function call: func" in prompt


def test_prepare_combined_prompt_skip_empty_messages_edge_case(mock_logger):
    """Test edge case for empty message skipping (lines 616-621)."""
    # Edge case: First message with only role prefix, no content
    messages = [Message.model_construct(role="assistant", content="")]

    prompt, _ = prepare_combined_prompt(messages, "req1")

    # Should be empty since only role prefix and no content
    assert prompt == ""
