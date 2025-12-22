"""
High-quality tests for api_utils/utils.py - Latest user text extraction (zero mocking).

Focus: Test _get_latest_user_text with pure function testing (no mocks).
Strategy: Comprehensive edge case coverage for message content extraction.
"""

from typing import List, cast

from models import Message, MessageContentItem


def test_get_latest_user_text_empty_messages():
    """
    Test scenario: Empty message list
    Expected: Return empty string
    """
    from api_utils.utils import _get_latest_user_text

    result = _get_latest_user_text([])

    assert result == ""


def test_get_latest_user_text_no_user_messages():
    """
    Test scenario: No user messages in message list
    Expected: Return empty string
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(role="system", content="System prompt"),
        Message(role="assistant", content="AI response"),
    ]

    result = _get_latest_user_text(messages)

    assert result == ""


def test_get_latest_user_text_single_user_message_string():
    """
    Test scenario: Single user message, content as string
    Expected: Return that string
    """
    from api_utils.utils import _get_latest_user_text

    messages = [Message(role="user", content="Hello, world!")]

    result = _get_latest_user_text(messages)

    assert result == "Hello, world!"


def test_get_latest_user_text_multiple_user_messages_returns_latest():
    """
    Test scenario: Multiple user messages
    Expected: Return content of the last user message
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(role="user", content="First message"),
        Message(role="assistant", content="Response"),
        Message(role="user", content="Second message"),
        Message(role="assistant", content="Another response"),
        Message(role="user", content="Latest message"),
    ]

    result = _get_latest_user_text(messages)

    assert result == "Latest message"


def test_get_latest_user_text_mixed_roles_returns_latest_user():
    """
    Test scenario: Mixed role messages (system, user, assistant)
    Expected: Return the last user message
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(role="system", content="System"),
        Message(role="user", content="User 1"),
        Message(role="assistant", content="AI 1"),
        Message(role="system", content="More system"),
        Message(role="user", content="User 2"),
        Message(role="assistant", content="AI 2"),
    ]

    result = _get_latest_user_text(messages)

    assert result == "User 2"


def test_get_latest_user_text_list_content_with_text_items():
    """
    Test scenario: User message content as list (containing text items)
    Expected: Concatenate all text items, joined by newline
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(
            role="user",
            content=cast(
                List[MessageContentItem],
                [
                    {"type": "text", "text": "First part"},
                    {"type": "text", "text": "Second part"},
                    {"type": "text", "text": "Third part"},
                ],
            ),
        )
    ]

    result = _get_latest_user_text(messages)

    assert result == "First part\nSecond part\nThird part"


def test_get_latest_user_text_list_content_with_mixed_types():
    """
    Test scenario: List content contains text and other types (e.g. image_url)
    Expected: Only extract text type content
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(
            role="user",
            content=cast(
                List[MessageContentItem],
                [
                    {"type": "text", "text": "Text before image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "http://example.com/img.jpg"},
                    },
                    {"type": "text", "text": "Text after image"},
                ],
            ),
        )
    ]

    result = _get_latest_user_text(messages)

    assert result == "Text before image\nText after image"


def test_get_latest_user_text_list_content_empty_text():
    """
    Test scenario: List content has empty text items
    Expected: Skip empty text items
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(
            role="user",
            content=cast(
                List[MessageContentItem],
                [
                    {"type": "text", "text": ""},
                    {"type": "text", "text": "Non-empty"},
                    {"type": "text", "text": ""},
                ],
            ),
        )
    ]

    result = _get_latest_user_text(messages)

    assert result == "Non-empty"


def test_get_latest_user_text_list_content_no_text_items():
    """
    Test scenario: List content has no text type items
    Expected: Return empty string
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(
            role="user",
            content=cast(
                List[MessageContentItem],
                [
                    {
                        "type": "image_url",
                        "image_url": {"url": "http://example.com/img.jpg"},
                    },
                ],
            ),
        )
    ]

    result = _get_latest_user_text(messages)

    assert result == ""


def test_get_latest_user_text_list_content_empty_list():
    """
    Test scenario: Content is an empty list
    Expected: Return empty string
    """
    from api_utils.utils import _get_latest_user_text

    messages = [Message(role="user", content=[])]

    result = _get_latest_user_text(messages)

    assert result == ""


def test_get_latest_user_text_content_is_none():
    """
    Test scenario: Content is None (though unusual)
    Expected: Return empty string
    """
    from api_utils.utils import _get_latest_user_text

    # Directly construct a case where content is None (bypass Pydantic validation)
    class MockMessage:
        def __init__(self):
            self.role = "user"
            self.content = None

    messages = [MockMessage()]

    result = _get_latest_user_text(cast(List[Message], messages))

    # Function will enter else branch and return ""
    assert result == ""


def test_get_latest_user_text_unicode_content():
    """
    Test scenario: Content contains Unicode characters
    Expected: Correctly handle Unicode characters
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(role="user", content="hello world"),
        Message(role="assistant", content="Response"),
        Message(role="user", content="latest message"),
    ]

    result = _get_latest_user_text(messages)

    assert result == "latest message"


def test_get_latest_user_text_multiline_string():
    """
    Test scenario: Content is multiline string
    Expected: Return full multiline string
    """
    from api_utils.utils import _get_latest_user_text

    multiline = """Line 1
Line 2
Line 3"""

    messages = [Message(role="user", content=multiline)]

    result = _get_latest_user_text(messages)

    assert result == multiline


def test_get_latest_user_text_reversed_iteration():
    """
    Test scenario: Verify function iterates messages backwards
    Expected: Should return the last user message even if there are other user messages before it
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(role="user", content="Old message 1"),
        Message(role="user", content="Old message 2"),
        Message(role="assistant", content="Response"),
        Message(role="user", content="Latest message"),
    ]

    result = _get_latest_user_text(messages)

    assert result == "Latest message"


def test_get_latest_user_text_special_characters():
    """
    Test scenario: Content contains special characters
    Expected: Correctly preserve special characters
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(
            role="user",
            content="Text with \"quotes\" and 'apostrophes' and \\backslashes\\",
        )
    ]

    result = _get_latest_user_text(messages)

    assert result == "Text with \"quotes\" and 'apostrophes' and \\backslashes\\"


def test_get_latest_user_text_very_long_content():
    """
    Test scenario: Very long content (performance test)
    Expected: Able to handle large text
    """
    from api_utils.utils import _get_latest_user_text

    # Create a 10,000 character long text
    long_text = "A" * 10000

    messages = [Message(role="user", content=long_text)]

    result = _get_latest_user_text(messages)

    assert result == long_text
    assert len(result) == 10000
