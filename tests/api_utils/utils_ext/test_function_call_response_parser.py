"""
Tests for Function Call Response Parser.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from api_utils.utils_ext.function_call_response_parser import (
    FunctionCallParseResult,
    FunctionCallResponseParser,
    _validate_function_names,
    format_function_calls_to_openai,
)
from api_utils.utils_ext.function_calling import ParsedFunctionCall
from api_utils.utils_ext.function_calling_cache import (
    FunctionCallingCache,
    FunctionCallingCacheEntry,
)


class TestFunctionCallParseResult:
    """Tests for FunctionCallParseResult dataclass."""

    def test_default_values(self):
        """Test default values are correct."""
        result = FunctionCallParseResult()
        assert result.has_function_calls is False
        assert result.function_calls == []
        assert result.text_content == ""
        assert result.raw_elements == []
        assert result.parse_errors == []

    def test_with_function_calls(self):
        """Test with populated function calls."""
        calls = [
            ParsedFunctionCall(name="get_weather", arguments={"location": "NYC"}),
            ParsedFunctionCall(name="get_time", arguments={}),
        ]
        result = FunctionCallParseResult(
            has_function_calls=True,
            function_calls=calls,
            text_content="Some text",
        )
        assert result.has_function_calls is True
        assert len(result.function_calls) == 2
        assert result.function_calls[0].name == "get_weather"


class TestFunctionCallResponseParser:
    """Tests for FunctionCallResponseParser class."""

    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page."""
        page = AsyncMock()
        return page

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""
        return MagicMock()

    @pytest.fixture
    def parser(self, mock_page, mock_logger):
        """Create a parser instance."""
        return FunctionCallResponseParser(
            page=mock_page,
            logger=mock_logger,
            req_id="test123",
        )

    def test_initialization(self, parser, mock_page, mock_logger):
        """Test parser initialization."""
        assert parser.page is mock_page
        assert parser.logger is mock_logger
        assert parser.req_id == "test123"

    def test_parse_arguments_json(self, parser):
        """Test parsing JSON arguments."""
        args = '{"location": "NYC", "units": "metric"}'
        result = parser._parse_arguments(args)
        assert result == {"location": "NYC", "units": "metric"}

    def test_parse_arguments_empty(self, parser):
        """Test parsing empty arguments."""
        result = parser._parse_arguments("")
        assert result == {}

    def test_parse_arguments_key_value(self, parser):
        """Test parsing key-value format arguments."""
        args = 'location: "NYC", count: 5, enabled: true'
        result = parser._parse_arguments(args)
        assert result.get("location") == "NYC"
        assert result.get("count") == 5
        assert result.get("enabled") is True

    def test_parse_function_call_from_text(self, parser):
        """Test parsing function call from text."""
        text = '{"name": "get_weather", "arguments": {"location": "NYC"}}'
        result = parser._parse_function_call_from_text(text)
        assert result is not None
        assert result.name == "get_weather"
        assert result.arguments == {"location": "NYC"}

    def test_parse_function_call_from_text_no_name(self, parser):
        """Test parsing returns None when no name found."""
        text = '{"arguments": {"location": "NYC"}}'
        result = parser._parse_function_call_from_text(text)
        assert result is None

    def test_parse_json_function_calls_single(self, parser):
        """Test parsing single function call from JSON."""
        json_text = (
            '{"function_call": {"name": "search", "arguments": {"query": "test"}}}'
        )
        results = parser._parse_json_function_calls(json_text)
        assert len(results) == 1
        assert results[0].name == "search"
        assert results[0].arguments == {"query": "test"}

    def test_parse_json_function_calls_tool_calls_array(self, parser):
        """Test parsing tool_calls array from JSON."""
        json_text = """
        {
            "tool_calls": [
                {"function": {"name": "func1", "arguments": "{}"}},
                {"function": {"name": "func2", "arguments": "{\\"x\\": 1}"}}
            ]
        }
        """
        results = parser._parse_json_function_calls(json_text)
        assert len(results) == 2
        assert results[0].name == "func1"
        assert results[1].name == "func2"
        assert results[1].arguments == {"x": 1}

    def test_parse_function_call_dict(self, parser):
        """Test parsing function call dict."""
        fc_dict = {"name": "get_weather", "arguments": '{"location": "NYC"}'}
        result = parser._parse_function_call_dict(fc_dict)
        assert result is not None
        assert result.name == "get_weather"
        assert result.arguments == {"location": "NYC"}

    def test_parse_function_call_dict_with_params(self, parser):
        """Test parsing function call dict with params key."""
        fc_dict = {"name": "get_time", "params": {"timezone": "UTC"}}
        result = parser._parse_function_call_dict(fc_dict)
        assert result is not None
        assert result.name == "get_time"
        assert result.arguments == {"timezone": "UTC"}

    def test_deduplicate_calls(self, parser):
        """Test deduplication of function calls."""
        calls = [
            ParsedFunctionCall(name="func1", arguments={"a": 1}),
            ParsedFunctionCall(name="func1", arguments={"a": 1}),  # Duplicate
            ParsedFunctionCall(name="func1", arguments={"a": 2}),  # Different args
            ParsedFunctionCall(name="func2", arguments={}),
        ]
        result = parser._deduplicate_calls(calls)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_detect_function_calls_widget_found(self, parser, mock_page):
        """Test detection when widget is found."""
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_page.locator = MagicMock(return_value=mock_locator)

        result = await parser.detect_function_calls()
        assert result is True

    @pytest.mark.asyncio
    async def test_detect_function_calls_none_found(self, parser, mock_page):
        """Test detection when no function calls found."""
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=0)
        mock_page.locator = MagicMock(return_value=mock_locator)

        result = await parser.detect_function_calls()
        assert result is False


class TestFormatFunctionCallsToOpenAI:
    """Tests for format_function_calls_to_openai helper."""

    def test_format_single_call(self):
        """Test formatting a single function call."""
        calls = [ParsedFunctionCall(name="get_weather", arguments={"city": "NYC"})]
        message, finish_reason = format_function_calls_to_openai(calls)

        assert finish_reason == "tool_calls"
        assert message["role"] == "assistant"
        assert "tool_calls" in message
        assert len(message["tool_calls"]) == 1
        assert message["tool_calls"][0]["function"]["name"] == "get_weather"
        assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {
            "city": "NYC"
        }

    def test_format_multiple_calls(self):
        """Test formatting multiple function calls."""
        calls = [
            ParsedFunctionCall(name="func1", arguments={}),
            ParsedFunctionCall(name="func2", arguments={"x": 1}),
        ]
        message, finish_reason = format_function_calls_to_openai(calls)

        assert finish_reason == "tool_calls"
        assert len(message["tool_calls"]) == 2

    def test_format_empty_calls(self):
        """Test formatting with no function calls."""
        message, finish_reason = format_function_calls_to_openai([])

        assert finish_reason == "stop"
        assert message["role"] == "assistant"
        # tool_calls may or may not be present when empty

    def test_format_with_content(self):
        """Test formatting with additional text content."""
        calls = [ParsedFunctionCall(name="search", arguments={"q": "test"})]
        message, finish_reason = format_function_calls_to_openai(
            calls, content="Here's the result"
        )

        assert finish_reason == "tool_calls"
        assert len(message["tool_calls"]) == 1


class TestValidateFunctionNames:
    """Tests for _validate_function_names helper function."""

    @pytest.fixture
    def mock_cache_with_tools(self):
        """Set up a cache with registered tool names."""
        cache = FunctionCallingCache.get_instance()
        cache._enabled = True
        cache._cache = FunctionCallingCacheEntry(
            tools_digest="test",
            toggle_enabled=True,
            declarations_set=True,
            timestamp=time.time(),
            tool_names={
                "gh_grep_searchGitHub",
                "tavily_tavily_search",
                "context7_get-library-docs",
            },
        )
        return cache

    def test_validate_empty_list(self):
        """Test validation of empty list returns empty list."""
        result = _validate_function_names([])
        assert result == []

    def test_validate_exact_match_no_change(self, mock_cache_with_tools):
        """Test that exact matches are not modified."""
        calls = [
            ParsedFunctionCall(name="gh_grep_searchGitHub", arguments={"q": "test"}),
        ]
        result = _validate_function_names(calls)
        assert len(result) == 1
        assert result[0].name == "gh_grep_searchGitHub"

    def test_validate_corrects_truncated_name(self, mock_cache_with_tools):
        """Test that truncated names are corrected."""
        calls = [
            ParsedFunctionCall(name="gh_grep_searchGitH", arguments={"q": "test"}),
        ]
        result = _validate_function_names(calls)
        assert len(result) == 1
        assert result[0].name == "gh_grep_searchGitHub"

    def test_validate_low_confidence_not_corrected(self, mock_cache_with_tools):
        """Test that low confidence matches are not corrected."""
        # "gh" is only ~10% match, below 70% threshold
        calls = [
            ParsedFunctionCall(name="gh", arguments={}),
        ]
        result = _validate_function_names(calls)
        assert len(result) == 1
        # Should NOT be corrected due to low confidence
        assert result[0].name == "gh"

    def test_validate_unknown_name_unchanged(self, mock_cache_with_tools):
        """Test that unknown names are left unchanged."""
        calls = [
            ParsedFunctionCall(name="unknown_function", arguments={}),
        ]
        result = _validate_function_names(calls)
        assert len(result) == 1
        assert result[0].name == "unknown_function"

    def test_validate_multiple_calls(self, mock_cache_with_tools):
        """Test validation of multiple function calls."""
        calls = [
            ParsedFunctionCall(name="gh_grep_searchGitH", arguments={"q": "test"}),
            ParsedFunctionCall(name="tavily_tavily_sear", arguments={"query": "hello"}),
            ParsedFunctionCall(name="unknown_func", arguments={}),
        ]
        result = _validate_function_names(calls)
        assert len(result) == 3
        assert result[0].name == "gh_grep_searchGitHub"  # Corrected
        assert result[1].name == "tavily_tavily_search"  # Corrected
        assert result[2].name == "unknown_func"  # Unchanged

    def test_validate_handles_empty_name(self, mock_cache_with_tools):
        """Test that calls with empty name are handled gracefully."""
        calls = [
            ParsedFunctionCall(name="", arguments={}),
            ParsedFunctionCall(name="gh_grep_searchGitHub", arguments={}),
        ]
        result = _validate_function_names(calls)
        assert len(result) == 2
        assert result[0].name == ""
        assert result[1].name == "gh_grep_searchGitHub"

    def test_validate_no_cache_returns_unchanged(self):
        """Test that with no cache, calls are returned unchanged."""
        # Clear any cached instance
        cache = FunctionCallingCache.get_instance()
        cache._cache = None

        calls = [
            ParsedFunctionCall(name="any_function", arguments={}),
        ]
        result = _validate_function_names(calls)
        assert len(result) == 1
        assert result[0].name == "any_function"
