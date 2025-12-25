"""
Function Calling Orchestrator

Central coordinator that routes function calling between native and emulated modes.
Integrates SchemaConverter, ResponseFormatter, and browser automation into the request flow.

Implements Phase 3 of ADR-001: Native Function Calling Architecture.
Includes caching to skip redundant UI operations for subsequent requests with same tools.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from browser_utils.page_controller import PageController
from logging_utils.fc_debug import FCModule, get_fc_logger

# FC debug logger for orchestrator-level events
fc_logger = get_fc_logger()
from config.settings import (
    FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS,
    FUNCTION_CALLING_DEBUG,
    FUNCTION_CALLING_MODE,
    FUNCTION_CALLING_NATIVE_FALLBACK,
    FUNCTION_CALLING_NATIVE_RETRY_COUNT,
)
from models import ClientDisconnectedError

# Import directly from the module file to avoid circular imports through __init__.py
# fmt: off
from api_utils.utils_ext.function_calling import (  # noqa: E501
    CallIdManager,
    FunctionCallingConfig,
    FunctionCallingMode,
    ParsedFunctionCall,
    ResponseFormatter,
    SchemaConversionError,
    SchemaConverter,
    build_assistant_message_with_tool_calls,
    get_finish_reason,
)
from api_utils.utils_ext.function_calling_cache import FunctionCallingCache
# fmt: on


class NativeFunctionCallingError(Exception):
    """Raised when native function calling fails and fallback may be needed."""

    pass


@dataclass
class FunctionCallingState:
    """Tracks the state of function calling for a request.

    Attributes:
        mode: The effective mode being used for this request.
        native_enabled: Whether native mode was successfully enabled.
        tools_configured: Whether tools were configured in native mode.
        fallback_used: Whether fallback to emulated mode was used.
        error_message: Any error message from native mode attempts.
        tools_digest: Digest of tool definitions for caching.
        cache_hit: Whether cache was used to skip UI operations.
    """

    mode: FunctionCallingMode
    native_enabled: bool = False
    tools_configured: bool = False
    fallback_used: bool = False
    error_message: Optional[str] = None
    tools_digest: Optional[str] = None
    cache_hit: bool = False


class FunctionCallingOrchestrator:
    """
    Central orchestrator for function calling that handles mode selection,
    tool configuration, and response processing.

    Usage:
        orchestrator = FunctionCallingOrchestrator()

        # Before sending prompt
        state = await orchestrator.prepare_request(
            tools=request.tools,
            tool_choice=request.tool_choice,
            page_controller=page_controller,
            check_client_disconnected=check_fn,
            req_id=req_id,
        )

        # After receiving response (for non-streaming)
        processed = await orchestrator.process_response(
            raw_content=response_content,
            functions=function_data,
            state=state,
        )
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the orchestrator.

        Args:
            logger: Optional logger instance. If None, uses default logger.
        """
        self.logger = logger or logging.getLogger("AIStudioProxyServer")
        self._config = FunctionCallingConfig.from_settings()
        self._schema_converter = SchemaConverter()
        self._response_formatter = ResponseFormatter()
        self._cache = FunctionCallingCache.get_instance(self.logger)

    @property
    def config(self) -> FunctionCallingConfig:
        """Get the current function calling configuration."""
        return self._config

    @property
    def response_formatter(self) -> ResponseFormatter:
        """Get the response formatter instance."""
        return self._response_formatter

    @property
    def cache(self) -> FunctionCallingCache:
        """Get the function calling cache instance."""
        return self._cache

    async def _ensure_fc_disabled_when_no_tools(
        self,
        page_controller: PageController,
        check_client_disconnected: Callable,
        req_id: str,
    ) -> None:
        """Ensure function calling toggle is disabled when no tools are provided.

        This handles the edge case where a previous request enabled FC,
        but the current request (e.g., XML-based tools) doesn't use OpenAI-format tools.
        We need to disable the toggle to prevent interference.

        Args:
            page_controller: PageController instance for browser automation.
            check_client_disconnected: Callback to check client connection.
            req_id: Request ID for logging.
        """
        # Only check/disable if we're in native or auto mode
        # In emulated mode, the toggle should never have been enabled by us
        if self._config.mode == FunctionCallingMode.EMULATED:
            return

        try:
            # Check if FC toggle is currently enabled
            is_enabled = await page_controller.is_function_calling_enabled(
                check_client_disconnected, use_cache=True
            )

            if is_enabled:
                if FUNCTION_CALLING_DEBUG:
                    self.logger.info(
                        f"[{req_id}] [FC] No tools in request but FC toggle is enabled - disabling for clean state"
                    )
                start_time = time.perf_counter()

                success = await page_controller.disable_function_calling(
                    check_client_disconnected
                )

                elapsed = time.perf_counter() - start_time

                if success:
                    # Invalidate cache since state changed
                    self._cache.invalidate(reason="no_tools_cleanup", req_id=req_id)
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.info(
                            f"[{req_id}] [FC:Perf] FC toggle disabled in {elapsed:.2f}s"
                        )
                else:
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.warning(
                            f"[{req_id}] [FC] Failed to disable FC toggle - may affect response"
                        )

        except ClientDisconnectedError:
            # Client gone, nothing to do
            pass
        except asyncio.CancelledError:
            # Cancelled, skip cleanup
            pass
        except Exception as e:
            # Non-fatal error - log and continue
            # The request can still proceed, just with FC potentially enabled
            if FUNCTION_CALLING_DEBUG:
                self.logger.warning(
                    f"[{req_id}] [FC] Error checking/disabling FC toggle: {e}"
                )

    def should_use_native_mode(
        self,
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Optional[Union[str, Dict[str, Any]]],
    ) -> bool:
        """Determine if native mode should be attempted for this request.

        Args:
            tools: List of tool definitions from the request.
            tool_choice: Tool choice parameter from the request.

        Returns:
            True if native mode should be attempted, False otherwise.
        """
        # No tools = no need for native mode
        if not tools or len(tools) == 0:
            return False

        # Check mode setting
        mode = self._config.mode

        # Emulated mode always uses text injection
        if mode == FunctionCallingMode.EMULATED:
            if self._config.debug:
                self.logger.debug("FC: Mode is EMULATED, using prompt injection")
            return False

        # Native and auto modes should try native
        if mode in (FunctionCallingMode.NATIVE, FunctionCallingMode.AUTO):
            if self._config.debug:
                self.logger.debug(
                    f"FC: Mode is {mode.value}, attempting native UI automation"
                )
            return True

        if self._config.debug:
            self.logger.debug(f"FC: Mode {mode} unknown, defaulting to False")
        return False

    def get_effective_mode(
        self,
        tools: Optional[List[Dict[str, Any]]],
    ) -> FunctionCallingMode:
        """Get the effective function calling mode for a request.

        Args:
            tools: List of tool definitions from the request.

        Returns:
            The effective FunctionCallingMode to use.
        """
        if not tools or len(tools) == 0:
            return FunctionCallingMode.EMULATED

        return self._config.mode

    async def prepare_request(
        self,
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Optional[Union[str, Dict[str, Any]]],
        page_controller: PageController,
        check_client_disconnected: Callable,
        req_id: str,
        model_name: Optional[str] = None,
    ) -> FunctionCallingState:
        """Prepare a request for function calling based on the configured mode.

        This method:
        1. Computes tool digest and checks cache for existing state
        2. If cache valid: skips UI automation (cache hit)
        3. If cache miss: converts tools and configures browser UI
        4. Updates cache on success
        5. Handles fallback if native mode fails and fallback is enabled
        6. If no tools provided but FC was previously enabled, disables it

        Args:
            tools: List of OpenAI-format tool definitions.
            tool_choice: Tool choice parameter (auto, none, required, or specific).
            page_controller: PageController instance for browser automation.
            check_client_disconnected: Callback to check client connection.
            req_id: Request ID for logging.
            model_name: Optional model name for cache validation.

        Returns:
            FunctionCallingState with the configuration result.
        """
        total_start = time.perf_counter()
        state = FunctionCallingState(mode=self.get_effective_mode(tools))

        # No tools provided - ensure FC toggle is disabled if it was previously enabled
        if not tools or len(tools) == 0:
            await self._ensure_fc_disabled_when_no_tools(
                page_controller=page_controller,
                check_client_disconnected=check_client_disconnected,
                req_id=req_id,
            )
            if self._config.debug:
                self.logger.debug(
                    f"[{req_id}] [FC] No tools in request, FC setup skipped/disabled"
                )
            return state

        if state.mode == FunctionCallingMode.EMULATED:
            if self._config.debug:
                self.logger.debug(
                    f"[{req_id}] [FC] Using emulated mode, skipping native FC setup"
                )
            if FUNCTION_CALLING_DEBUG:
                fc_logger.log_mode_selection(req_id, "emulated", "configured mode")
            return state

        # Native or Auto mode - compute digest and check cache
        tools_digest = self._cache.compute_tools_digest(tools)
        state.tools_digest = tools_digest

        # Check cache first
        if self._cache.is_cache_valid(tools_digest, model_name, req_id=req_id):
            cached_state = self._cache.get_cached_state()
            if (
                cached_state
                and cached_state.declarations_set
                and cached_state.toggle_enabled
            ):
                # Cache HIT - but UI toggle may have been reset by new_chat
                # Verify and re-enable toggle if needed before trusting cache
                try:
                    # Check actual UI toggle state (bypass instance cache)
                    toggle_enabled = await page_controller.is_function_calling_enabled(
                        check_client_disconnected, use_cache=False
                    )
                    if not toggle_enabled:
                        if FUNCTION_CALLING_DEBUG:
                            self.logger.warning(
                                f"[{req_id}] [FC:Cache] HIT but UI toggle disabled - re-enabling"
                            )
                        enable_success = await page_controller.enable_function_calling(
                            check_client_disconnected
                        )
                        if not enable_success:
                            if FUNCTION_CALLING_DEBUG:
                                self.logger.warning(
                                    f"[{req_id}] [FC:Cache] Failed to re-enable toggle, "
                                    "falling through to full setup"
                                )
                            # Fall through to full native configuration
                        else:
                            elapsed = time.perf_counter() - total_start
                            if FUNCTION_CALLING_DEBUG:
                                self.logger.info(
                                    f"[{req_id}] [FC:Cache] HIT - toggle re-enabled "
                                    f"(digest={tools_digest[:8]}..., checked in {elapsed:.3f}s)"
                                )
                            state.native_enabled = True
                            state.tools_configured = True
                            state.cache_hit = True
                            return state
                    else:
                        elapsed = time.perf_counter() - total_start
                        if FUNCTION_CALLING_DEBUG:
                            self.logger.info(
                                f"[{req_id}] [FC:Cache] HIT - skipping native FC setup "
                                f"(digest={tools_digest[:8]}..., checked in {elapsed:.3f}s)"
                            )
                        state.native_enabled = True
                        state.tools_configured = True
                        state.cache_hit = True
                        return state
                except ClientDisconnectedError:
                    raise
                except Exception as e:
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.warning(
                            f"[{req_id}] [FC:Cache] Toggle verification failed: {e}, "
                            "falling through to full setup"
                        )
                    # Fall through to full native configuration

        # Cache miss - proceed with native configuration
        if FUNCTION_CALLING_DEBUG:
            self.logger.info(
                f"[{req_id}] [FC] Configuring native function calling with {len(tools)} tool(s) "
                f"(digest={tools_digest[:8]}...)"
            )
        if FUNCTION_CALLING_DEBUG:
            fc_logger.log_mode_selection(
                req_id, "native", f"cache_miss, {len(tools)} tools"
            )

        # Log tool choice if specific
        if tool_choice:
            if isinstance(tool_choice, dict):
                forced_fn = tool_choice.get("function", {}).get(
                    "name"
                ) or tool_choice.get("name")
                if forced_fn:
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.info(
                            f"[{req_id}] [FC] Tool choice: FORCING specific tool '{forced_fn}'"
                        )
            elif isinstance(tool_choice, str) and tool_choice.lower() not in (
                "auto",
                "none",
                "required",
            ):
                if FUNCTION_CALLING_DEBUG:
                    self.logger.info(
                        f"[{req_id}] [FC] Tool choice: FORCING specific tool '{tool_choice}'"
                    )

        try:
            # Convert OpenAI tools to Gemini format
            convert_start = time.perf_counter()
            gemini_declarations = self._schema_converter.convert_tools(tools)
            convert_elapsed = time.perf_counter() - convert_start

            if self._config.debug:
                self.logger.debug(
                    f"[{req_id}] [FC:Perf] Converted {len(tools)} tools to Gemini format "
                    f"in {convert_elapsed:.3f}s"
                )
            if FUNCTION_CALLING_DEBUG:
                fc_logger.log_schema_conversion(
                    req_id, tool_count=len(tools), elapsed_ms=convert_elapsed * 1000
                )

            # Retry loop for UI automation
            last_error: Optional[Exception] = None
            for attempt in range(1, self._config.native_retry_count + 1):
                try:
                    if attempt > 1:
                        if FUNCTION_CALLING_DEBUG:
                            self.logger.warning(
                                f"[{req_id}] [FC:UI] Retry attempt {attempt}/{self._config.native_retry_count}"
                            )

                    check_client_disconnected(f"FC prepare attempt {attempt}")

                    # Check if function calling is available
                    fc_available = await page_controller.is_function_calling_available(
                        check_client_disconnected
                    )

                    if not fc_available:
                        raise NativeFunctionCallingError(
                            "Function calling UI not available for this model"
                        )

                    # Set function declarations via UI (with caching support)
                    success = await page_controller.set_function_declarations(
                        gemini_declarations,
                        check_client_disconnected,
                        tools_digest=tools_digest,
                        model_name=model_name,
                    )

                    if success:
                        state.native_enabled = True
                        state.tools_configured = True
                        total_elapsed = time.perf_counter() - total_start
                        if FUNCTION_CALLING_DEBUG:
                            self.logger.info(
                                f"[{req_id}] [FC:Perf] Native function calling configured "
                                f"in {total_elapsed:.2f}s"
                            )
                        if FUNCTION_CALLING_DEBUG:
                            fc_logger.info(
                                FCModule.ORCHESTRATOR,
                                f"Native FC configured successfully in {total_elapsed:.2f}s",
                                req_id=req_id,
                            )
                        return state
                    else:
                        raise NativeFunctionCallingError(
                            "Failed to set function declarations in UI"
                        )

                except ClientDisconnectedError:
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    last_error = e
                    if FUNCTION_CALLING_DEBUG:
                        self.logger.warning(
                            f"[{req_id}] [FC] Native FC attempt {attempt}/{self._config.native_retry_count} failed: {e}"
                        )
                    if attempt < self._config.native_retry_count:
                        await asyncio.sleep(0.5)

            # All retries failed
            raise NativeFunctionCallingError(
                f"Native function calling failed after {self._config.native_retry_count} attempts: {last_error}"
            )

        except SchemaConversionError as e:
            state.error_message = f"Schema conversion error: {e}"
            if FUNCTION_CALLING_DEBUG:
                self.logger.error(f"[{req_id}] [FC] {state.error_message}")

            # Schema errors are not recoverable - don't fallback
            if state.mode == FunctionCallingMode.NATIVE:
                raise

            # Auto mode with schema error - fall through to emulated
            state.fallback_used = True
            state.mode = FunctionCallingMode.EMULATED
            if FUNCTION_CALLING_DEBUG:
                self.logger.warning(
                    f"[{req_id}] [FC] Falling back to emulated mode due to schema error"
                )
            if FUNCTION_CALLING_DEBUG:
                fc_logger.log_mode_selection(
                    req_id, "emulated", "fallback_schema_error"
                )
            return state

        except NativeFunctionCallingError as e:
            state.error_message = str(e)
            if FUNCTION_CALLING_DEBUG:
                self.logger.warning(
                    f"[{req_id}] [FC] Native function calling failed: {e}"
                )

            # Check if fallback is allowed
            if state.mode == FunctionCallingMode.AUTO and self._config.native_fallback:
                state.fallback_used = True
                state.mode = FunctionCallingMode.EMULATED
                if FUNCTION_CALLING_DEBUG:
                    self.logger.info(
                        f"[{req_id}] [FC] Falling back to emulated mode for function calling"
                    )
                if FUNCTION_CALLING_DEBUG:
                    fc_logger.log_mode_selection(
                        req_id, "emulated", "fallback_native_error"
                    )
                return state
            elif state.mode == FunctionCallingMode.NATIVE:
                # Native mode with no fallback - raise error
                raise

        except ClientDisconnectedError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            state.error_message = f"Unexpected error: {e}"
            if FUNCTION_CALLING_DEBUG:
                self.logger.error(
                    f"[{req_id}] [FC] Unexpected error in FC prepare: {e}"
                )

            if state.mode == FunctionCallingMode.AUTO and self._config.native_fallback:
                state.fallback_used = True
                state.mode = FunctionCallingMode.EMULATED
                return state
            elif state.mode == FunctionCallingMode.NATIVE:
                raise

        return state

    async def cleanup_after_request(
        self,
        state: FunctionCallingState,
        page_controller: PageController,
        check_client_disconnected: Callable,
        req_id: str,
        preserve_cache: bool = False,
    ) -> None:
        """Clean up function calling state after a request completes.

        If configured to clear between requests and native mode was used,
        this will clear the function declarations from the UI.

        Args:
            state: The function calling state from prepare_request.
            page_controller: PageController instance for browser automation.
            check_client_disconnected: Callback to check client connection.
            req_id: Request ID for logging.
            preserve_cache: If True, don't invalidate cache (for same-tool sequences).
        """
        if not FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS:
            if self._config.debug:
                self.logger.debug(
                    f"[{req_id}] [FC] Skipping cleanup (CLEAR_BETWEEN_REQUESTS=False)"
                )
            return

        if not state.tools_configured:
            return

        # If this was a cache hit, we didn't actually change anything
        if state.cache_hit:
            if self._config.debug:
                self.logger.debug(
                    f"[{req_id}] [FC] Skipping cleanup (cache hit, no UI changes made)"
                )
            return

        try:
            start_time = time.perf_counter()
            # Pass invalidate_cache=not preserve_cache to control cache behavior
            await page_controller.clear_function_declarations(
                check_client_disconnected,
                invalidate_cache=not preserve_cache,
            )
            elapsed = time.perf_counter() - start_time

            if self._config.debug:
                self.logger.debug(
                    f"[{req_id}] [FC:Perf] Cleared function declarations in {elapsed:.2f}s"
                )
        except ClientDisconnectedError:
            pass  # Client gone, nothing to clean up
        except asyncio.CancelledError:
            pass  # Cancelled, skip cleanup
        except Exception as e:
            if FUNCTION_CALLING_DEBUG:
                self.logger.warning(
                    f"[{req_id}] [FC] Failed to clear function declarations: {e}"
                )

    def format_function_calls_for_response(
        self,
        functions: List[Dict[str, Any]],
        content: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Format function call data from AI Studio into OpenAI response format.

        Args:
            functions: List of function call data from AI Studio.
                       Each item should have 'name' and 'params' keys.
            content: Optional text content to include in the response.

        Returns:
            Tuple of (message_dict, finish_reason).
        """
        if not functions:
            return {"role": "assistant", "content": content or ""}, "stop"

        parsed_calls: List[ParsedFunctionCall] = []
        for func_data in functions:
            if isinstance(func_data, dict):
                name = func_data.get("name", "")
                params = func_data.get("params", {})
                if name:
                    parsed_calls.append(ParsedFunctionCall(name=name, arguments=params))

        if not parsed_calls:
            return {"role": "assistant", "content": content or ""}, "stop"

        message = self._response_formatter.format_non_streaming_response(
            parsed_calls, content=None
        )
        finish_reason = get_finish_reason(True)

        return message, finish_reason

    def format_streaming_tool_calls(
        self,
        functions: List[Dict[str, Any]],
        chunk_size: int = 50,
    ) -> List[Dict[str, Any]]:
        """Format function calls for streaming response.

        Generates all the delta chunks needed to stream function calls.

        Args:
            functions: List of function call data.
            chunk_size: Size of each arguments chunk.

        Returns:
            List of delta objects for streaming.
        """
        if not functions:
            return []

        all_chunks: List[Dict[str, Any]] = []
        for idx, func_data in enumerate(functions):
            if not isinstance(func_data, dict):
                continue

            name = func_data.get("name", "")
            params = func_data.get("params", {})

            if not name:
                continue

            parsed = ParsedFunctionCall(name=name, arguments=params)
            chunks = self._response_formatter.format_streaming_chunks(
                index=idx, parsed_call=parsed, chunk_size=chunk_size
            )
            all_chunks.extend(chunks)

        return all_chunks


# Module-level singleton for convenience
_orchestrator: Optional[FunctionCallingOrchestrator] = None


def get_function_calling_orchestrator() -> FunctionCallingOrchestrator:
    """Get or create the global function calling orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = FunctionCallingOrchestrator()
    return _orchestrator


def reset_orchestrator() -> None:
    """Reset the global orchestrator (useful for testing)."""
    global _orchestrator
    _orchestrator = None


# =============================================================================
# Convenience Functions for Request Processing Integration
# =============================================================================


def should_skip_tool_injection(
    tools: Optional[List[Dict[str, Any]]],
    fc_state: Optional[FunctionCallingState] = None,
) -> bool:
    """Determine if tool catalog injection should be skipped.

    In native mode, the tool catalog is configured via UI automation,
    so we should skip injecting it into the prompt text.

    When fc_state is provided (from prepare_request), it takes precedence
    over static config to handle AUTO mode fallback correctly.

    Args:
        tools: List of tool definitions from the request.
        fc_state: Optional dynamic state from FunctionCallingOrchestrator.
                  If provided, uses the actual resolved mode (handles fallback).

    Returns:
        True if tool injection should be skipped (native mode successfully configured),
        False if tool catalog should be injected (emulated mode or fallback).
    """
    if not tools or len(tools) == 0:
        return True  # No tools, nothing to inject anyway

    # If we have dynamic state from the orchestrator, use it
    # This correctly handles AUTO mode fallback scenarios
    if fc_state is not None:
        # Only skip injection if native mode was successfully configured
        if fc_state.native_enabled and fc_state.tools_configured:
            return True
        # If fallback was used, we need to inject tools
        if fc_state.fallback_used:
            return False
        # If mode is explicitly EMULATED (either configured or after fallback)
        if fc_state.mode == FunctionCallingMode.EMULATED:
            return False
        # Native/Auto mode attempted but tools not configured - inject as fallback
        if not fc_state.tools_configured:
            return False
        return True

    # Fall back to static config check (backwards compatibility)
    mode_str = FUNCTION_CALLING_MODE.lower()

    # In emulated mode, always inject tools into prompt
    if mode_str == "emulated":
        return False

    # In native or auto mode, skip injection (tools configured via UI)
    if mode_str in ("native", "auto"):
        return True

    return False


def get_effective_function_calling_mode() -> FunctionCallingMode:
    """Get the currently configured function calling mode.

    Returns:
        The FunctionCallingMode enum value.
    """
    mode_str = FUNCTION_CALLING_MODE.lower()
    try:
        return FunctionCallingMode(mode_str)
    except ValueError:
        return FunctionCallingMode.EMULATED


__all__ = [
    "FunctionCallingOrchestrator",
    "FunctionCallingState",
    "NativeFunctionCallingError",
    "get_function_calling_orchestrator",
    "reset_orchestrator",
    "should_skip_tool_injection",
    "get_effective_function_calling_mode",
]
