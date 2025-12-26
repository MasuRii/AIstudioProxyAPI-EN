"""
Tests for FunctionCallingCache - specifically for tool name extraction and validation.
"""

import time
from unittest.mock import MagicMock

import pytest

from api_utils.utils_ext.function_calling_cache import (
    FunctionCallingCache,
    FunctionCallingCacheEntry,
)


class TestFunctionCallingCacheEntry:
    """Tests for FunctionCallingCacheEntry dataclass."""

    def test_default_values(self):
        """Test default values are correct."""
        entry = FunctionCallingCacheEntry(
            tools_digest="abc123",
            toggle_enabled=True,
            declarations_set=True,
            timestamp=time.time(),
        )
        assert entry.tools_digest == "abc123"
        assert entry.toggle_enabled is True
        assert entry.declarations_set is True
        assert entry.model_name is None
        assert entry.tool_names == set()

    def test_with_tool_names(self):
        """Test entry with tool names."""
        names = {"get_weather", "search_web", "calculate"}
        entry = FunctionCallingCacheEntry(
            tools_digest="xyz789",
            toggle_enabled=True,
            declarations_set=True,
            timestamp=time.time(),
            tool_names=names,
        )
        assert entry.tool_names == names
        assert "get_weather" in entry.tool_names
        assert "search_web" in entry.tool_names


class TestExtractToolNames:
    """Tests for _extract_tool_names method."""

    @pytest.fixture
    def cache(self):
        """Create a cache instance."""
        return FunctionCallingCache(logger=MagicMock())

    def test_extract_from_openai_format(self, cache):
        """Test extracting names from OpenAI tool format (nested function.name)."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather info",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
        names = cache._extract_tool_names(tools)
        assert names == {"get_weather", "search_web"}

    def test_extract_from_flat_format(self, cache):
        """Test extracting names from flat format (name at top level)."""
        tools = [
            {"name": "get_weather", "description": "Get weather"},
            {"name": "calculate", "description": "Calculate math"},
        ]
        names = cache._extract_tool_names(tools)
        assert names == {"get_weather", "calculate"}

    def test_extract_from_mixed_format(self, cache):
        """Test extracting names from mixed formats."""
        tools = [
            {"type": "function", "function": {"name": "openai_tool"}},
            {"name": "flat_tool"},
        ]
        names = cache._extract_tool_names(tools)
        assert names == {"openai_tool", "flat_tool"}

    def test_extract_empty_list(self, cache):
        """Test extracting from empty list."""
        names = cache._extract_tool_names([])
        assert names == set()

    def test_extract_invalid_tools(self, cache):
        """Test extracting from invalid tool definitions."""
        tools = [
            None,
            "not a dict",
            {"no_name_key": "value"},
            {"function": "not a dict"},
            {"function": {"no_name": "value"}},
        ]
        names = cache._extract_tool_names(tools)
        assert names == set()

    def test_extract_with_special_characters(self, cache):
        """Test extracting names with special characters."""
        tools = [
            {"name": "gh_grep_searchGitHub"},
            {"name": "tavily_tavily_search"},
            {"name": "context7_get-library-docs"},
        ]
        names = cache._extract_tool_names(tools)
        assert names == {
            "gh_grep_searchGitHub",
            "tavily_tavily_search",
            "context7_get-library-docs",
        }


class TestValidateFunctionName:
    """Tests for validate_function_name method (fuzzy matching)."""

    @pytest.fixture
    def cache_with_tools(self):
        """Create a cache with registered tools."""
        cache = FunctionCallingCache(logger=MagicMock())
        # Manually set up cache with tool names
        cache._cache = FunctionCallingCacheEntry(
            tools_digest="test123",
            toggle_enabled=True,
            declarations_set=True,
            timestamp=time.time(),
            tool_names={
                "gh_grep_searchGitHub",
                "tavily_tavily_search",
                "context7_get-library-docs",
                "chrome_devtools_click",
                "short",
            },
        )
        return cache

    def test_exact_match(self, cache_with_tools):
        """Test exact name match returns the name unchanged."""
        corrected, was_corrected, confidence = cache_with_tools.validate_function_name(
            "gh_grep_searchGitHub"
        )
        assert corrected == "gh_grep_searchGitHub"
        assert was_corrected is False
        assert confidence == 1.0

    def test_prefix_match_truncated_name(self, cache_with_tools):
        """Test fuzzy matching corrects truncated names."""
        # Simulate truncated name from model hallucination
        corrected, was_corrected, confidence = cache_with_tools.validate_function_name(
            "gh_grep_searchGitH"
        )
        assert corrected == "gh_grep_searchGitHub"
        assert was_corrected is True
        assert 0.7 < confidence < 1.0  # High confidence but not exact

    def test_prefix_match_another_truncated(self, cache_with_tools):
        """Test another truncated name gets corrected."""
        corrected, was_corrected, confidence = cache_with_tools.validate_function_name(
            "tavily_tavily_sear"
        )
        assert corrected == "tavily_tavily_search"
        assert was_corrected is True
        assert 0.7 < confidence < 1.0

    def test_prefix_too_short(self, cache_with_tools):
        """Test that very short prefixes still match (no minimum threshold)."""
        # "gh" matches "gh_grep_searchGitHub" via prefix
        corrected, was_corrected, confidence = cache_with_tools.validate_function_name(
            "gh"
        )
        # It will match but with low confidence
        assert was_corrected is True
        assert confidence < 0.2  # Very low confidence for short prefix

    def test_no_match_invalid_name(self, cache_with_tools):
        """Test that completely invalid names are not matched."""
        corrected, was_corrected, confidence = cache_with_tools.validate_function_name(
            "completely_unknown_function"
        )
        assert was_corrected is False
        assert corrected == "completely_unknown_function"
        assert confidence == 0.0

    def test_empty_cache(self):
        """Test validation with empty cache returns original name."""
        cache = FunctionCallingCache(logger=MagicMock())
        # No cache set
        corrected, was_corrected, confidence = cache.validate_function_name(
            "any_function"
        )
        assert was_corrected is False
        assert corrected == "any_function"
        assert confidence == 0.0

    def test_empty_tool_names(self):
        """Test validation with empty tool_names set."""
        cache = FunctionCallingCache(logger=MagicMock())
        cache._cache = FunctionCallingCacheEntry(
            tools_digest="test",
            toggle_enabled=True,
            declarations_set=True,
            timestamp=time.time(),
            tool_names=set(),
        )
        corrected, was_corrected, confidence = cache.validate_function_name(
            "any_function"
        )
        assert was_corrected is False
        assert corrected == "any_function"
        assert confidence == 0.0

    def test_ambiguous_prefix(self, cache_with_tools):
        """Test that ambiguous prefixes (matching multiple tools) return first match."""
        # Add another tool with similar prefix
        cache_with_tools._cache.tool_names.add("chrome_devtools_screenshot")
        # "chrome_devtools_c" matches "chrome_devtools_click"
        corrected, was_corrected, confidence = cache_with_tools.validate_function_name(
            "chrome_devtools_c"
        )
        assert was_corrected is True
        assert corrected == "chrome_devtools_click"


class TestGetRegisteredToolNames:
    """Tests for get_registered_tool_names method."""

    def test_no_cache(self):
        """Test returns empty set when no cache exists."""
        cache = FunctionCallingCache(logger=MagicMock())
        names = cache.get_registered_tool_names()
        assert names == set()

    def test_with_cache(self):
        """Test returns tool names from cache."""
        cache = FunctionCallingCache(logger=MagicMock())
        cache._cache = FunctionCallingCacheEntry(
            tools_digest="test",
            toggle_enabled=True,
            declarations_set=True,
            timestamp=time.time(),
            tool_names={"func1", "func2", "func3"},
        )
        names = cache.get_registered_tool_names()
        assert names == {"func1", "func2", "func3"}


class TestUpdateCacheWithTools:
    """Tests for update_cache with tools parameter."""

    @pytest.fixture
    def cache(self):
        """Create a cache instance."""
        cache = FunctionCallingCache(logger=MagicMock())
        cache._enabled = True
        return cache

    def test_update_cache_with_openai_tools(self, cache):
        """Test that update_cache extracts and stores tool names."""
        tools = [
            {"type": "function", "function": {"name": "get_weather"}},
            {"type": "function", "function": {"name": "search_web"}},
        ]
        cache.update_cache(
            tools_digest="digest123",
            toggle_enabled=True,
            declarations_set=True,
            tools=tools,
        )
        assert cache._cache is not None
        assert cache._cache.tool_names == {"get_weather", "search_web"}

    def test_update_cache_without_tools(self, cache):
        """Test that update_cache works without tools (empty set)."""
        cache.update_cache(
            tools_digest="digest123",
            toggle_enabled=True,
            declarations_set=True,
        )
        assert cache._cache is not None
        assert cache._cache.tool_names == set()

    def test_update_cache_replaces_previous_tools(self, cache):
        """Test that update_cache replaces previous tool names."""
        # First update
        cache.update_cache(
            tools_digest="digest1",
            toggle_enabled=True,
            declarations_set=True,
            tools=[{"name": "old_tool"}],
        )
        assert cache._cache.tool_names == {"old_tool"}

        # Second update replaces
        cache.update_cache(
            tools_digest="digest2",
            toggle_enabled=True,
            declarations_set=True,
            tools=[{"name": "new_tool"}],
        )
        assert cache._cache.tool_names == {"new_tool"}
        assert "old_tool" not in cache._cache.tool_names
