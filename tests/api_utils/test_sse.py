"""
High-quality tests for api_utils/sse.py (minimal mocking).

Focus: Test real SSE generation logic with minimal mocks.
Note: Functions use time.time() but we verify structure/format, not exact timestamps.
"""

import json


def test_generate_sse_chunk_basic():
    """
    测试场景: 生成基本的 SSE 数据块
    策略: 纯函数测试，验证输出格式和结构
    """
    from api_utils.sse import generate_sse_chunk

    result = generate_sse_chunk(delta="Hello", req_id="req123", model="gemini-1.5-pro")

    # 验证 SSE 格式
    assert isinstance(result, str)
    assert result.startswith("data: ")
    assert result.endswith("\n\n")

    # 提取并解析 JSON
    json_part = result[6:-2]  # Remove "data: " prefix and "\n\n" suffix
    chunk_data = json.loads(json_part)

    # 验证结构
    assert chunk_data["id"] == "chatcmpl-req123"
    assert chunk_data["object"] == "chat.completion.chunk"
    assert chunk_data["model"] == "gemini-1.5-pro"
    assert "created" in chunk_data
    assert isinstance(chunk_data["created"], int)

    # 验证 choices
    assert len(chunk_data["choices"]) == 1
    choice = chunk_data["choices"][0]
    assert choice["index"] == 0
    assert choice["delta"]["content"] == "Hello"
    assert choice["finish_reason"] is None


def test_generate_sse_chunk_empty_delta():
    """
    测试场景: 生成空 delta 的 SSE 块
    验证: 能处理空字符串
    """
    from api_utils.sse import generate_sse_chunk

    result = generate_sse_chunk(delta="", req_id="req456", model="gemini-2.0-flash-exp")

    json_part = result[6:-2]
    chunk_data = json.loads(json_part)

    assert chunk_data["choices"][0]["delta"]["content"] == ""
    assert chunk_data["model"] == "gemini-2.0-flash-exp"


def test_generate_sse_chunk_unicode():
    """
    测试场景: 生成包含 Unicode 字符的 SSE 块
    验证: 正确处理中文、emoji 等字符
    """
    from api_utils.sse import generate_sse_chunk

    result = generate_sse_chunk(
        delta="你好世界 😀", req_id="req789", model="test-model"
    )

    json_part = result[6:-2]
    chunk_data = json.loads(json_part)

    assert chunk_data["choices"][0]["delta"]["content"] == "你好世界 😀"


def test_generate_sse_chunk_special_characters():
    """
    测试场景: 生成包含特殊字符的 SSE 块
    验证: 正确转义引号、换行等
    """
    from api_utils.sse import generate_sse_chunk

    delta_with_quotes = 'She said "hello" and left.'
    result = generate_sse_chunk(delta=delta_with_quotes, req_id="req101", model="test")

    json_part = result[6:-2]
    chunk_data = json.loads(json_part)

    assert chunk_data["choices"][0]["delta"]["content"] == delta_with_quotes


def test_generate_sse_stop_chunk_default_reason():
    """
    测试场景: 生成默认停止原因的 SSE 块
    验证: finish_reason 为 "stop"，包含 [DONE] 标记
    """
    from api_utils.sse import generate_sse_stop_chunk

    result = generate_sse_stop_chunk(req_id="req202", model="gemini-1.5-pro")

    # 验证包含两个 data: 块
    assert result.count("data:") == 2
    assert "data: [DONE]" in result
    assert result.endswith("\n\n")

    # 提取第一个 JSON 块（stop chunk）
    lines = result.split("\n")
    first_data_line = None
    for line in lines:
        if line.startswith("data:") and not line.startswith("data: [DONE]"):
            first_data_line = line[6:]
            break

    assert first_data_line is not None
    chunk_data = json.loads(first_data_line)

    # 验证结构
    assert chunk_data["id"] == "chatcmpl-req202"
    assert chunk_data["object"] == "chat.completion.chunk"
    assert chunk_data["model"] == "gemini-1.5-pro"
    assert chunk_data["choices"][0]["delta"] == {}
    assert chunk_data["choices"][0]["finish_reason"] == "stop"
    assert "usage" not in chunk_data  # 无 usage 时不应包含该字段


def test_generate_sse_stop_chunk_custom_reason():
    """
    测试场景: 生成自定义停止原因的 SSE 块
    验证: finish_reason 为自定义值
    """
    from api_utils.sse import generate_sse_stop_chunk

    result = generate_sse_stop_chunk(
        req_id="req303", model="gemini-2.0-flash-exp", reason="length"
    )

    lines = result.split("\n")
    for line in lines:
        if line.startswith("data:") and not line.startswith("data: [DONE]"):
            chunk_data = json.loads(line[6:])
            assert chunk_data["choices"][0]["finish_reason"] == "length"
            break


def test_generate_sse_stop_chunk_with_usage():
    """
    测试场景: 生成包含 usage 统计的停止块
    验证: usage 字段被正确包含
    """
    from api_utils.sse import generate_sse_stop_chunk

    usage_stats = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    result = generate_sse_stop_chunk(
        req_id="req404", model="test-model", reason="stop", usage=usage_stats
    )

    lines = result.split("\n")
    for line in lines:
        if line.startswith("data:") and not line.startswith("data: [DONE]"):
            chunk_data = json.loads(line[6:])
            assert "usage" in chunk_data
            assert chunk_data["usage"] == usage_stats
            assert chunk_data["usage"]["prompt_tokens"] == 100
            assert chunk_data["usage"]["completion_tokens"] == 50
            assert chunk_data["usage"]["total_tokens"] == 150
            break


def test_generate_sse_stop_chunk_with_empty_usage():
    """
    测试场景: 生成包含空 usage 字典的停止块
    验证: 空字典被视为 falsy，不会被包含（正确行为）
    """
    from api_utils.sse import generate_sse_stop_chunk

    result = generate_sse_stop_chunk(
        req_id="req505", model="test-model", reason="stop", usage={}
    )

    lines = result.split("\n")
    for line in lines:
        if line.startswith("data:") and not line.startswith("data: [DONE]"):
            chunk_data = json.loads(line[6:])
            # 空字典是 falsy，不应包含 usage 字段
            assert "usage" not in chunk_data
            break


def test_generate_sse_error_chunk_default_type():
    """
    测试场景: 生成默认错误类型的 SSE 块
    验证: error_type 为 "server_error"
    """
    from api_utils.sse import generate_sse_error_chunk

    result = generate_sse_error_chunk(
        message="Internal error occurred", req_id="req606"
    )

    assert isinstance(result, str)
    assert result.startswith("data: ")
    assert result.endswith("\n\n")

    json_part = result[6:-2]
    error_chunk = json.loads(json_part)

    # 验证 error 结构
    assert "error" in error_chunk
    error = error_chunk["error"]
    assert error["message"] == "Internal error occurred"
    assert error["type"] == "server_error"
    assert error["param"] is None
    assert error["code"] == "req606"


def test_generate_sse_error_chunk_custom_type():
    """
    测试场景: 生成自定义错误类型的 SSE 块
    验证: error_type 参数被正确使用
    """
    from api_utils.sse import generate_sse_error_chunk

    result = generate_sse_error_chunk(
        message="Invalid API key", req_id="req707", error_type="authentication_error"
    )

    json_part = result[6:-2]
    error_chunk = json.loads(json_part)

    assert error_chunk["error"]["type"] == "authentication_error"
    assert error_chunk["error"]["message"] == "Invalid API key"


def test_generate_sse_error_chunk_unicode_message():
    """
    测试场景: 错误消息包含 Unicode 字符
    验证: 正确处理中文、emoji 等
    """
    from api_utils.sse import generate_sse_error_chunk

    result = generate_sse_error_chunk(message="处理失败 😢", req_id="req808")

    json_part = result[6:-2]
    error_chunk = json.loads(json_part)

    assert error_chunk["error"]["message"] == "处理失败 😢"


def test_sse_format_consistency():
    """
    测试场景: 验证所有 SSE 函数输出格式一致性
    验证: 都以 "data: " 开头，以 "\n\n" 结尾
    """
    from api_utils.sse import (
        generate_sse_chunk,
        generate_sse_error_chunk,
        generate_sse_stop_chunk,
    )

    chunk = generate_sse_chunk(delta="test", req_id="req", model="model")
    stop = generate_sse_stop_chunk(req_id="req", model="model")
    error = generate_sse_error_chunk(message="error", req_id="req")

    # 验证格式一致性
    assert chunk.startswith("data: ")
    assert error.startswith("data: ")
    # stop chunk 包含两个 data: 块，但也以 data: 开头
    assert stop.startswith("data: ")

    assert chunk.endswith("\n\n")
    assert error.endswith("\n\n")
    assert stop.endswith("\n\n")
