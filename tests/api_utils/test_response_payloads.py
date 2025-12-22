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
    Test scenario: Construct basic response (no optional parameters)
    Expected: Return complete chat.completion response, without seed and response_format (lines 18-34)
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

    # Verify: Basic structure (lines 19-34)
    assert response["object"] == "chat.completion"
    assert response["created"] == 1234567890
    assert response["model"] == "gemini-1.5-pro"
    assert response["system_fingerprint"] == "camoufox-proxy"

    # Verify: ID format (line 20)
    assert response["id"] == f"{CHAT_COMPLETION_ID_PREFIX}test-req-123-1234567890"
    assert response["id"].startswith(CHAT_COMPLETION_ID_PREFIX)

    # Verify: choices array (lines 24-31)
    assert len(response["choices"]) == 1
    choice = response["choices"][0]
    assert choice["index"] == 0
    assert choice["message"] == message_payload
    assert choice["finish_reason"] == "stop"
    assert choice["native_finish_reason"] == "stop"

    # Verify: usage (line 32)
    assert response["usage"] == usage_stats

    # Verify: Does not include optional fields
    assert "seed" not in response
    assert "response_format" not in response


def test_build_chat_completion_response_json_with_seed():
    """
    Test scenario: Include seed parameter
    Expected: Response contains seed field (lines 35-36)
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

    # Verify: seed field exists (line 36)
    assert "seed" in response
    assert response["seed"] == 42


def test_build_chat_completion_response_json_with_response_format():
    """
    Test scenario: Include response_format parameter
    Expected: Response contains response_format field (lines 37-38)
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

    # Verify: response_format field exists (line 38)
    assert "response_format" in response
    assert response["response_format"] == {"type": "json_object"}


def test_build_chat_completion_response_json_with_both_optional_params():
    """
    Test scenario: Include both seed and response_format
    Expected: Both optional fields exist (lines 35-38)
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

    # Verify: Both optional fields exist
    assert "seed" in response
    assert response["seed"] == 999
    assert "response_format" in response
    assert response["response_format"] == {"type": "text"}


def test_build_chat_completion_response_json_seed_none_not_included():
    """
    Test scenario: seed=None (explicitly passed)
    Expected: seed field not included in response (condition at line 35 is False)
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

    # Verify: seed not included
    assert "seed" not in response


def test_build_chat_completion_response_json_response_format_none_not_included():
    """
    Test scenario: response_format=None (explicitly passed)
    Expected: response_format field not included in response (condition at line 37 is False)
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

    # Verify: response_format not included
    assert "response_format" not in response


def test_build_chat_completion_response_json_custom_system_fingerprint():
    """
    Test scenario: Custom system_fingerprint
    Expected: Use provided value instead of default (line 33)
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

    # Verify: Custom system_fingerprint
    assert response["system_fingerprint"] == "custom-fingerprint-123"


def test_build_chat_completion_response_json_different_finish_reasons():
    """
    Test scenario: Different finish_reason values
    Expected: Both finish_reason and native_finish_reason set correctly (lines 28-29)
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
    Test scenario: Verify timestamp format
    Expected: created field is an integer timestamp (line 18, 22)
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

    # Verify: created is an integer (line 18 using int())
    assert isinstance(response["created"], int)
    assert response["created"] == 1234567890


def test_build_chat_completion_response_json_id_includes_timestamp():
    """
    Test scenario: Verify ID contains timestamp
    Expected: ID format is prefix-req_id-timestamp (line 20)
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

    # Verify: ID contains timestamp
    assert response["id"] == f"{CHAT_COMPLETION_ID_PREFIX}unique-req-9999999999"
    assert "9999999999" in response["id"]


def test_build_chat_completion_response_json_message_payload_structure():
    """
    Test scenario: Verify message_payload passed as is
    Expected: message field is exactly equal to message_payload (line 27)
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

    # Verify: message_payload passed as is
    assert response["choices"][0]["message"] == message_payload
    assert response["choices"][0]["message"]["tool_calls"][0]["id"] == "call_123"


def test_build_chat_completion_response_json_usage_stats_structure():
    """
    Test scenario: Verify usage_stats passed as is
    Expected: usage field is exactly equal to usage_stats (line 32)
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

    # Verify: usage_stats passed as is, including extra fields
    assert response["usage"] == usage_stats
    assert response["usage"]["prompt_tokens_details"]["cached_tokens"] == 20
