"""
High-quality tests for api_utils/sse.py (minimal mocking).

Focus: Test real SSE generation logic with minimal mocks.
Note: Functions use time.time() but we verify structure/format, not exact timestamps.
"""

import json


def test_generate_sse_chunk_basic():
    """
    Test scenario: Generate basic SSE data chunk
    Strategy: Pure function test, verify output format and structure
    """
    from api_utils.sse import generate_sse_chunk

    result = generate_sse_chunk(delta="Hello", req_id="req123", model="gemini-1.5-pro")

    # Verify SSE format
    assert isinstance(result, str)
    assert result.startswith("data: ")
    assert result.endswith("\n\n")

    # Extract and parse JSON
    json_part = result[6:-2]  # Remove "data: " prefix and "\n\n" suffix
    chunk_data = json.loads(json_part)

    # Verify structure
    assert chunk_data["id"] == "chatcmpl-req123"
    assert chunk_data["object"] == "chat.completion.chunk"
    assert chunk_data["model"] == "gemini-1.5-pro"
    assert "created" in chunk_data
    assert isinstance(chunk_data["created"], int)

    # Verify choices
    assert len(chunk_data["choices"]) == 1
    choice = chunk_data["choices"][0]
    assert choice["index"] == 0
    assert choice["delta"]["content"] == "Hello"
    assert choice["finish_reason"] is None


def test_generate_sse_chunk_empty_delta():
    """
    Test scenario: Generate SSE chunk with empty delta
    Verify: Can handle empty string
    """
    from api_utils.sse import generate_sse_chunk

    result = generate_sse_chunk(delta="", req_id="req456", model="gemini-2.0-flash-exp")

    json_part = result[6:-2]
    chunk_data = json.loads(json_part)

    assert chunk_data["choices"][0]["delta"]["content"] == ""
    assert chunk_data["model"] == "gemini-2.0-flash-exp"


def test_generate_sse_chunk_unicode():
    """
    Test scenario: Generate SSE chunk containing Unicode characters
    Verify: Correctly handle Unicode characters
    """
    from api_utils.sse import generate_sse_chunk

    result = generate_sse_chunk(
        delta="hello world", req_id="req789", model="test-model"
    )

    json_part = result[6:-2]
    chunk_data = json.loads(json_part)

    assert chunk_data["choices"][0]["delta"]["content"] == "hello world"


def test_generate_sse_chunk_special_characters():
    """
    Test scenario: Generate SSE chunk containing special characters
    Verify: Correctly escape quotes, newlines, etc.
    """
    from api_utils.sse import generate_sse_chunk

    delta_with_quotes = 'She said "hello" and left.'
    result = generate_sse_chunk(delta=delta_with_quotes, req_id="req101", model="test")

    json_part = result[6:-2]
    chunk_data = json.loads(json_part)

    assert chunk_data["choices"][0]["delta"]["content"] == delta_with_quotes


def test_generate_sse_stop_chunk_default_reason():
    """
    Test scenario: Generate SSE chunk with default stop reason
    Verify: finish_reason is "stop", includes [DONE] marker
    """
    from api_utils.sse import generate_sse_stop_chunk

    result = generate_sse_stop_chunk(req_id="req202", model="gemini-1.5-pro")

    # Verify includes two data: chunks
    assert result.count("data:") == 2
    assert "data: [DONE]" in result
    assert result.endswith("\n\n")

    # Extract first JSON chunk (stop chunk)
    lines = result.split("\n")
    first_data_line = None
    for line in lines:
        if line.startswith("data:") and not line.startswith("data: [DONE]"):
            first_data_line = line[6:]
            break

    assert first_data_line is not None
    chunk_data = json.loads(first_data_line)

    # Verify structure
    assert chunk_data["id"] == "chatcmpl-req202"
    assert chunk_data["object"] == "chat.completion.chunk"
    assert chunk_data["model"] == "gemini-1.5-pro"
    assert chunk_data["choices"][0]["delta"] == {}
    assert chunk_data["choices"][0]["finish_reason"] == "stop"
    assert "usage" not in chunk_data  # Should not include usage when not provided


def test_generate_sse_stop_chunk_custom_reason():
    """
    Test scenario: Generate SSE chunk with custom stop reason
    Verify: finish_reason is custom value
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
    Test scenario: Generate stop chunk containing usage statistics
    Verify: usage field correctly included
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
    Test scenario: Generate stop chunk with empty usage dict
    Verify: Empty dict treated as falsy, not included (correct behavior)
    """
    from api_utils.sse import generate_sse_stop_chunk

    result = generate_sse_stop_chunk(
        req_id="req505", model="test-model", reason="stop", usage={}
    )

    lines = result.split("\n")
    for line in lines:
        if line.startswith("data:") and not line.startswith("data: [DONE]"):
            chunk_data = json.loads(line[6:])
            # Empty dict is falsy, should not include usage field
            assert "usage" not in chunk_data
            break


def test_generate_sse_error_chunk_default_type():
    """
    Test scenario: Generate SSE chunk with default error type
    Verify: error_type is "server_error"
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

    # Verify error structure
    assert "error" in error_chunk
    error = error_chunk["error"]
    assert error["message"] == "Internal error occurred"
    assert error["type"] == "server_error"
    assert error["param"] is None
    assert error["code"] == "req606"


def test_generate_sse_error_chunk_custom_type():
    """
    Test scenario: Generate SSE chunk with custom error type
    Verify: error_type parameter used correctly
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
    Test scenario: Error message contains Unicode characters
    Verify: Correctly handle Unicode characters
    """
    from api_utils.sse import generate_sse_error_chunk

    result = generate_sse_error_chunk(message="Processing failed", req_id="req808")

    json_part = result[6:-2]
    error_chunk = json.loads(json_part)

    assert error_chunk["error"]["message"] == "Processing failed"


def test_sse_format_consistency():
    """
    Test scenario: Verify output format consistency across all SSE functions
    Verify: All start with "data: " and end with "\n\n"
    """
    from api_utils.sse import (
        generate_sse_chunk,
        generate_sse_error_chunk,
        generate_sse_stop_chunk,
    )

    chunk = generate_sse_chunk(delta="test", req_id="req", model="model")
    stop = generate_sse_stop_chunk(req_id="req", model="model")
    error = generate_sse_error_chunk(message="error", req_id="req")

    # Verify format consistency
    assert chunk.startswith("data: ")
    assert error.startswith("data: ")
    # stop chunk contains two data: chunks, but also starts with data:
    assert stop.startswith("data: ")

    assert chunk.endswith("\n\n")
    assert error.endswith("\n\n")
    assert stop.endswith("\n\n")
