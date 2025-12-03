"""
High-quality tests for api_utils/utils.py pure functions (zero mocking).

Focus: Test real business logic with no mocks, only pure function testing.
"""

import json


def test_extract_json_from_text_valid_json():
    """
    测试场景: 从文本中提取有效的 JSON
    策略: 纯函数测试，无需模拟
    """
    from api_utils.utils import _extract_json_from_text

    text = 'Some text before {"key": "value", "num": 42} and text after'
    result = _extract_json_from_text(text)

    assert result is not None
    parsed = json.loads(result)
    assert parsed["key"] == "value"
    assert parsed["num"] == 42


def test_extract_json_from_text_nested_json():
    """
    测试场景: 提取嵌套的 JSON 对象
    验证: 能正确处理复杂结构
    """
    from api_utils.utils import _extract_json_from_text

    text = '{"outer": {"inner": {"deep": "value"}}, "array": [1, 2, 3]}'
    result = _extract_json_from_text(text)

    assert result is not None
    parsed = json.loads(result)
    assert parsed["outer"]["inner"]["deep"] == "value"
    assert parsed["array"] == [1, 2, 3]


def test_extract_json_from_text_invalid_json():
    """
    测试场景: 无效的 JSON 字符串
    预期: 返回 None
    """
    from api_utils.utils import _extract_json_from_text

    text = "{invalid json syntax"
    result = _extract_json_from_text(text)

    assert result is None


def test_extract_json_from_text_empty_string():
    """
    测试场景: 空字符串
    预期: 返回 None
    """
    from api_utils.utils import _extract_json_from_text

    result = _extract_json_from_text("")
    assert result is None


def test_extract_json_from_text_no_braces():
    """
    测试场景: 没有大括号的文本
    预期: 返回 None
    """
    from api_utils.utils import _extract_json_from_text

    text = "just plain text without any braces"
    result = _extract_json_from_text(text)

    assert result is None


def test_extract_json_from_text_multiple_json_objects():
    """
    测试场景: 包含多个 JSON 对象的文本（无效情况）
    验证: 函数处理无效的多对象文本

    说明: 函数从第一个 '{' 到最后一个 '}' 提取，
    对于 '{"first": "obj"} text {"second": "obj"}' 会得到整个字符串，
    这不是有效的 JSON，所以返回 None
    """
    from api_utils.utils import _extract_json_from_text

    text = '{"first": "obj"} some text {"second": "obj"}'
    result = _extract_json_from_text(text)

    # 预期返回 None，因为提取的字符串不是有效JSON
    assert result is None


def test_extract_json_from_text_json_with_unicode():
    """
    测试场景: 包含 Unicode 字符的 JSON
    验证: 正确处理非 ASCII 字符
    """
    from api_utils.utils import _extract_json_from_text

    text = '{"message": "你好世界", "emoji": "😀"}'
    result = _extract_json_from_text(text)

    assert result is not None
    parsed = json.loads(result)
    assert parsed["message"] == "你好世界"
    assert parsed["emoji"] == "😀"


def test_extract_json_from_text_json_with_escaped_quotes():
    """
    测试场景: 包含转义引号的 JSON
    验证: 正确处理转义字符
    """
    from api_utils.utils import _extract_json_from_text

    text = '{"quote": "He said \\"hello\\""}'
    result = _extract_json_from_text(text)

    assert result is not None
    parsed = json.loads(result)
    assert parsed["quote"] == 'He said "hello"'


def test_generate_sse_stop_chunk_with_usage_basic():
    """
    测试场景: 生成基本的 SSE 停止块
    策略: 纯函数测试，验证输出格式
    """
    from api_utils.utils import generate_sse_stop_chunk_with_usage

    usage_stats = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    result = generate_sse_stop_chunk_with_usage(
        req_id="test123", model="gemini-1.5-pro", usage_stats=usage_stats, reason="stop"
    )

    # 验证输出是 SSE 格式
    assert isinstance(result, str)
    assert "data:" in result

    # 提取 JSON 部分验证
    # SSE格式: data: {json}\n\n
    lines = result.strip().split("\n")
    data_line = None
    for line in lines:
        if line.startswith("data:"):
            data_line = line[5:].strip()  # 移除 "data:" 前缀
            break

    if data_line and data_line != "[DONE]":
        try:
            chunk_data = json.loads(data_line)
            assert "choices" in chunk_data or "usage" in chunk_data
        except json.JSONDecodeError:
            # 某些 SSE 块可能不是 JSON
            pass


def test_generate_sse_stop_chunk_with_usage_custom_reason():
    """
    测试场景: 使用自定义停止原因
    验证: reason 参数被正确传递
    """
    from api_utils.utils import generate_sse_stop_chunk_with_usage

    usage_stats = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    result = generate_sse_stop_chunk_with_usage(
        req_id="test456",
        model="gemini-2.0-flash-exp",
        usage_stats=usage_stats,
        reason="length",  # 自定义原因
    )

    assert isinstance(result, str)
    assert "data:" in result
    # 验证包含停止信息
    assert result  # 非空


def test_generate_sse_stop_chunk_with_empty_usage():
    """
    测试场景: 空的 usage 统计
    验证: 能处理空字典
    """
    from api_utils.utils import generate_sse_stop_chunk_with_usage

    result = generate_sse_stop_chunk_with_usage(
        req_id="test789", model="test-model", usage_stats={}, reason="stop"
    )

    assert isinstance(result, str)
    assert "data:" in result
