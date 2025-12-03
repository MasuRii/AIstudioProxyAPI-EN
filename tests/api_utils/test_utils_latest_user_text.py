"""
High-quality tests for api_utils/utils.py - Latest user text extraction (zero mocking).

Focus: Test _get_latest_user_text with pure function testing (no mocks).
Strategy: Comprehensive edge case coverage for message content extraction.
"""

from typing import List, cast

from models import Message, MessageContentItem


def test_get_latest_user_text_empty_messages():
    """
    测试场景: 空消息列表
    预期: 返回空字符串
    """
    from api_utils.utils import _get_latest_user_text

    result = _get_latest_user_text([])

    assert result == ""


def test_get_latest_user_text_no_user_messages():
    """
    测试场景: 消息列表中没有用户消息
    预期: 返回空字符串
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
    测试场景: 单条用户消息，内容为字符串
    预期: 返回该字符串
    """
    from api_utils.utils import _get_latest_user_text

    messages = [Message(role="user", content="Hello, world!")]

    result = _get_latest_user_text(messages)

    assert result == "Hello, world!"


def test_get_latest_user_text_multiple_user_messages_returns_latest():
    """
    测试场景: 多条用户消息
    预期: 返回最后一条用户消息的内容
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
    测试场景: 混合角色消息（system, user, assistant）
    预期: 返回最后一条用户消息
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
    测试场景: 用户消息内容为列表（包含文本项）
    预期: 拼接所有文本项，用换行符连接
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
    测试场景: 列表内容包含 text 和其他类型（如 image_url）
    预期: 只提取 text 类型的内容
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
    测试场景: 列表内容中有空文本项
    预期: 跳过空文本项
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
    测试场景: 列表内容中没有 text 类型项
    预期: 返回空字符串
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
    测试场景: 内容为空列表
    预期: 返回空字符串
    """
    from api_utils.utils import _get_latest_user_text

    messages = [Message(role="user", content=[])]

    result = _get_latest_user_text(messages)

    assert result == ""


def test_get_latest_user_text_content_is_none():
    """
    测试场景: 内容为 None（虽然不常见）
    预期: 返回空字符串
    """
    from api_utils.utils import _get_latest_user_text

    # 直接构造一个 content 为 None 的情况（绕过 Pydantic 验证）
    # 在实际中 Message 的 content 字段通常不会是 None，但函数应该能处理
    class MockMessage:
        def __init__(self):
            self.role = "user"
            self.content = None

    messages = [MockMessage()]

    result = _get_latest_user_text(cast(List[Message], messages))

    # 函数会进入 else 分支，返回 ""
    assert result == ""


def test_get_latest_user_text_unicode_content():
    """
    测试场景: 包含 Unicode 字符的内容
    预期: 正确处理中文、emoji 等
    """
    from api_utils.utils import _get_latest_user_text

    messages = [
        Message(role="user", content="你好世界 😀 🌍"),
        Message(role="assistant", content="Response"),
        Message(role="user", content="最新消息 🚀"),
    ]

    result = _get_latest_user_text(messages)

    assert result == "最新消息 🚀"


def test_get_latest_user_text_multiline_string():
    """
    测试场景: 内容为多行字符串
    预期: 返回完整的多行字符串
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
    测试场景: 验证函数从后向前遍历消息
    预期: 应该返回最后一条用户消息，即使前面有其他用户消息
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
    测试场景: 内容包含特殊字符
    预期: 正确保留特殊字符
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
    测试场景: 非常长的内容（性能测试）
    预期: 能够处理大文本
    """
    from api_utils.utils import _get_latest_user_text

    # 创建一个 10000 字符的长文本
    long_text = "A" * 10000

    messages = [Message(role="user", content=long_text)]

    result = _get_latest_user_text(messages)

    assert result == long_text
    assert len(result) == 10000
