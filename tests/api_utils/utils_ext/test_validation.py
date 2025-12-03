"""
High-quality tests for api_utils/utils_ext/validation.py (zero mocking).

Focus: Test real validation logic with no mocks, only pure function testing.
"""

import pytest

from models import Message


def test_validate_chat_request_valid():
    """
    测试场景: 有效的聊天请求（包含用户消息）
    策略: 纯函数测试，无需模拟
    """
    from api_utils.utils_ext.validation import validate_chat_request

    messages = [Message(role="user", content="Hello")]

    result = validate_chat_request(messages, req_id="req123")

    assert result["error"] is None
    assert result["warning"] is None


def test_validate_chat_request_with_system_and_user():
    """
    测试场景: 包含系统消息和用户消息的请求
    验证: 有效请求
    """
    from api_utils.utils_ext.validation import validate_chat_request

    messages = [
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="Hello"),
    ]

    result = validate_chat_request(messages, req_id="req456")

    assert result["error"] is None
    assert result["warning"] is None


def test_validate_chat_request_with_assistant_message():
    """
    测试场景: 包含助手消息的历史对话
    验证: 有效请求
    """
    from api_utils.utils_ext.validation import validate_chat_request

    messages = [
        Message(role="user", content="What is 2+2?"),
        Message(role="assistant", content="4"),
        Message(role="user", content="Thanks!"),
    ]

    result = validate_chat_request(messages, req_id="req789")

    assert result["error"] is None
    assert result["warning"] is None


def test_validate_chat_request_empty_messages():
    """
    测试场景: messages 数组为空
    预期: 抛出 ValueError
    """
    from api_utils.utils_ext.validation import validate_chat_request

    with pytest.raises(ValueError, match="messages.*缺失或为空"):
        validate_chat_request(messages=[], req_id="req101")


def test_validate_chat_request_only_system_messages():
    """
    测试场景: 仅包含系统消息，无用户或助手消息
    预期: 抛出 ValueError
    """
    from api_utils.utils_ext.validation import validate_chat_request

    messages = [
        Message(role="system", content="System prompt 1"),
        Message(role="system", content="System prompt 2"),
    ]

    with pytest.raises(ValueError, match="所有消息都是系统消息"):
        validate_chat_request(messages, req_id="req202")


def test_validate_chat_request_req_id_in_error_message():
    """
    测试场景: 验证错误消息包含 req_id
    验证: 错误追踪
    """
    from api_utils.utils_ext.validation import validate_chat_request

    try:
        validate_chat_request(messages=[], req_id="req303")
        pytest.fail("Expected ValueError")
    except ValueError as e:
        assert "[req303]" in str(e)


def test_validate_chat_request_mixed_messages_valid():
    """
    测试场景: 复杂的消息历史（系统、用户、助手混合）
    验证: 有效请求
    """
    from api_utils.utils_ext.validation import validate_chat_request

    messages = [
        Message(role="system", content="Context"),
        Message(role="user", content="Question 1"),
        Message(role="assistant", content="Answer 1"),
        Message(role="system", content="Additional context"),
        Message(role="user", content="Question 2"),
    ]

    result = validate_chat_request(messages, req_id="req404")

    assert result["error"] is None
    assert result["warning"] is None
