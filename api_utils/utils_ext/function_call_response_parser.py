"""
Function Call Response Parser

Parses function call blocks from AI Studio's DOM response.
Detects when the model wants to call a function and extracts
the function name and arguments.

This module provides DOM-based parsing as a complement to the
network interceptor-based parsing in stream/interceptors.py.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from playwright.async_api import Locator
from playwright.async_api import Page as AsyncPage

from config.selectors import (
    FUNCTION_CALL_ARGS_SELECTOR,
    FUNCTION_CALL_CODE_BLOCK_SELECTOR,
    FUNCTION_CALL_NAME_SELECTOR,
    FUNCTION_CALL_WIDGET_SELECTOR,
    NATIVE_FUNCTION_CALL_ARGS_SELECTOR,
    NATIVE_FUNCTION_CALL_CHUNK_SELECTOR,
    NATIVE_FUNCTION_CALL_NAME_SELECTOR,
)
from config.settings import FUNCTION_CALLING_DEBUG

logger = logging.getLogger("AIStudioProxyServer")

# Compiled patterns for static parsing (used outside class context)
# Enhanced pattern: captures function names with underscores, hyphens, and special chars
# Uses greedy match up to newline or open brace, then strips trailing whitespace
_STATIC_EMULATED_FC_PATTERN = re.compile(
    r"Request\s+function\s+call:\s*([\w\-_.:]+)(?:\s*\n|\s*\{|\s*$)",
    re.IGNORECASE,
)
_STATIC_EMULATED_PARAMS_PATTERN = re.compile(
    r"Parameters:\s*\n?\s*(\{[\s\S]*?\})\s*(?:\n\n|\Z|(?=Request\s+function\s+call:))",
    re.IGNORECASE,
)
_STATIC_EMULATED_PARAMS_PATTERN = re.compile(
    r"Parameters:\s*\n?\s*(\{[\s\S]*?\})\s*(?:\n\n|\Z|(?=Request\s+function\s+call:))",
    re.IGNORECASE,
)


def parse_emulated_function_calls_static(text: str) -> List[Any]:
    """Static function to parse emulated text-based function calls without page instance.

    Handles the format:
        Request function call: <function_name>
        Parameters:
        {
          "key": "value",
          ...
        }

    This is useful for recovering function calls in response_generators.py
    when the DOM-based detection fails due to timing issues.

    Args:
        text: The text content to parse.

    Returns:
        List of ParsedFunctionCall objects.
    """
    calls: List[Any] = []

    if not text or "Request function call:" not in text:
        return calls

    try:
        # Split by "Request function call:" to handle multiple calls
        parts = re.split(r"(?=Request\s+function\s+call:)", text, flags=re.IGNORECASE)

        for part in parts:
            if not part.strip():
                continue

            # Extract function name
            name_match = _STATIC_EMULATED_FC_PATTERN.search(part)
            if not name_match:
                continue

            function_name = name_match.group(1).strip()

            # Strip common prefixes like "default_api_"
            if function_name.startswith("default_api_"):
                function_name = function_name[len("default_api_") :]

            # Extract parameters
            arguments: Dict[str, Any] = {}
            params_match = _STATIC_EMULATED_PARAMS_PATTERN.search(part)
            if params_match:
                try:
                    json_str = params_match.group(1)
                    # Clean control characters
                    json_str = re.sub(r"<ctrl\d+>", "", json_str)
                    arguments = json.loads(json_str)
                except (json.JSONDecodeError, Exception):
                    pass

            call = _create_parsed_call(
                name=function_name,
                arguments=arguments,
                raw_text=part[:200],
            )
            calls.append(call)

    except Exception as e:
        if FUNCTION_CALLING_DEBUG:
            logger.debug(f"Static emulated FC parsing error: {e}")

    # Validate and potentially correct function names using fuzzy matching
    calls = _validate_function_names(calls)

    return calls


def _validate_function_names(calls: List[Any]) -> List[Any]:
    """Validate parsed function names against registered tools.

    Uses fuzzy matching to correct truncated or slightly malformed function names
    that may result from model hallucination in text-format function calls.

    Args:
        calls: List of ParsedFunctionCall objects.

    Returns:
        List with corrected function names where possible.
    """
    if not calls:
        return calls

    try:
        from api_utils.utils_ext.function_calling_cache import FunctionCallingCache

        cache = FunctionCallingCache.get_instance()

        for call in calls:
            if hasattr(call, "name") and call.name:
                validated_name, was_corrected, confidence = (
                    cache.validate_function_name(call.name)
                )
                if was_corrected and confidence >= 0.7:
                    if FUNCTION_CALLING_DEBUG:
                        logger.debug(
                            f"Corrected function name: '{call.name}' -> '{validated_name}' "
                            f"(confidence={confidence:.2f})"
                        )
                    call.name = validated_name

    except Exception as e:
        if FUNCTION_CALLING_DEBUG:
            logger.debug(f"Function name validation error: {e}")

    return calls


def _create_parsed_call(
    name: str, arguments: Dict[str, Any], raw_text: Optional[str] = None
) -> Any:
    """Create a ParsedFunctionCall instance using lazy import.

    This avoids circular imports while still returning the proper type.

    Args:
        name: Function name.
        arguments: Function arguments as dict.
        raw_text: Optional raw text for debugging.

    Returns:
        ParsedFunctionCall instance.
    """
    # Import at call time to avoid circular imports
    from api_utils.utils_ext.function_calling import ParsedFunctionCall

    return ParsedFunctionCall(name=name, arguments=arguments, raw_text=raw_text)


@dataclass
class FunctionCallParseResult:
    """Result of parsing function call responses from DOM.

    Attributes:
        has_function_calls: Whether any function calls were detected.
        function_calls: List of parsed function calls (ParsedFunctionCall objects).
        text_content: Any regular text content (non-function-call).
        raw_elements: Raw element text for debugging.
        parse_errors: Any errors encountered during parsing.
    """

    has_function_calls: bool = False
    function_calls: List[Any] = field(default_factory=list)
    text_content: str = ""
    raw_elements: List[str] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)


class FunctionCallResponseParser:
    """
    Parses function call widgets and blocks from AI Studio's DOM.

    AI Studio displays function calls in different formats:
    1. Structured widget: ms-function-call element with name and args
    2. JSON code block: ```json with function_call/tool_call structure
    3. Inline format: Function name followed by arguments

    This parser handles all these formats and converts them to
    ParsedFunctionCall objects.
    """

    # Common patterns for function call detection in text
    FUNCTION_CALL_PATTERNS = [
        # JSON-style function call
        re.compile(
            r'[\{\[]?\s*"?function_call"?\s*:\s*\{([^}]+)\}',
            re.IGNORECASE | re.DOTALL,
        ),
        # Tool call format
        re.compile(
            r'[\{\[]?\s*"?tool_call"?\s*:\s*\{([^}]+)\}',
            re.IGNORECASE | re.DOTALL,
        ),
        # Direct name/arguments format
        re.compile(
            r'"name"\s*:\s*"([^"]+)"[,\s]*"arguments"\s*:\s*(\{[^}]+\})',
            re.IGNORECASE | re.DOTALL,
        ),
        # Gemini-style function call
        re.compile(
            r'functionCall\s*[\(:]?\s*\{?\s*"?name"?\s*:\s*"([^"]+)"',
            re.IGNORECASE | re.DOTALL,
        ),
    ]

    # Pattern for emulated/text-based function calls:
    # "Request function call: <function_name>\nParameters:\n{...}"
    # This handles cases where the model outputs text-formatted tool calls
    # instead of using native function calling UI elements
    # Supports: with params (newline or {), without params (end of string/line)
    # Enhanced: uses \w, hyphen, underscore, and dot to capture full function names
    EMULATED_FUNCTION_CALL_PATTERN = re.compile(
        r"Request\s+function\s+call:\s*([\w\-_.:]+)(?:\s*\n|\s*\{|\s*$)",
        re.IGNORECASE,
    )
    # Pattern to extract the JSON parameters block after "Parameters:"
    EMULATED_PARAMS_PATTERN = re.compile(
        r"Parameters:\s*\n?\s*(\{[\s\S]*?\})\s*(?:\n\n|\Z|(?=Request\s+function\s+call:))",
        re.IGNORECASE,
    )

    # Pattern for extracting function name and params from various formats
    NAME_PATTERN = re.compile(r'"?name"?\s*:\s*"([^"]+)"', re.IGNORECASE)
    ARGS_PATTERN = re.compile(
        r'"?(?:arguments|params|parameters)"?\s*:\s*(\{[^}]*\}|\[[^\]]*\]|"[^"]*")',
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(
        self,
        page: AsyncPage,
        logger: Optional[logging.Logger] = None,
        req_id: str = "",
    ):
        """Initialize the parser.

        Args:
            page: Playwright page instance.
            logger: Optional logger instance.
            req_id: Request ID for logging.
        """
        self.page = page
        self.logger = logger or logging.getLogger("AIStudioProxyServer")
        self.req_id = req_id

    async def detect_function_calls(
        self,
        check_client_disconnected: Optional[Callable[..., Any]] = None,
    ) -> bool:
        """Quickly detect if the current response contains function calls.

        This is a fast check without full parsing. Supports both native
        function calling (ms-function-call-chunk) and legacy formats.

        Args:
            check_client_disconnected: Optional callback to check connection.

        Returns:
            True if function calls are detected, False otherwise.
        """
        try:
            # Check for native function call chunks first (AI Studio's built-in FC)
            native_locator = self.page.locator(NATIVE_FUNCTION_CALL_CHUNK_SELECTOR)
            if await native_locator.count() > 0:
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] Detected native function call chunk(s)"
                    )
                return True

            # Check for legacy function call widgets
            widget_locator = self.page.locator(FUNCTION_CALL_WIDGET_SELECTOR)
            if await widget_locator.count() > 0:
                return True

            # Check for function call code blocks
            code_block_locator = self.page.locator(FUNCTION_CALL_CODE_BLOCK_SELECTOR)
            if await code_block_locator.count() > 0:
                return True

            return False

        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] Error detecting function calls: {e}"
                )
            return False

    async def parse_function_calls(
        self,
        check_client_disconnected: Optional[Callable[..., Any]] = None,
    ) -> FunctionCallParseResult:
        """Parse all function calls from the current response.

        This method supports both native function calling (AI Studio's built-in
        ms-function-call-chunk elements) and legacy/emulated formats.

        Args:
            check_client_disconnected: Optional callback to check connection.

        Returns:
            FunctionCallParseResult with all detected function calls.
        """
        result = FunctionCallParseResult()

        try:
            # Strategy 1: Try native function call parsing first (ms-function-call-chunk)
            # This is the format used by AI Studio's built-in native function calling
            native_calls = await self._parse_native_function_calls()
            if native_calls:
                result.function_calls.extend(native_calls)
                result.has_function_calls = True
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] Found {len(native_calls)} native function call(s)"
                    )

            # Strategy 2: Try structured widget parsing (legacy/fallback)
            if not result.has_function_calls:
                widget_calls = await self._parse_widget_function_calls()
                if widget_calls:
                    result.function_calls.extend(widget_calls)
                    result.has_function_calls = True

            # Strategy 3: Try code block parsing
            if not result.has_function_calls:
                code_block_calls = await self._parse_code_block_function_calls()
                if code_block_calls:
                    result.function_calls.extend(code_block_calls)
                    result.has_function_calls = True

            # Strategy 4: Always try to get text content, and use text pattern matching if no calls found yet
            text_calls, text_content = await self._parse_text_function_calls()
            result.text_content = text_content

            if not result.has_function_calls and text_calls:
                result.function_calls.extend(text_calls)
                result.has_function_calls = True

            # Deduplicate function calls by name + arguments
            result.function_calls = self._deduplicate_calls(result.function_calls)

            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] Parsed {len(result.function_calls)} function call(s) total"
                )

        except Exception as e:
            error_msg = f"Error parsing function calls: {e}"
            if FUNCTION_CALLING_DEBUG:
                self.logger.error(f"[{self.req_id}] {error_msg}")
            result.parse_errors.append(error_msg)

        return result

    async def _parse_native_function_calls(self) -> List[Any]:
        """Parse function calls from AI Studio's native function call chunks.

        Native function calls use the ms-function-call-chunk element with:
        - Function name in mat-panel-title span (after the icon)
        - Arguments as JSON in pre > code block

        Returns:
            List of parsed function calls from native chunks.
        """
        calls: List[Any] = []

        try:
            # Look for native function call chunks
            chunks = self.page.locator(NATIVE_FUNCTION_CALL_CHUNK_SELECTOR)
            chunk_count = await chunks.count()

            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] Found {chunk_count} native function call chunk(s)"
                )

            for i in range(chunk_count):
                try:
                    chunk = chunks.nth(i)
                    call = await self._parse_single_native_chunk(chunk)
                    if call:
                        calls.append(call)
                        if FUNCTION_CALLING_DEBUG:
                            self.logger.debug(
                                f"[{self.req_id}] Parsed native function call: {call.name}"
                            )
                except Exception as e:
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.debug(
                            f"[{self.req_id}] Error parsing native chunk {i}: {e}"
                        )

        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] Error accessing native function call chunks: {e}"
                )

        return calls

    async def _parse_single_native_chunk(self, chunk: Locator) -> Optional[Any]:
        """Parse a single native function call chunk element.

        Args:
            chunk: Locator for the ms-function-call-chunk element.

        Returns:
            ParsedFunctionCall if successful, None otherwise.
        """
        try:
            # Extract function name from mat-panel-title span
            # The structure is: mat-panel-title > span.material-symbols-outlined (icon) > span (name)
            name_elem = chunk.locator(NATIVE_FUNCTION_CALL_NAME_SELECTOR)

            function_name = ""
            if await name_elem.count() > 0:
                function_name = await name_elem.first.inner_text(timeout=2000)
                function_name = function_name.strip()

            # If name not found via selector, try alternative extraction
            if not function_name:
                # Try to get from mat-expansion-panel-header-title
                header = chunk.locator(
                    "mat-panel-title, .mat-expansion-panel-header-title"
                )
                if await header.count() > 0:
                    header_text = await header.first.inner_text(timeout=2000)
                    # Remove icon text and common prefixes
                    function_name = self._extract_function_name_from_header(header_text)

            if not function_name:
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] Could not extract function name from native chunk"
                    )
                return None

            # Extract arguments from pre > code block
            args_elem = chunk.locator(NATIVE_FUNCTION_CALL_ARGS_SELECTOR)
            arguments: Dict[str, Any] = {}

            if await args_elem.count() > 0:
                args_text = await args_elem.first.inner_text(timeout=2000)
                arguments = self._parse_arguments(args_text)
                if FUNCTION_CALLING_DEBUG:
                    self.logger.debug(
                        f"[{self.req_id}] Extracted arguments for {function_name}: {list(arguments.keys())}"
                    )

            return _create_parsed_call(
                name=function_name,
                arguments=arguments,
                raw_text=f"{function_name}({json.dumps(arguments)})",
            )

        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(f"[{self.req_id}] Error parsing native chunk: {e}")
            return None

    def _extract_function_name_from_header(self, header_text: str) -> str:
        """Extract function name from header text, removing icons and extra content.

        Args:
            header_text: Raw text from mat-panel-title or header element.

        Returns:
            Cleaned function name.
        """
        if not header_text:
            return ""

        # Clean up the header text
        lines = header_text.strip().split("\n")
        for line in lines:
            line = line.strip()
            # Skip icon names and common prefixes
            if line and line not in (
                "function",
                "functions",
                "chevron_right",
                "chevron_left",
            ):
                # Skip material icon names
                if not line.startswith("expand_") and not line.startswith("download"):
                    return line

        return ""

    async def _parse_widget_function_calls(self) -> List[Any]:
        """Parse function calls from structured widget elements.

        Returns:
            List of parsed function calls from widgets.
        """
        calls: List[Any] = []

        try:
            widgets = self.page.locator(FUNCTION_CALL_WIDGET_SELECTOR)
            widget_count = await widgets.count()

            for i in range(widget_count):
                try:
                    widget = widgets.nth(i)
                    call = await self._parse_single_widget(widget)
                    if call:
                        calls.append(call)
                except Exception as e:
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.debug(
                            f"[{self.req_id}] Error parsing widget {i}: {e}"
                        )

        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] Error accessing function call widgets: {e}"
                )

        return calls

    async def _parse_single_widget(self, widget: Locator) -> Optional[Any]:
        """Parse a single function call widget element.

        Args:
            widget: Locator for the widget element.

        Returns:
            ParsedFunctionCall if successful, None otherwise.
        """
        try:
            # Extract function name
            name_elem = widget.locator(FUNCTION_CALL_NAME_SELECTOR)
            if await name_elem.count() == 0:
                # Try getting text from the widget itself
                widget_text = await widget.inner_text(timeout=1000)
                return self._parse_function_call_from_text(widget_text)

            function_name = await name_elem.first.inner_text(timeout=1000)
            function_name = function_name.strip()

            if not function_name:
                return None

            # Extract arguments
            args_elem = widget.locator(FUNCTION_CALL_ARGS_SELECTOR)
            arguments: Dict[str, Any] = {}

            if await args_elem.count() > 0:
                args_text = await args_elem.first.inner_text(timeout=1000)
                arguments = self._parse_arguments(args_text)

            return _create_parsed_call(
                name=function_name,
                arguments=arguments,
                raw_text=f"{function_name}({json.dumps(arguments)})",
            )

        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(f"[{self.req_id}] Error parsing widget: {e}")
            return None

    async def _parse_code_block_function_calls(self) -> List[Any]:
        """Parse function calls from JSON/code blocks.

        Returns:
            List of parsed function calls from code blocks.
        """
        calls: List[Any] = []

        try:
            code_blocks = self.page.locator(FUNCTION_CALL_CODE_BLOCK_SELECTOR)
            block_count = await code_blocks.count()

            for i in range(block_count):
                try:
                    block = code_blocks.nth(i)
                    block_text = await block.inner_text(timeout=2000)

                    # Try to parse as JSON
                    block_calls = self._parse_json_function_calls(block_text)
                    calls.extend(block_calls)

                except Exception as e:
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.debug(
                            f"[{self.req_id}] Error parsing code block {i}: {e}"
                        )

        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(f"[{self.req_id}] Error accessing code blocks: {e}")

        return calls

    async def _parse_text_function_calls(self) -> Tuple[List[Any], str]:
        """Parse function calls from general text content.

        Returns:
            Tuple of (function_calls, remaining_text_content).
        """
        calls: List[Any] = []
        text_content = ""

        try:
            # Get the last response turn
            from config.selectors import FINAL_RESPONSE_SELECTOR

            response_elem = self.page.locator(FINAL_RESPONSE_SELECTOR).last

            if await response_elem.count() > 0:
                text_content = await response_elem.inner_text(timeout=2000)

                # Strategy A: Check for emulated text-based function calls first
                # Format: "Request function call: <name>\nParameters:\n{...}"
                emulated_calls = self._parse_emulated_function_calls(text_content)
                if emulated_calls:
                    calls.extend(emulated_calls)
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.debug(
                            f"[{self.req_id}] Found {len(emulated_calls)} emulated text-based function call(s)"
                        )

                # Strategy B: Check for JSON-style function call patterns
                if not calls:
                    for pattern in self.FUNCTION_CALL_PATTERNS:
                        matches = pattern.findall(text_content)
                        if matches:
                            for match in matches:
                                call = self._parse_function_call_from_match(match)
                                if call:
                                    calls.append(call)

        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] Error parsing text function calls: {e}"
                )

        return calls, text_content

    def _parse_emulated_function_calls(self, text: str) -> List[Any]:
        """Parse emulated text-based function calls.

        Handles the format:
            Request function call: <function_name>
            Parameters:
            {
              "key": "value",
              ...
            }

        This format is output by the model when it doesn't use the native
        function calling UI elements but still intends to call a function.

        Args:
            text: The text content to parse.

        Returns:
            List of ParsedFunctionCall objects.
        """
        calls: List[Any] = []

        if not text or "Request function call:" not in text:
            return calls

        try:
            # Find all function call requests in the text
            # Split by "Request function call:" to handle multiple calls
            parts = re.split(
                r"(?=Request\s+function\s+call:)", text, flags=re.IGNORECASE
            )

            for part in parts:
                if not part.strip():
                    continue

                # Extract function name
                name_match = self.EMULATED_FUNCTION_CALL_PATTERN.search(part)
                if not name_match:
                    continue

                function_name = name_match.group(1).strip()

                # Check if original text has inline params like "func_name{params}"
                # The regex stops at '{', so check if '{' follows the match
                match_end = name_match.end()
                has_inline_params = (
                    match_end <= len(part) and part[match_end - 1 : match_end] == "{"
                )

                if has_inline_params:
                    # Try to parse inline params from original text
                    arguments = self._parse_inline_params(part)
                else:
                    # Extract parameters from "Parameters:" block
                    arguments = self._extract_emulated_params(part)

                if function_name:
                    # Clean up function name (remove any trailing colons, etc.)
                    function_name = function_name.rstrip(":").strip()

                    # Strip common prefixes that models add but clients don't expect
                    # e.g., "default_api:write_to_file" -> "write_to_file"
                    prefix_patterns = ["default_api:", "functions.", "tools."]
                    for prefix in prefix_patterns:
                        if function_name.startswith(prefix):
                            function_name = function_name[len(prefix) :]
                            break

                    call = _create_parsed_call(
                        name=function_name,
                        arguments=arguments,
                        raw_text=part[:500],  # Keep first 500 chars for debugging
                    )
                    calls.append(call)
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.debug(
                            f"[{self.req_id}] Parsed emulated function call: {function_name} "
                            f"with {len(arguments)} argument(s)"
                        )

        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[{self.req_id}] Error parsing emulated function calls: {e}"
                )

        # Validate and potentially correct function names using fuzzy matching
        calls = _validate_function_names(calls)

        return calls

    def _extract_emulated_params(self, text: str) -> Dict[str, Any]:
        """Extract parameters from emulated function call text.

        Handles the "Parameters:" block with JSON content.

        Args:
            text: Text containing the Parameters block.

        Returns:
            Parsed arguments dictionary.
        """
        arguments: Dict[str, Any] = {}

        # Try the dedicated params pattern first
        params_match = self.EMULATED_PARAMS_PATTERN.search(text)
        if params_match:
            params_text = params_match.group(1)
            try:
                arguments = json.loads(params_text)
                if isinstance(arguments, dict):
                    return arguments
            except json.JSONDecodeError:
                pass

        # Fallback: Find JSON object after "Parameters:"
        params_idx = text.lower().find("parameters:")
        if params_idx != -1:
            after_params = text[params_idx + len("parameters:") :]

            # Find the first { and extract the JSON object
            brace_start = after_params.find("{")
            if brace_start != -1:
                # Count braces to find the matching closing brace
                brace_count = 0
                json_end = 0
                for i, char in enumerate(after_params[brace_start:]):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = brace_start + i + 1
                            break

                if json_end > 0:
                    json_str = after_params[brace_start:json_end]
                    try:
                        arguments = json.loads(json_str)
                        if isinstance(arguments, dict):
                            return arguments
                    except json.JSONDecodeError:
                        # Try to clean up the JSON string
                        cleaned = self._clean_json_string(json_str)
                        try:
                            arguments = json.loads(cleaned)
                            if isinstance(arguments, dict):
                                return arguments
                        except json.JSONDecodeError:
                            pass

        return arguments

    def _clean_json_string(self, json_str: str) -> str:
        """Clean up a potentially malformed JSON string.

        Args:
            json_str: The JSON string to clean.

        Returns:
            Cleaned JSON string.
        """
        # Remove control characters (like <ctrl46> which appears in some outputs)
        cleaned = re.sub(r"<ctrl\d+>", "", json_str)
        # Remove other non-printable characters except newlines and tabs
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", cleaned)
        return cleaned

    def _parse_inline_params(self, text: str) -> Dict[str, Any]:
        """Parse inline parameters from function call text.

        Handles formats like:
        - func_name{key: "value"}  (JavaScript-like)
        - func_name{key: <ctrl46>value<ctrl46>}  (control char delimiters)
        - func_name{"key": "value"}  (JSON)

        Args:
            text: Text containing the inline params.

        Returns:
            Parsed arguments dictionary.
        """
        arguments: Dict[str, Any] = {}

        try:
            # Find the complete JSON/object block
            brace_start = text.find("{")
            if brace_start == -1:
                return arguments

            brace_count = 0
            json_end = 0
            full_text = text[brace_start:]

            for i, char in enumerate(full_text):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break

            if json_end == 0:
                return arguments

            raw_params = full_text[:json_end]

            # Strategy 1: Try direct JSON parse
            try:
                arguments = json.loads(raw_params)
                if isinstance(arguments, dict):
                    return arguments
            except json.JSONDecodeError:
                pass

            # Strategy 2: Clean <ctrlNN> markers and retry
            # <ctrl46> appears to be used as string delimiters (ASCII 46 = '.')
            # Replace with quotes for JSON compatibility
            cleaned = re.sub(r"<ctrl\d+>", '"', raw_params)
            try:
                arguments = json.loads(cleaned)
                if isinstance(arguments, dict):
                    return arguments
            except json.JSONDecodeError:
                pass

            # Strategy 3: Convert JavaScript-like notation to JSON
            # Handle unquoted keys: {key: "value"} -> {"key": "value"}
            js_to_json = re.sub(r"(\{|,)\s*(\w+)\s*:", r'\1"\2":', cleaned)
            try:
                arguments = json.loads(js_to_json)
                if isinstance(arguments, dict):
                    return arguments
            except json.JSONDecodeError:
                pass

            # Strategy 4: Try parsing as nested structure with arrays
            # Handle format like: {files:[{path:"value"}]}
            # First, ensure all keys are quoted
            step1 = re.sub(r"(\{|\[|,)\s*(\w+)\s*:", r'\1"\2":', raw_params)
            # Replace <ctrlNN> with quotes
            step2 = re.sub(r"<ctrl\d+>", '"', step1)
            try:
                arguments = json.loads(step2)
                if isinstance(arguments, dict):
                    return arguments
            except json.JSONDecodeError:
                pass

            # Strategy 5: Extract key-value pairs manually
            # For simple cases like {path: <ctrl46>value<ctrl46>}
            kv_pattern = re.compile(
                r'["\']?(\w+)["\']?\s*:\s*(?:<ctrl\d+>|["\'])([^"\'<}]+)(?:<ctrl\d+>|["\'])?',
                re.IGNORECASE,
            )
            matches = kv_pattern.findall(raw_params)
            if matches:
                for key, value in matches:
                    arguments[key] = value.strip()

        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(f"[{self.req_id}] Error parsing inline params: {e}")

        return arguments

    def _parse_json_function_calls(self, json_text: str) -> List[Any]:
        """Parse function calls from JSON text.

        Args:
            json_text: JSON string that may contain function calls.

        Returns:
            List of parsed function calls.
        """
        calls: List[Any] = []

        # Clean the text
        json_text = json_text.strip()

        # Try direct JSON parse
        try:
            data = json.loads(json_text)
            calls.extend(self._extract_calls_from_json(data))
            return calls
        except json.JSONDecodeError:
            pass

        # Try to find JSON within the text
        json_pattern = re.compile(r"(\{[^{}]*\}|\[[^\[\]]*\])", re.DOTALL)
        matches = json_pattern.findall(json_text)

        for match in matches:
            try:
                data = json.loads(match)
                calls.extend(self._extract_calls_from_json(data))
            except json.JSONDecodeError:
                continue

        return calls

    def _extract_calls_from_json(self, data: Any) -> List[Any]:
        """Extract function calls from parsed JSON data.

        Args:
            data: Parsed JSON data (dict or list).

        Returns:
            List of parsed function calls.
        """
        calls: List[Any] = []

        if isinstance(data, dict):
            # Check for function_call or tool_call
            if "function_call" in data:
                call = self._parse_function_call_dict(data["function_call"])
                if call:
                    calls.append(call)
            elif "tool_call" in data:
                call = self._parse_function_call_dict(data["tool_call"])
                if call:
                    calls.append(call)
            elif "name" in data:
                call = self._parse_function_call_dict(data)
                if call:
                    calls.append(call)

            # Check for tool_calls array
            if "tool_calls" in data and isinstance(data["tool_calls"], list):
                for tc in data["tool_calls"]:
                    if isinstance(tc, dict) and "function" in tc:
                        call = self._parse_function_call_dict(tc["function"])
                        if call:
                            calls.append(call)

        elif isinstance(data, list):
            for item in data:
                calls.extend(self._extract_calls_from_json(item))

        return calls

    def _parse_function_call_dict(self, fc_dict: Dict[str, Any]) -> Optional[Any]:
        """Parse a function call from a dict.

        Args:
            fc_dict: Dict with 'name' and 'arguments'/'params'.

        Returns:
            ParsedFunctionCall if valid, None otherwise.
        """
        if not isinstance(fc_dict, dict):
            return None

        name = fc_dict.get("name")
        if not name or not isinstance(name, str):
            return None

        # Get arguments (may be string or dict)
        arguments = fc_dict.get("arguments") or fc_dict.get("params") or {}

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        return _create_parsed_call(
            name=name,
            arguments=arguments,
            raw_text=json.dumps(fc_dict),
        )

    def _parse_function_call_from_text(self, text: str) -> Optional[Any]:
        """Parse a function call from raw text using patterns.

        Args:
            text: Raw text that may contain a function call.

        Returns:
            ParsedFunctionCall if found, None otherwise.
        """
        if not text:
            return None

        # Try to extract name
        name_match = self.NAME_PATTERN.search(text)
        if not name_match:
            return None

        name = name_match.group(1)

        # Try to extract arguments
        args_match = self.ARGS_PATTERN.search(text)
        arguments: Dict[str, Any] = {}

        if args_match:
            args_str = args_match.group(1)
            arguments = self._parse_arguments(args_str)

        return _create_parsed_call(
            name=name,
            arguments=arguments,
            raw_text=text[:200],  # Keep first 200 chars for debugging
        )

    def _parse_function_call_from_match(self, match: Any) -> Optional[Any]:
        """Parse function call from regex match.

        Args:
            match: Regex match result (string or tuple).

        Returns:
            ParsedFunctionCall if valid, None otherwise.
        """
        if isinstance(match, tuple):
            if len(match) >= 2:
                name = match[0]
                args_str = match[1] if len(match) > 1 else "{}"
                arguments = self._parse_arguments(args_str)
                return _create_parsed_call(name=name, arguments=arguments)
            elif len(match) == 1:
                # Just the inner content, need to extract name
                return self._parse_function_call_from_text(match[0])
        elif isinstance(match, str):
            return self._parse_function_call_from_text(match)

        return None

    def _parse_arguments(self, args_text: str) -> Dict[str, Any]:
        """Parse arguments from text.

        Args:
            args_text: Arguments text (JSON or other format).

        Returns:
            Parsed arguments dict.
        """
        if not args_text:
            return {}

        args_text = args_text.strip()

        # Debug log raw args_text
        if FUNCTION_CALLING_DEBUG:
            self.logger.debug(
                f"[{self.req_id}] Raw args_text (len={len(args_text)}): {args_text[:500]}"
            )

        # Try JSON parse
        try:
            result = json.loads(args_text)
            if isinstance(result, dict):
                return result
            return {"value": result}
        except json.JSONDecodeError as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.debug(f"[{self.req_id}] JSON parse failed: {e}")

        # Try to extract key-value pairs
        kv_pattern = re.compile(r'"?(\w+)"?\s*[:=]\s*(".*?"|[^,}\]]+)')
        matches = kv_pattern.findall(args_text)

        if matches:
            result = {}
            for key, value in matches:
                value = value.strip().strip('"')
                # Try to parse value type
                if value.lower() == "true":
                    result[key] = True
                elif value.lower() == "false":
                    result[key] = False
                elif value.lower() == "null":
                    result[key] = None
                else:
                    try:
                        result[key] = int(value)
                    except ValueError:
                        try:
                            result[key] = float(value)
                        except ValueError:
                            result[key] = value
            return result

        return {}

    def _deduplicate_calls(self, calls: List[Any]) -> List[Any]:
        """Remove duplicate function calls.

        Args:
            calls: List of function calls.

        Returns:
            Deduplicated list.
        """
        seen: set = set()
        unique: List[Any] = []

        for call in calls:
            key = (call.name, json.dumps(call.arguments, sort_keys=True))
            if key not in seen:
                seen.add(key)
                unique.append(call)

        return unique


def format_function_calls_to_openai(
    parsed_calls: List[Any],
    content: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """Format parsed function calls to OpenAI response format.

    Args:
        parsed_calls: List of parsed function calls (ParsedFunctionCall objects).
        content: Optional text content.

    Returns:
        Tuple of (message_dict, finish_reason).
    """
    from api_utils.utils_ext.function_calling import (
        ResponseFormatter,
        build_assistant_message_with_tool_calls,
        get_finish_reason,
    )

    formatter = ResponseFormatter()
    tool_calls = formatter.format_tool_calls(parsed_calls)

    message = build_assistant_message_with_tool_calls(tool_calls, content)
    finish_reason = get_finish_reason(bool(tool_calls))

    return message, finish_reason


__all__ = [
    "FunctionCallResponseParser",
    "FunctionCallParseResult",
    "format_function_calls_to_openai",
]
