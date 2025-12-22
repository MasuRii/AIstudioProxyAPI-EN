"""
High-quality tests for api_utils/utils_ext/validation.py (zero mocking).

Focus: Test real validation logic with no mocks, only pure function testing.
"""

import pytest

from models import Message


def test_validate_chat_request_valid():
    """
    Test scenario: Valid chat request (containing user message)
    Strategy: Pure function test, no mocking needed
    """
    from api_utils.utils_ext.validation import validate_chat_request

    messages = [Message(role="user", content="Hello")]

    result = validate_chat_request(messages, req_id="req123")

    assert result["error"] is None
    assert result["warning"] is None


def test_validate_chat_request_with_system_and_user():
    """
    Test scenario: Request containing system and user messages
    Verify: Valid request
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
    Test scenario: Conversation history containing assistant message
    Verify: Valid request
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
    Test scenario: messages array is empty
    Expected: Throw ValueError
    """
    from api_utils.utils_ext.validation import validate_chat_request

    with pytest.raises(ValueError, match="messages.*missing or empty"):
        validate_chat_request(messages=[], req_id="req101")


def test_validate_chat_request_only_system_messages():
    """
    Test scenario: Only system messages, no user or assistant messages
    Expected: Throw ValueError
    """
    from api_utils.utils_ext.validation import validate_chat_request

    messages = [
        Message(role="system", content="System prompt 1"),
        Message(role="system", content="System prompt 2"),
    ]

    with pytest.raises(ValueError, match="All messages are system messages"):
        validate_chat_request(messages, req_id="req202")


def test_validate_chat_request_req_id_in_error_message():
    """
    Test scenario: Verify error message contains req_id
    Verify: Error tracking
    """
    from api_utils.utils_ext.validation import validate_chat_request

    try:
        validate_chat_request(messages=[], req_id="req303")
        pytest.fail("Expected ValueError")
    except ValueError as e:
        assert "[req303]" in str(e)


def test_validate_chat_request_mixed_messages_valid():
    """
    Test scenario: Complex message history (mixed system, user, assistant)
    Verify: Valid request
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
