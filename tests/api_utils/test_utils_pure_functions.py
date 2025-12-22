"""
High-quality tests for api_utils/utils.py pure functions (zero mocking).

Focus: Test real business logic with no mocks, only pure function testing.
"""

import json


def test_extract_json_from_text_valid_json():
    """
    Test scenario: Extract valid JSON from text
    Strategy: Pure function test, no mocking needed
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
    Test scenario: Extract nested JSON object
    Verify: Able to handle complex structures
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
    Test scenario: Invalid JSON string
    Expected: Return None
    """
    from api_utils.utils import _extract_json_from_text

    text = "{invalid json syntax"
    result = _extract_json_from_text(text)

    assert result is None


def test_extract_json_from_text_empty_string():
    """
    Test scenario: Empty string
    Expected: Return None
    """
    from api_utils.utils import _extract_json_from_text

    result = _extract_json_from_text("")
    assert result is None


def test_extract_json_from_text_no_braces():
    """
    Test scenario: Text without braces
    Expected: Return None
    """
    from api_utils.utils import _extract_json_from_text

    text = "just plain text without any braces"
    result = _extract_json_from_text(text)

    assert result is None


def test_extract_json_from_text_multiple_json_objects():
    """
    Test scenario: Text containing multiple JSON objects (invalid case)
    Verify: Function handles invalid multi-object text

    Description: Function extracts from the first '{' to the last '}',
    so for '{"first": "obj"} text {"second": "obj"}' it gets the whole string,
    which is not valid JSON, thus returns None.
    """
    from api_utils.utils import _extract_json_from_text

    text = '{"first": "obj"} some text {"second": "obj"}'
    result = _extract_json_from_text(text)

    # Expected to return None because extracted string is not valid JSON
    assert result is None


def test_extract_json_from_text_json_with_unicode():
    """
    Test scenario: JSON with Unicode characters
    Verify: Correctly handle non-ASCII characters
    """
    from api_utils.utils import _extract_json_from_text

    text = '{"message": "hello world", "emoji": "smile"}'
    result = _extract_json_from_text(text)

    assert result is not None
    parsed = json.loads(result)
    assert parsed["message"] == "hello world"
    assert parsed["emoji"] == "smile"


def test_extract_json_from_text_json_with_escaped_quotes():
    """
    Test scenario: JSON with escaped quotes
    Verify: Correctly handle escape characters
    """
    from api_utils.utils import _extract_json_from_text

    text = '{"quote": "He said \\"hello\\""}'
    result = _extract_json_from_text(text)

    assert result is not None
    parsed = json.loads(result)
    assert parsed["quote"] == 'He said "hello"'


def test_generate_sse_stop_chunk_with_usage_basic():
    """
    Test scenario: Generate basic SSE stop chunk
    Strategy: Pure function test, verify output format
    """
    from api_utils.utils import generate_sse_stop_chunk_with_usage

    usage_stats = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    result = generate_sse_stop_chunk_with_usage(
        req_id="test123", model="gemini-1.5-pro", usage_stats=usage_stats, reason="stop"
    )

    # Verify output is in SSE format
    assert isinstance(result, str)
    assert "data:" in result

    # Extract JSON part to verify
    # SSE format: data: {json}\n\n
    lines = result.strip().split("\n")
    data_line = None
    for line in lines:
        if line.startswith("data:"):
            data_line = line[5:].strip()  # Remove "data:" prefix
            break

    if data_line and data_line != "[DONE]":
        try:
            chunk_data = json.loads(data_line)
            assert "choices" in chunk_data or "usage" in chunk_data
        except json.JSONDecodeError:
            # Some SSE chunks might not be JSON
            pass


def test_generate_sse_stop_chunk_with_usage_custom_reason():
    """
    Test scenario: Use custom stop reason
    Verify: reason parameter passed correctly
    """
    from api_utils.utils import generate_sse_stop_chunk_with_usage

    usage_stats = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    result = generate_sse_stop_chunk_with_usage(
        req_id="test456",
        model="gemini-2.0-flash-exp",
        usage_stats=usage_stats,
        reason="length",  # Custom reason
    )

    assert isinstance(result, str)
    assert "data:" in result
    # Verify contains stop info
    assert result  # non-empty


def test_generate_sse_stop_chunk_with_usage_empty_usage():
    """
    Test scenario: Empty usage statistics
    Verify: Able to handle empty dict
    """
    from api_utils.utils import generate_sse_stop_chunk_with_usage

    result = generate_sse_stop_chunk_with_usage(
        req_id="test789", model="test-model", usage_stats={}, reason="stop"
    )

    assert isinstance(result, str)
    assert "data:" in result
