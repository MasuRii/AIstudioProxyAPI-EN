"""
High-quality tests for api_utils/utils.py - Tool execution safety (zero mocking of core logic).

Focus: Test maybe_execute_tools with emphasis on async safety and edge cases.
Strategy: Mock only external boundaries (execute_tool_call, register_runtime_tools).
"""

import asyncio
from typing import List, cast
from unittest.mock import AsyncMock, patch

import pytest

from models import Message, MessageContentItem


@pytest.mark.asyncio
async def test_maybe_execute_tools_cancelled_error_reraised():
    """
    Test scenario: Correctly re-throw CancelledError when function is cancelled
    Expected: CancelledError not swallowed, must be re-thrown
    This is a CRITICAL test - prevents request hang
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "test_tool"}}]
    tool_choice = {"type": "function", "function": {"name": "test_tool"}}

    # Mock execute_tool_call to raise CancelledError - patch where it's imported/used
    with patch(
        "api_utils.utils_ext.tools_execution.execute_tool_call", new_callable=AsyncMock
    ) as mock_exec:
        mock_exec.side_effect = asyncio.CancelledError()
        with patch("api_utils.utils_ext.tools_execution.register_runtime_tools"):
            # Expected: CancelledError re-thrown
            with pytest.raises(asyncio.CancelledError):
                await maybe_execute_tools(messages, tools, tool_choice)


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_dict_format():
    """
    Test scenario: tool_choice as dictionary format {"type": "function", "function": {"name": "foo"}}
    Expected: Extract function name and execute
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content='{"arg": "value"}')]
    tools = [{"function": {"name": "my_function"}}]
    tool_choice = {"type": "function", "function": {"name": "my_function"}}

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools"),
    ):
        mock_exec.return_value = '{"result": "success"}'

        result = await maybe_execute_tools(messages, tools, tool_choice)

        # Verify: execute_tool_call called with correct parameters
        mock_exec.assert_called_once_with("my_function", '{"arg": "value"}')
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "my_function"
        assert result[0]["arguments"] == '{"arg": "value"}'
        assert result[0]["result"] == '{"result": "success"}'


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_string_none():
    """
    Test scenario: tool_choice as string "none" (case-insensitive)
    Expected: Return None, no tool executed
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "test_tool"}}]

    with patch("api_utils.utils_ext.tools_execution.register_runtime_tools"):
        for choice in ["none", "None", "NONE", "no", "NO", "off", "OFF"]:
            result = await maybe_execute_tools(messages, tools, choice)
            assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_auto_single_tool():
    """
    Test scenario: tool_choice as "auto" and only one tool
    Expected: Automatically execute that tool
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content='{"x": 1}')]
    tools = [{"function": {"name": "only_tool"}}]

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools"),
    ):
        mock_exec.return_value = '{"done": true}'

        for choice in ["auto", "required", "any"]:
            result = await maybe_execute_tools(messages, tools, choice)

            assert result is not None
            assert result[0]["name"] == "only_tool"
            mock_exec.assert_called_with("only_tool", '{"x": 1}')
            mock_exec.reset_mock()


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_auto_multiple_tools():
    """
    Test scenario: tool_choice as "auto" but multiple tools
    Expected: No tool executed (as automatic choice is not possible)
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [
        {"function": {"name": "tool1"}},
        {"function": {"name": "tool2"}},
    ]

    with patch("api_utils.utils_ext.tools_execution.register_runtime_tools"):
        result = await maybe_execute_tools(messages, tools, "auto")
        assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_direct_name():
    """
    Test scenario: tool_choice as function name string (direct specification)
    Expected: Execute that function
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content='{"param": 123}')]
    tools = [{"function": {"name": "direct_call"}}]

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools"),
    ):
        mock_exec.return_value = '{"status": "ok"}'

        result = await maybe_execute_tools(messages, tools, "direct_call")

        assert result is not None
        assert result[0]["name"] == "direct_call"
        mock_exec.assert_called_once_with("direct_call", '{"param": 123}')


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_none():
    """
    Test scenario: tool_choice is None
    Expected: Do not actively execute tool, return None
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "test_tool"}}]

    with patch("api_utils.utils_ext.tools_execution.register_runtime_tools"):
        result = await maybe_execute_tools(messages, tools, None)
        assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_arguments_from_user_text():
    """
    Test scenario: Extract JSON from the latest user message as parameters
    Expected: Use _extract_json_from_text to extract JSON
    """
    from api_utils.utils import maybe_execute_tools

    messages = [
        Message(role="system", content="System message"),
        Message(role="user", content="First user message"),
        Message(role="assistant", content="Response"),
        Message(
            role="user",
            content='Call function with params: {"key": "value", "num": 42}',
        ),
    ]
    tools = [{"function": {"name": "test_func"}}]
    tool_choice = "test_func"

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools"),
    ):
        mock_exec.return_value = "ok"

        result = await maybe_execute_tools(messages, tools, tool_choice)

        # Verify: Parameters extracted as JSON from the last user message
        mock_exec.assert_called_once_with("test_func", '{"key": "value", "num": 42}')
        assert result is not None
        assert result[0]["arguments"] == '{"key": "value", "num": 42}'


@pytest.mark.asyncio
async def test_maybe_execute_tools_arguments_fallback_empty():
    """
    Test scenario: No valid JSON in user message
    Expected: Use empty parameters "{}"
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="No JSON here, just plain text")]
    tools = [{"function": {"name": "my_tool"}}]
    tool_choice = "my_tool"

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools"),
    ):
        mock_exec.return_value = "done"

        result = await maybe_execute_tools(messages, tools, tool_choice)

        # Verify: Parameters fall back to empty JSON
        mock_exec.assert_called_once_with("my_tool", "{}")
        assert result is not None
        assert result[0]["arguments"] == "{}"


@pytest.mark.asyncio
async def test_maybe_execute_tools_existing_tool_result_skip():
    """
    Test scenario: Message with role='tool' already in message list
    Expected: No further tool execution, return None (follows conversational call loop)
    """
    from api_utils.utils import maybe_execute_tools

    messages = [
        Message(role="user", content='{"x": 1}'),
        Message(role="assistant", content="Let me call the tool"),
        # Already have tool result message
        Message(role="tool", content='{"result": "previous call"}'),
    ]
    tools = [{"function": {"name": "my_tool"}}]
    tool_choice = "my_tool"

    with patch("api_utils.utils_ext.tools_execution.register_runtime_tools"):
        result = await maybe_execute_tools(messages, tools, tool_choice)

        # Verify: No execution because tool result already exists
        assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_base_exception_returns_none():
    """
    Test scenario: execute_tool_call throws common exception (non-CancelledError)
    Expected: Catch exception, return None
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content='{"arg": "val"}')]
    tools = [{"function": {"name": "failing_tool"}}]
    tool_choice = "failing_tool"

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools"),
    ):
        # Mock common exception
        mock_exec.side_effect = ValueError("Something went wrong")

        result = await maybe_execute_tools(messages, tools, tool_choice)

        # Verify: Exception caught, return None
        assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_register_runtime_tools_called():
    """
    Test scenario: Verify register_runtime_tools called correctly
    Expected: Register tools on each maybe_execute_tools call
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "tool1"}}, {"function": {"name": "tool2"}}]
    tool_choice = "tool1"

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch(
            "api_utils.utils_ext.tools_execution.register_runtime_tools"
        ) as mock_register,
    ):
        mock_exec.return_value = "ok"

        await maybe_execute_tools(messages, tools, tool_choice)

        # Verify: register_runtime_tools called with tools and None (default MCP endpoint)
        mock_register.assert_called_once_with(tools, None)


@pytest.mark.asyncio
async def test_maybe_execute_tools_empty_messages():
    """
    Test scenario: Message list is empty
    Expected: No user text, parameters fall back to "{}"
    """
    from api_utils.utils import maybe_execute_tools

    messages = []
    tools = [{"function": {"name": "test_tool"}}]
    tool_choice = "test_tool"

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools"),
    ):
        mock_exec.return_value = "done"

        await maybe_execute_tools(messages, tools, tool_choice)

        # Verify: Parameters are empty JSON
        mock_exec.assert_called_once_with("test_tool", "{}")


@pytest.mark.asyncio
async def test_maybe_execute_tools_no_chosen_name():
    """
    Test scenario: No function name obtained after tool_choice parsing
    Expected: Return None
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "test_tool"}}]

    with patch("api_utils.utils_ext.tools_execution.register_runtime_tools"):
        # tool_choice is empty dict, no function.name
        result1 = await maybe_execute_tools(messages, tools, {})
        assert result1 is None

        # tool_choice is dict but function.name missing
        result2 = await maybe_execute_tools(
            messages, tools, {"type": "function", "function": {}}
        )
        assert result2 is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_multiline_json_extraction():
    """
    Test scenario: User message contains multiline JSON
    Expected: Correctly extract multiline JSON
    """
    from api_utils.utils import maybe_execute_tools

    messages = [
        Message(
            role="user",
            content="""Please call the function with:
{
    "param1": "value1",
    "param2": "value2",
    "nested": {
        "key": "val"
    }
}
Thank you!""",
        )
    ]
    tools = [{"function": {"name": "multi_tool"}}]
    tool_choice = "multi_tool"

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools"),
    ):
        mock_exec.return_value = "ok"

        await maybe_execute_tools(messages, tools, tool_choice)

        # Verify: Full multiline JSON extracted
        called_args = mock_exec.call_args[0][1]
        import json

        parsed = json.loads(called_args)
        assert parsed["param1"] == "value1"
        assert parsed["nested"]["key"] == "val"


@pytest.mark.asyncio
async def test_maybe_execute_tools_list_content_extraction():
    """
    Test scenario: User message content as list (containing text and images)
    Expected: Extract JSON from text parts
    """
    from api_utils.utils import maybe_execute_tools

    messages = [
        Message(
            role="user",
            content=cast(
                List[MessageContentItem],
                [
                    {"type": "text", "text": "Before image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "http://example.com/img.jpg"},
                    },
                    {"type": "text", "text": '{"action": "process_image"}'},
                ],
            ),
        )
    ]
    tools = [{"function": {"name": "image_tool"}}]
    tool_choice = "image_tool"

    with (
        patch(
            "api_utils.utils_ext.tools_execution.execute_tool_call",
            new_callable=AsyncMock,
        ) as mock_exec,
        patch("api_utils.utils_ext.tools_execution.register_runtime_tools"),
    ):
        mock_exec.return_value = "processed"

        await maybe_execute_tools(messages, tools, tool_choice)

        # Verify: JSON extracted from concatenated text
        # _get_latest_user_text concatenates: "Before image\n{\"action\": \"process_image\"}"
        # _extract_json_from_text extracts: {"action": "process_image"}
        mock_exec.assert_called_once_with("image_tool", '{"action": "process_image"}')
