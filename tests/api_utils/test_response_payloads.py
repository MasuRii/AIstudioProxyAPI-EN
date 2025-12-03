"""
High-quality tests for api_utils/response_payloads.py - Response construction.

Focus: Test build_chat_completion_response_json with all parameter combinations.
Strategy: Test required fields, optional parameters (seed, response_format), structure validation.
"""

from unittest.mock import patch

from api_utils.response_payloads import build_chat_completion_response_json
from config import CHAT_COMPLETION_ID_PREFIX


def test_build_chat_completion_response_json_basic():
    """
    测试场景: 构造基本响应 (无可选参数)
    预期: 返回完整的 chat.completion 响应,不包含 seed 和 response_format (lines 18-34)
    """
    message_payload = {"role": "assistant", "content": "Hello, how can I help?"}
    usage_stats = {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17}

    with patch("time.time", return_value=1234567890.5):
        response = build_chat_completion_response_json(
            req_id="test-req-123",
            model_name="gemini-1.5-pro",
            message_payload=message_payload,
            finish_reason="stop",
            usage_stats=usage_stats,
        )

    # 验证: 基本结构 (lines 19-34)
    assert response["object"] == "chat.completion"
    assert response["created"] == 1234567890
    assert response["model"] == "gemini-1.5-pro"
    assert response["system_fingerprint"] == "camoufox-proxy"

    # 验证: ID 格式 (line 20)
    assert response["id"] == f"{CHAT_COMPLETION_ID_PREFIX}test-req-123-1234567890"
    assert response["id"].startswith(CHAT_COMPLETION_ID_PREFIX)

    # 验证: choices 数组 (lines 24-31)
    assert len(response["choices"]) == 1
    choice = response["choices"][0]
    assert choice["index"] == 0
    assert choice["message"] == message_payload
    assert choice["finish_reason"] == "stop"
    assert choice["native_finish_reason"] == "stop"

    # 验证: usage (line 32)
    assert response["usage"] == usage_stats

    # 验证: 不包含可选字段
    assert "seed" not in response
    assert "response_format" not in response


def test_build_chat_completion_response_json_with_seed():
    """
    测试场景: 包含 seed 参数
    预期: 响应包含 seed 字段 (lines 35-36)
    """
    message_payload = {"role": "assistant", "content": "Test"}
    usage_stats = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}

    response = build_chat_completion_response_json(
        req_id="req-456",
        model_name="gemini-2.0-flash",
        message_payload=message_payload,
        finish_reason="stop",
        usage_stats=usage_stats,
        seed=42,
    )

    # 验证: seed 字段存在 (line 36)
    assert "seed" in response
    assert response["seed"] == 42


def test_build_chat_completion_response_json_with_response_format():
    """
    测试场景: 包含 response_format 参数
    预期: 响应包含 response_format 字段 (lines 37-38)
    """
    message_payload = {"role": "assistant", "content": '{"result": "json"}'}
    usage_stats = {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13}
    response_format = {"type": "json_object"}

    response = build_chat_completion_response_json(
        req_id="req-789",
        model_name="gemini-1.5-pro",
        message_payload=message_payload,
        finish_reason="stop",
        usage_stats=usage_stats,
        response_format=response_format,
    )

    # 验证: response_format 字段存在 (line 38)
    assert "response_format" in response
    assert response["response_format"] == {"type": "json_object"}


def test_build_chat_completion_response_json_with_both_optional_params():
    """
    测试场景: 同时包含 seed 和 response_format
    预期: 两个可选字段都存在 (lines 35-38)
    """
    message_payload = {"role": "assistant", "content": "Full response"}
    usage_stats = {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
    response_format = {"type": "text"}

    response = build_chat_completion_response_json(
        req_id="req-full",
        model_name="gemini-2.0-flash-thinking-exp",
        message_payload=message_payload,
        finish_reason="length",
        usage_stats=usage_stats,
        seed=999,
        response_format=response_format,
    )

    # 验证: 两个可选字段都存在
    assert "seed" in response
    assert response["seed"] == 999
    assert "response_format" in response
    assert response["response_format"] == {"type": "text"}


def test_build_chat_completion_response_json_seed_none_not_included():
    """
    测试场景: seed=None (显式传递)
    预期: seed 字段不包含在响应中 (line 35 条件为 False)
    """
    message_payload = {"role": "assistant", "content": "Test"}
    usage_stats = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}

    response = build_chat_completion_response_json(
        req_id="req-none",
        model_name="gemini-1.5-pro",
        message_payload=message_payload,
        finish_reason="stop",
        usage_stats=usage_stats,
        seed=None,
    )

    # 验证: seed 不包含
    assert "seed" not in response


def test_build_chat_completion_response_json_response_format_none_not_included():
    """
    测试场景: response_format=None (显式传递)
    预期: response_format 字段不包含在响应中 (line 37 条件为 False)
    """
    message_payload = {"role": "assistant", "content": "Test"}
    usage_stats = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}

    response = build_chat_completion_response_json(
        req_id="req-none2",
        model_name="gemini-1.5-pro",
        message_payload=message_payload,
        finish_reason="stop",
        usage_stats=usage_stats,
        response_format=None,
    )

    # 验证: response_format 不包含
    assert "response_format" not in response


def test_build_chat_completion_response_json_custom_system_fingerprint():
    """
    测试场景: 自定义 system_fingerprint
    预期: 使用提供的值而非默认值 (line 33)
    """
    message_payload = {"role": "assistant", "content": "Test"}
    usage_stats = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}

    response = build_chat_completion_response_json(
        req_id="req-custom",
        model_name="gemini-1.5-pro",
        message_payload=message_payload,
        finish_reason="stop",
        usage_stats=usage_stats,
        system_fingerprint="custom-fingerprint-123",
    )

    # 验证: 自定义 system_fingerprint
    assert response["system_fingerprint"] == "custom-fingerprint-123"


def test_build_chat_completion_response_json_different_finish_reasons():
    """
    测试场景: 不同的 finish_reason 值
    预期: finish_reason 和 native_finish_reason 都设置正确 (lines 28-29)
    """
    message_payload = {"role": "assistant", "content": "Test"}
    usage_stats = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}

    # Test "length" finish reason
    response1 = build_chat_completion_response_json(
        req_id="req-length",
        model_name="gemini-1.5-pro",
        message_payload=message_payload,
        finish_reason="length",
        usage_stats=usage_stats,
    )
    assert response1["choices"][0]["finish_reason"] == "length"
    assert response1["choices"][0]["native_finish_reason"] == "length"

    # Test "tool_calls" finish reason
    response2 = build_chat_completion_response_json(
        req_id="req-tools",
        model_name="gemini-1.5-pro",
        message_payload=message_payload,
        finish_reason="tool_calls",
        usage_stats=usage_stats,
    )
    assert response2["choices"][0]["finish_reason"] == "tool_calls"
    assert response2["choices"][0]["native_finish_reason"] == "tool_calls"


def test_build_chat_completion_response_json_timestamp_format():
    """
    测试场景: 验证时间戳格式
    预期: created 字段是整数时间戳 (line 18, 22)
    """
    message_payload = {"role": "assistant", "content": "Test"}
    usage_stats = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}

    # Mock time.time() to return a fractional timestamp
    with patch("time.time", return_value=1234567890.789):
        response = build_chat_completion_response_json(
            req_id="req-ts",
            model_name="gemini-1.5-pro",
            message_payload=message_payload,
            finish_reason="stop",
            usage_stats=usage_stats,
        )

    # 验证: created 是整数 (line 18 使用 int())
    assert isinstance(response["created"], int)
    assert response["created"] == 1234567890


def test_build_chat_completion_response_json_id_includes_timestamp():
    """
    测试场景: 验证 ID 包含时间戳
    预期: ID 格式为 prefix-req_id-timestamp (line 20)
    """
    message_payload = {"role": "assistant", "content": "Test"}
    usage_stats = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}

    with patch("time.time", return_value=9999999999.0):
        response = build_chat_completion_response_json(
            req_id="unique-req",
            model_name="gemini-1.5-pro",
            message_payload=message_payload,
            finish_reason="stop",
            usage_stats=usage_stats,
        )

    # 验证: ID 包含时间戳
    assert response["id"] == f"{CHAT_COMPLETION_ID_PREFIX}unique-req-9999999999"
    assert "9999999999" in response["id"]


def test_build_chat_completion_response_json_message_payload_structure():
    """
    测试场景: 验证 message_payload 原样传递
    预期: message 字段完全等于 message_payload (line 27)
    """
    # Complex message with tool_calls
    message_payload = {
        "role": "assistant",
        "content": "I'll help with that.",
        "tool_calls": [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "search", "arguments": '{"query": "test"}'},
            }
        ],
    }
    usage_stats = {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25}

    response = build_chat_completion_response_json(
        req_id="req-complex",
        model_name="gemini-1.5-pro",
        message_payload=message_payload,
        finish_reason="tool_calls",
        usage_stats=usage_stats,
    )

    # 验证: message_payload 原样传递
    assert response["choices"][0]["message"] == message_payload
    assert response["choices"][0]["message"]["tool_calls"][0]["id"] == "call_123"


def test_build_chat_completion_response_json_usage_stats_structure():
    """
    测试场景: 验证 usage_stats 原样传递
    预期: usage 字段完全等于 usage_stats (line 32)
    """
    message_payload = {"role": "assistant", "content": "Test"}
    usage_stats = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "prompt_tokens_details": {"cached_tokens": 20},
    }

    response = build_chat_completion_response_json(
        req_id="req-usage",
        model_name="gemini-1.5-pro",
        message_payload=message_payload,
        finish_reason="stop",
        usage_stats=usage_stats,
    )

    # 验证: usage_stats 原样传递,包括额外字段
    assert response["usage"] == usage_stats
    assert response["usage"]["prompt_tokens_details"]["cached_tokens"] == 20
