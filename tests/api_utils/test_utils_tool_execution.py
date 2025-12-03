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
    测试场景: 函数被取消时正确重新抛出 CancelledError
    预期: CancelledError 不会被吞掉，必须重新抛出
    这是 CRITICAL 测试 - 防止请求挂起
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "test_tool"}}]
    tool_choice = {"type": "function", "function": {"name": "test_tool"}}

    # Mock execute_tool_call to raise CancelledError
    with patch(
        "api_utils.utils.execute_tool_call", new_callable=AsyncMock
    ) as mock_exec:
        mock_exec.side_effect = asyncio.CancelledError()
        with patch("api_utils.utils.register_runtime_tools"):
            # 预期: CancelledError 被重新抛出
            with pytest.raises(asyncio.CancelledError):
                await maybe_execute_tools(messages, tools, tool_choice)


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_dict_format():
    """
    测试场景: tool_choice 为字典格式 {"type": "function", "function": {"name": "foo"}}
    预期: 提取函数名并执行
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content='{"arg": "value"}')]
    tools = [{"function": {"name": "my_function"}}]
    tool_choice = {"type": "function", "function": {"name": "my_function"}}

    with (
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools"),
    ):
        mock_exec.return_value = '{"result": "success"}'

        result = await maybe_execute_tools(messages, tools, tool_choice)

        # 验证: execute_tool_call 被调用，参数正确
        mock_exec.assert_called_once_with("my_function", '{"arg": "value"}')
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "my_function"
        assert result[0]["arguments"] == '{"arg": "value"}'
        assert result[0]["result"] == '{"result": "success"}'


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_string_none():
    """
    测试场景: tool_choice 为字符串 "none" (大小写不敏感)
    预期: 返回 None，不执行任何工具
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "test_tool"}}]

    with patch("api_utils.utils.register_runtime_tools"):
        for choice in ["none", "None", "NONE", "no", "NO", "off", "OFF"]:
            result = await maybe_execute_tools(messages, tools, choice)
            assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_auto_single_tool():
    """
    测试场景: tool_choice 为 "auto" 且只有一个工具
    预期: 自动执行该工具
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content='{"x": 1}')]
    tools = [{"function": {"name": "only_tool"}}]

    with (
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools"),
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
    测试场景: tool_choice 为 "auto" 但有多个工具
    预期: 不执行任何工具（因为无法自动选择）
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [
        {"function": {"name": "tool1"}},
        {"function": {"name": "tool2"}},
    ]

    with patch("api_utils.utils.register_runtime_tools"):
        result = await maybe_execute_tools(messages, tools, "auto")
        assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_direct_name():
    """
    测试场景: tool_choice 为函数名字符串（直接指定）
    预期: 执行该函数
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content='{"param": 123}')]
    tools = [{"function": {"name": "direct_call"}}]

    with (
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools"),
    ):
        mock_exec.return_value = '{"status": "ok"}'

        result = await maybe_execute_tools(messages, tools, "direct_call")

        assert result is not None
        assert result[0]["name"] == "direct_call"
        mock_exec.assert_called_once_with("direct_call", '{"param": 123}')


@pytest.mark.asyncio
async def test_maybe_execute_tools_tool_choice_none():
    """
    测试场景: tool_choice 为 None
    预期: 不主动执行工具，返回 None
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "test_tool"}}]

    with patch("api_utils.utils.register_runtime_tools"):
        result = await maybe_execute_tools(messages, tools, None)
        assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_arguments_from_user_text():
    """
    测试场景: 从最近的用户消息中提取 JSON 作为参数
    预期: 使用 _extract_json_from_text 提取 JSON
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
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools"),
    ):
        mock_exec.return_value = "ok"

        result = await maybe_execute_tools(messages, tools, tool_choice)

        # 验证: 参数是从最后一条用户消息中提取的 JSON
        mock_exec.assert_called_once_with("test_func", '{"key": "value", "num": 42}')
        assert result is not None
        assert result[0]["arguments"] == '{"key": "value", "num": 42}'


@pytest.mark.asyncio
async def test_maybe_execute_tools_arguments_fallback_empty():
    """
    测试场景: 用户消息中没有有效 JSON
    预期: 使用空参数 "{}"
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="No JSON here, just plain text")]
    tools = [{"function": {"name": "my_tool"}}]
    tool_choice = "my_tool"

    with (
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools"),
    ):
        mock_exec.return_value = "done"

        result = await maybe_execute_tools(messages, tools, tool_choice)

        # 验证: 参数回退到空 JSON
        mock_exec.assert_called_once_with("my_tool", "{}")
        assert result is not None
        assert result[0]["arguments"] == "{}"


@pytest.mark.asyncio
async def test_maybe_execute_tools_existing_tool_result_skip():
    """
    测试场景: 消息列表中已有 role='tool' 的消息
    预期: 不再执行工具，返回 None（遵循对话式调用循环）
    """
    from api_utils.utils import maybe_execute_tools

    messages = [
        Message(role="user", content='{"x": 1}'),
        Message(role="assistant", content="Let me call the tool"),
        # 已有工具结果消息
        Message(role="tool", content='{"result": "previous call"}'),
    ]
    tools = [{"function": {"name": "my_tool"}}]
    tool_choice = "my_tool"

    with patch("api_utils.utils.register_runtime_tools"):
        result = await maybe_execute_tools(messages, tools, tool_choice)

        # 验证: 不执行，因为已有工具结果
        assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_base_exception_returns_none():
    """
    测试场景: execute_tool_call 抛出普通异常（非 CancelledError）
    预期: 捕获异常，返回 None
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content='{"arg": "val"}')]
    tools = [{"function": {"name": "failing_tool"}}]
    tool_choice = "failing_tool"

    with (
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools"),
    ):
        # Mock 抛出普通异常
        mock_exec.side_effect = ValueError("Something went wrong")

        result = await maybe_execute_tools(messages, tools, tool_choice)

        # 验证: 异常被捕获，返回 None
        assert result is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_register_runtime_tools_called():
    """
    测试场景: 验证 register_runtime_tools 被正确调用
    预期: 每次调用 maybe_execute_tools 时注册工具
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "tool1"}}, {"function": {"name": "tool2"}}]
    tool_choice = "tool1"

    with (
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools") as mock_register,
    ):
        mock_exec.return_value = "ok"

        await maybe_execute_tools(messages, tools, tool_choice)

        # 验证: register_runtime_tools 被调用，传入 tools 和 None（默认 MCP 端点）
        mock_register.assert_called_once_with(tools, None)


@pytest.mark.asyncio
async def test_maybe_execute_tools_empty_messages():
    """
    测试场景: 消息列表为空
    预期: 无用户文本，参数回退到 "{}"
    """
    from api_utils.utils import maybe_execute_tools

    messages = []
    tools = [{"function": {"name": "test_tool"}}]
    tool_choice = "test_tool"

    with (
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools"),
    ):
        mock_exec.return_value = "done"

        await maybe_execute_tools(messages, tools, tool_choice)

        # 验证: 参数为空 JSON
        mock_exec.assert_called_once_with("test_tool", "{}")


@pytest.mark.asyncio
async def test_maybe_execute_tools_no_chosen_name():
    """
    测试场景: tool_choice 解析后没有得到函数名
    预期: 返回 None
    """
    from api_utils.utils import maybe_execute_tools

    messages = [Message(role="user", content="test")]
    tools = [{"function": {"name": "test_tool"}}]

    with patch("api_utils.utils.register_runtime_tools"):
        # tool_choice 为空字典，无 function.name
        result1 = await maybe_execute_tools(messages, tools, {})
        assert result1 is None

        # tool_choice 为字典但 function.name 缺失
        result2 = await maybe_execute_tools(
            messages, tools, {"type": "function", "function": {}}
        )
        assert result2 is None


@pytest.mark.asyncio
async def test_maybe_execute_tools_multiline_json_extraction():
    """
    测试场景: 用户消息包含多行 JSON
    预期: 正确提取跨行的 JSON
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
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools"),
    ):
        mock_exec.return_value = "ok"

        await maybe_execute_tools(messages, tools, tool_choice)

        # 验证: 提取了完整的多行 JSON
        called_args = mock_exec.call_args[0][1]
        import json

        parsed = json.loads(called_args)
        assert parsed["param1"] == "value1"
        assert parsed["nested"]["key"] == "val"


@pytest.mark.asyncio
async def test_maybe_execute_tools_list_content_extraction():
    """
    测试场景: 用户消息内容为列表（包含文本和图片）
    预期: 从文本部分提取 JSON
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
        patch("api_utils.utils.execute_tool_call", new_callable=AsyncMock) as mock_exec,
        patch("api_utils.utils.register_runtime_tools"),
    ):
        mock_exec.return_value = "processed"

        await maybe_execute_tools(messages, tools, tool_choice)

        # 验证: 从拼接的文本中提取了 JSON
        # _get_latest_user_text 会拼接: "Before image\n{\"action\": \"process_image\"}"
        # _extract_json_from_text 会提取: {"action": "process_image"}
        mock_exec.assert_called_once_with("image_tool", '{"action": "process_image"}')
