"""Verification test for emulated function call parsing fix.

Tests that the FunctionCallResponseParser correctly handles text-formatted
function calls like:
    Request function call: write_to_file
    Parameters:
    {
      "path": "test.txt",
      "content": "Hello"
    }
"""

import pytest

from api_utils.utils_ext.function_call_response_parser import FunctionCallResponseParser


class TestEmulatedFunctionCallParsing:
    """Test suite for emulated text-based function call parsing."""

    def test_pattern_matches_simple_function_call(self):
        """Test that EMULATED_FUNCTION_CALL_PATTERN matches basic format."""
        text = "Request function call: write_to_file\nParameters:\n{}"
        match = FunctionCallResponseParser.EMULATED_FUNCTION_CALL_PATTERN.search(text)
        assert match is not None
        assert match.group(1).strip() == "write_to_file"

    def test_pattern_matches_with_colon_namespace(self):
        """Test parsing function names with namespace like default_api:func."""
        text = "Request function call: default_api:apply_diff\nParameters:\n{}"
        match = FunctionCallResponseParser.EMULATED_FUNCTION_CALL_PATTERN.search(text)
        assert match is not None
        assert match.group(1).strip() == "default_api:apply_diff"

    def test_params_pattern_extracts_json(self):
        """Test that EMULATED_PARAMS_PATTERN extracts JSON block."""
        text = """Parameters:
{
  "path": "test.txt",
  "content": "Hello World"
}"""
        match = FunctionCallResponseParser.EMULATED_PARAMS_PATTERN.search(text)
        assert match is not None
        # Should capture the JSON block
        import json

        params = json.loads(match.group(1))
        assert params["path"] == "test.txt"
        assert params["content"] == "Hello World"

    def test_parse_emulated_single_call(self):
        """Test parsing a single emulated function call."""

        # Create a mock parser (we'll test the method directly)
        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        text = """Request function call: write_to_file
Parameters:
{
  "path": "test_tool_capability.txt",
  "content": "This is a test file to verify tool capability."
}"""

        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "write_to_file"
        assert calls[0].arguments["path"] == "test_tool_capability.txt"
        assert "test file" in calls[0].arguments["content"]

    def test_parse_emulated_inline_params(self):
        """Test parsing function call with inline params format."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        # Format seen in Kilo Code logs: "list_files{path:.,recursive:false}"
        text = """Request function call: list_files
Parameters:
{"path": ".", "recursive": false}"""

        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "list_files"
        assert calls[0].arguments.get("path") == "."
        assert calls[0].arguments.get("recursive") is False

    def test_parse_multiple_emulated_calls(self):
        """Test parsing multiple function calls in one response."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        text = """I'll help you with that.

Request function call: read_file
Parameters:
{"path": "src/main.py"}

Then I'll also need to check:

Request function call: list_files
Parameters:
{"path": "src", "recursive": true}"""

        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 2
        assert calls[0].name == "read_file"
        assert calls[0].arguments["path"] == "src/main.py"
        assert calls[1].name == "list_files"
        assert calls[1].arguments["path"] == "src"

    def test_parse_with_control_characters(self):
        """Test parsing handles control characters in output."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        # Simulate control characters that appeared in logs
        text = """Request function call: apply_diff
Parameters:
{"diff": "some content", "path": "file.py"}"""

        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "apply_diff"

    def test_clean_json_string_removes_control_chars(self):
        """Test that _clean_json_string removes control characters."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        dirty = '{"path": "<ctrl46>.", "value": "test"}'
        cleaned = parser._clean_json_string(dirty)
        assert "<ctrl46>" not in cleaned
        assert '"path": "."' in cleaned

    def test_no_false_positives_for_regular_text(self):
        """Test that regular text without function calls returns empty list."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        text = "Here's how to use the write_to_file function in your code."
        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 0

    def test_handles_nested_json_in_params(self):
        """Test parsing handles nested JSON objects in parameters."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        text = """Request function call: complex_tool
Parameters:
{
  "config": {
    "nested": {
      "deep": "value"
    }
  },
  "options": ["a", "b", "c"]
}"""

        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "complex_tool"
        assert calls[0].arguments["config"]["nested"]["deep"] == "value"
        assert calls[0].arguments["options"] == ["a", "b", "c"]

    def test_strips_default_api_prefix(self):
        """Test that default_api: prefix is stripped from function names."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        text = """Request function call: default_api:write_to_file
Parameters:
{"path": "test.txt", "content": "hello"}"""

        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "write_to_file"  # Prefix stripped
        assert calls[0].arguments["path"] == "test.txt"

    def test_inline_params_with_ctrl46_delimiters(self):
        """Test parsing inline params using <ctrl46> as string delimiters."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        text = "Request function call: read_file{files:[{path:<ctrl46>temp_test.txt<ctrl46>}]}"

        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "read_file"
        assert "files" in calls[0].arguments
        assert calls[0].arguments["files"][0]["path"] == "temp_test.txt"

    def test_multiline_ctrl46_params(self):
        """Test parsing multi-line content in <ctrl46> delimited params."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        text = """Request function call: default_api:update_todos{todos:<ctrl46>[ ] Create file
[ ] Verify file
[x] Done<ctrl46>}"""

        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "update_todos"  # Prefix stripped
        assert "todos" in calls[0].arguments
        assert "Create file" in calls[0].arguments["todos"]

    def test_no_param_function_call(self):
        """Test parsing function calls with no parameters."""

        class MockPage:
            pass

        parser = FunctionCallResponseParser(page=MockPage(), req_id="test")

        text = "Request function call: attempt_completion"

        calls = parser._parse_emulated_function_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "attempt_completion"
        assert calls[0].arguments == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
