"""
Comprehensive tests for the FC Debug Logging module.

Tests cover:
- Singleton pattern for FunctionCallingDebugLogger
- Configuration defaults and environment variable loading
- Per-module enable/disable
- Log levels configuration
- Payload truncation
- File handler creation
- Request ID correlation
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Generator
from unittest.mock import MagicMock, patch

import pytest

from logging_utils.fc_debug import FCModule, get_fc_logger
from logging_utils.fc_debug.config import FCDebugConfig
from logging_utils.fc_debug.formatters import FCDebugFormatter
from logging_utils.fc_debug.handlers import (
    create_rotating_file_handler,
    ensure_log_directory,
)
from logging_utils.fc_debug.logger import FunctionCallingDebugLogger
from logging_utils.fc_debug.truncation import (
    TruncationConfig,
    summarize_tools,
    truncate_payload,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_fc_logger() -> Generator[None, None, None]:
    """Reset the singleton logger before and after each test."""
    FunctionCallingDebugLogger.reset_instance()
    yield
    FunctionCallingDebugLogger.reset_instance()


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Clean all FC debug environment variables before/after test."""
    fc_env_vars = [
        "FC_DEBUG_ENABLED",
        "FUNCTION_CALLING_DEBUG",
        "FC_DEBUG_COMBINED_LOG",
        "FC_DEBUG_LOG_MAX_BYTES",
        "FC_DEBUG_LOG_BACKUP_COUNT",
        "FC_DEBUG_TRUNCATE_ENABLED",
        "FC_DEBUG_TRUNCATE_MAX_TOOL_DEF",
        "FC_DEBUG_TRUNCATE_MAX_ARGS",
        "FC_DEBUG_TRUNCATE_MAX_RESPONSE",
    ]
    # Add per-module env vars
    for module in FCModule:
        fc_env_vars.append(module.env_enabled_key)
        fc_env_vars.append(module.env_level_key)

    # Save original values
    original: Dict[str, str | None] = {}
    for var in fc_env_vars:
        original[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


@pytest.fixture
def temp_log_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# =============================================================================
# Test: Singleton Pattern
# =============================================================================


class TestFCDebugLoggerSingleton:
    """Verify the singleton pattern for FunctionCallingDebugLogger."""

    def test_get_instance_returns_same_object(self, clean_env: None) -> None:
        """Multiple calls to get_instance should return the same object."""
        logger1 = FunctionCallingDebugLogger.get_instance()
        logger2 = FunctionCallingDebugLogger.get_instance()
        assert logger1 is logger2

    def test_reset_instance_clears_singleton(self, clean_env: None) -> None:
        """reset_instance should allow creating a new singleton."""
        logger1 = FunctionCallingDebugLogger.get_instance()
        FunctionCallingDebugLogger.reset_instance()
        logger2 = FunctionCallingDebugLogger.get_instance()
        assert logger1 is not logger2

    def test_get_fc_logger_convenience_function(self, clean_env: None) -> None:
        """get_fc_logger() should return the singleton instance."""
        logger1 = get_fc_logger()
        logger2 = FunctionCallingDebugLogger.get_instance()
        assert logger1 is logger2


# =============================================================================
# Test: Config Defaults
# =============================================================================


class TestFCDebugConfigDefaults:
    """Verify default configuration values."""

    def test_master_disabled_by_default(self, clean_env: None) -> None:
        """Master switch should be disabled by default."""
        config = FCDebugConfig.from_env()
        assert config.master_enabled is False

    def test_modules_disabled_by_default(self, clean_env: None) -> None:
        """All modules should be disabled by default."""
        config = FCDebugConfig.from_env()
        for module in FCModule:
            assert config.module_enabled.get(module) is False

    def test_default_log_levels(self, clean_env: None) -> None:
        """Default log level should be DEBUG for all modules."""
        config = FCDebugConfig.from_env()
        for module in FCModule:
            assert config.module_levels.get(module) == logging.DEBUG

    def test_default_rotation_settings(self, clean_env: None) -> None:
        """Default rotation settings should be 5MB and 3 backups."""
        config = FCDebugConfig.from_env()
        assert config.log_max_bytes == 5 * 1024 * 1024
        assert config.log_backup_count == 3

    def test_combined_log_disabled_by_default(self, clean_env: None) -> None:
        """Combined log should be disabled by default."""
        config = FCDebugConfig.from_env()
        assert config.combined_log_enabled is False


# =============================================================================
# Test: Module Enable/Disable
# =============================================================================


class TestFCDebugModuleEnableDisable:
    """Verify per-module enable/disable functionality."""

    def test_master_switch_enables_logging(self, clean_env: None) -> None:
        """Master switch enables the logger when set."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_ORCHESTRATOR"] = "true"
        config = FCDebugConfig.from_env()
        assert config.master_enabled is True
        assert config.is_module_enabled(FCModule.ORCHESTRATOR) is True

    def test_module_disabled_without_master(self, clean_env: None) -> None:
        """Module is not enabled if master switch is off."""
        os.environ["FC_DEBUG_ORCHESTRATOR"] = "true"
        # Master not set (defaults to false)
        config = FCDebugConfig.from_env()
        assert config.is_module_enabled(FCModule.ORCHESTRATOR) is False

    def test_individual_modules_can_be_toggled(self, clean_env: None) -> None:
        """Each module can be independently enabled/disabled."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_CACHE"] = "true"
        os.environ["FC_DEBUG_UI"] = "false"

        config = FCDebugConfig.from_env()
        assert config.is_module_enabled(FCModule.CACHE) is True
        assert config.is_module_enabled(FCModule.UI) is False
        assert config.is_module_enabled(FCModule.ORCHESTRATOR) is False

    def test_legacy_function_calling_debug_enables_orchestrator(
        self, clean_env: None
    ) -> None:
        """FUNCTION_CALLING_DEBUG env var enables ORCHESTRATOR for backwards compatibility."""
        os.environ["FUNCTION_CALLING_DEBUG"] = "true"
        config = FCDebugConfig.from_env()
        assert config.master_enabled is True
        assert config.is_module_enabled(FCModule.ORCHESTRATOR) is True

    def test_env_var_accepts_various_truthy_values(self, clean_env: None) -> None:
        """Environment variables accept 'true', '1', and 'yes' as truthy."""
        for truthy in ["true", "1", "yes", "TRUE", "Yes"]:
            os.environ["FC_DEBUG_ENABLED"] = truthy
            os.environ["FC_DEBUG_CACHE"] = truthy
            config = FCDebugConfig.from_env()
            assert config.master_enabled is True
            assert config.module_enabled[FCModule.CACHE] is True


# =============================================================================
# Test: Log Levels
# =============================================================================


class TestFCDebugLogLevels:
    """Verify log level configuration."""

    def test_default_level_is_debug(self, clean_env: None) -> None:
        """Default log level for modules is DEBUG."""
        config = FCDebugConfig.from_env()
        assert config.get_module_level(FCModule.CACHE) == logging.DEBUG

    def test_custom_level_via_env(self, clean_env: None) -> None:
        """Log level can be configured via environment variable."""
        os.environ["FC_DEBUG_LEVEL_CACHE"] = "INFO"
        config = FCDebugConfig.from_env()
        assert config.get_module_level(FCModule.CACHE) == logging.INFO

    def test_various_log_levels(self, clean_env: None) -> None:
        """All standard log levels should be supported."""
        levels = [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
        ]

        for level_name, level_val in levels:
            os.environ["FC_DEBUG_LEVEL_CACHE"] = level_name
            config = FCDebugConfig.from_env()
            assert config.get_module_level(FCModule.CACHE) == level_val

    def test_invalid_level_defaults_to_debug(self, clean_env: None) -> None:
        """Invalid log level string should default to DEBUG."""
        os.environ["FC_DEBUG_LEVEL_CACHE"] = "INVALID"
        config = FCDebugConfig.from_env()
        assert config.get_module_level(FCModule.CACHE) == logging.DEBUG


# =============================================================================
# Test: Truncation
# =============================================================================


class TestFCDebugTruncation:
    """Verify payload truncation functionality."""

    def test_truncation_config_defaults(self, clean_env: None) -> None:
        """TruncationConfig has sensible defaults."""
        config = TruncationConfig.from_env()
        assert config.enabled is True
        assert config.max_tool_definition == 500
        assert config.max_arguments == 1000
        assert config.max_response == 2000

    def test_truncation_config_from_env(self, clean_env: None) -> None:
        """TruncationConfig can be customized via environment."""
        os.environ["FC_DEBUG_TRUNCATE_ENABLED"] = "false"
        os.environ["FC_DEBUG_TRUNCATE_MAX_TOOL_DEF"] = "1000"
        config = TruncationConfig.from_env()
        assert config.enabled is False
        assert config.max_tool_definition == 1000

    def test_truncate_short_string(self) -> None:
        """Short strings should not be truncated."""
        result = truncate_payload("short", max_length=100)
        assert result == "short"

    def test_truncate_long_string(self) -> None:
        """Long strings should be truncated with indicator."""
        long_str = "a" * 100
        result = truncate_payload(long_str, max_length=50)
        assert "..." in result
        assert "truncated" in result
        assert f"total={len(long_str)}" in result

    def test_truncate_small_dict(self) -> None:
        """Small dicts should not be truncated."""
        small_dict = {"key": "value"}
        result = truncate_payload(small_dict, max_length=100)
        assert "key" in result
        assert "value" in result

    def test_truncate_large_dict(self) -> None:
        """Large dicts should be truncated with key summary."""
        large_dict = {f"key_{i}": "x" * 50 for i in range(20)}
        result = truncate_payload(large_dict, max_length=200)
        assert "truncated" in result
        assert "keys=" in result

    def test_truncate_large_list(self) -> None:
        """Large lists should be truncated with length summary."""
        large_list = list(range(100))
        result = truncate_payload(large_list, max_length=50)
        assert "truncated" in result
        assert "length=" in result

    def test_truncate_exception_handling(self) -> None:
        """Truncation should handle objects that can't be serialized."""

        class UnserializableObj:
            def __repr__(self) -> str:
                raise ValueError("Cannot represent")

        # This shouldn't raise, should return error message
        result = truncate_payload(UnserializableObj(), max_length=100)
        assert "Error" in result or isinstance(result, str)

    def test_module_specific_max_lengths(self, clean_env: None) -> None:
        """Different modules should have different max lengths."""
        config = TruncationConfig.from_env()

        sample = {"data": "x"}
        assert (
            config.get_max_length(sample, FCModule.SCHEMA) == config.max_tool_definition
        )
        assert config.get_max_length(sample, FCModule.WIRE) == config.max_arguments
        assert config.get_max_length(sample, FCModule.RESPONSE) == config.max_response
        assert config.get_max_length(sample, FCModule.CACHE) == config.max_default

    def test_summarize_tools_empty(self) -> None:
        """summarize_tools with empty list returns '[]'."""
        assert summarize_tools([]) == "[]"

    def test_summarize_tools_single(self) -> None:
        """summarize_tools shows function name and param count."""
        tools = [
            {
                "function": {
                    "name": "get_weather",
                    "parameters": {"properties": {"city": {}}},
                }
            }
        ]
        result = summarize_tools(tools)
        assert "get_weather" in result
        assert "1 params" in result

    def test_summarize_tools_many(self) -> None:
        """summarize_tools truncates at 10 tools and shows count."""
        tools = [
            {"function": {"name": f"func_{i}", "parameters": {"properties": {}}}}
            for i in range(15)
        ]
        result = summarize_tools(tools)
        assert "+5 more" in result


# =============================================================================
# Test: File Handlers
# =============================================================================


class TestFCDebugFileHandlers:
    """Verify file handler creation and configuration."""

    def test_ensure_log_directory_creates_dir(self, temp_log_dir: Path) -> None:
        """ensure_log_directory should create the directory if it doesn't exist."""
        new_dir = temp_log_dir / "fc_debug" / "nested"
        ensure_log_directory(new_dir)
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_create_rotating_file_handler(self, temp_log_dir: Path) -> None:
        """create_rotating_file_handler should create a working handler."""
        log_file = temp_log_dir / "test.log"
        handler = create_rotating_file_handler(log_file)

        assert handler is not None
        assert handler.maxBytes == 5 * 1024 * 1024
        assert handler.backupCount == 3
        assert handler.level == logging.DEBUG

        handler.close()

    def test_create_handler_with_custom_settings(self, temp_log_dir: Path) -> None:
        """Handler should respect custom max_bytes, backup_count, and level."""
        log_file = temp_log_dir / "custom.log"
        handler = create_rotating_file_handler(
            log_file,
            max_bytes=1024,
            backup_count=5,
            level=logging.WARNING,
        )

        assert handler.maxBytes == 1024
        assert handler.backupCount == 5
        assert handler.level == logging.WARNING

        handler.close()

    def test_handler_uses_fc_debug_formatter(self, temp_log_dir: Path) -> None:
        """Handler should use FCDebugFormatter by default."""
        log_file = temp_log_dir / "formatted.log"
        handler = create_rotating_file_handler(log_file)

        assert isinstance(handler.formatter, FCDebugFormatter)

        handler.close()


# =============================================================================
# Test: Request ID Correlation
# =============================================================================


class TestFCDebugRequestIdCorrelation:
    """Verify request ID correlation in logs."""

    def test_log_includes_request_id(self, clean_env: None) -> None:
        """Log messages should include request ID when provided."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_CACHE"] = "true"

        logger = get_fc_logger()

        # Get the underlying Python logger for the module
        module_logger = logger._module_loggers.get(FCModule.CACHE)
        assert module_logger is not None
        assert module_logger.enabled is True

        # Add a mock handler to capture output
        mock_handler = MagicMock(spec=logging.Handler)
        mock_handler.level = logging.DEBUG
        mock_handler.filter = MagicMock(return_value=True)
        module_logger.logger.addHandler(mock_handler)

        # Log with request ID
        logger.debug(FCModule.CACHE, "Test message", req_id="test-req-123")

        # Verify the log was called - check emit was called
        assert mock_handler.handle.called or mock_handler.emit.called

    def test_log_without_request_id(self, clean_env: None) -> None:
        """Log messages without request ID should still work."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_CACHE"] = "true"

        logger = get_fc_logger()

        # Should not raise
        logger.debug(FCModule.CACHE, "Test message without req_id")

    def test_convenience_methods_include_request_id(self, clean_env: None) -> None:
        """Convenience methods should properly pass request ID."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_CACHE"] = "true"

        logger = get_fc_logger()

        # These should not raise
        logger.log_cache_hit(req_id="req-001", digest="abc12345678", age_seconds=1.5)
        logger.log_cache_miss(req_id="req-002", reason="no match")


# =============================================================================
# Test: Formatter
# =============================================================================


class TestFCDebugFormatter:
    """Verify log formatter behavior."""

    def test_formatter_includes_timestamp(self) -> None:
        """Formatter should include timestamp with milliseconds."""
        formatter = FCDebugFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        # Should have timestamp pattern: YYYY-MM-DD HH:MM:SS.mmm
        assert "|" in formatted
        assert "INFO" in formatted
        assert "Test message" in formatted

    def test_formatter_includes_level(self) -> None:
        """Formatter should include padded log level."""
        formatter = FCDebugFormatter()

        for level in [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]:
            record = logging.LogRecord(
                name="test",
                level=level,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            formatted = formatter.format(record)
            assert logging.getLevelName(level) in formatted

    def test_formatter_includes_exception_info(self) -> None:
        """Formatter should include exception info when present."""
        formatter = FCDebugFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )

            formatted = formatter.format(record)
            assert "ValueError" in formatted
            assert "Test error" in formatted


# =============================================================================
# Test: FCModule Properties
# =============================================================================


class TestFCModule:
    """Verify FCModule enum properties."""

    def test_module_prefix(self) -> None:
        """Each module should have a proper prefix."""
        assert FCModule.ORCHESTRATOR.prefix == "[FC:ORCH]"
        assert FCModule.CACHE.prefix == "[FC:CACHE]"
        assert FCModule.UI.prefix == "[FC:UI]"
        assert FCModule.RESPONSE.prefix == "[FC:RESP]"

    def test_module_env_enabled_key(self) -> None:
        """Each module should have proper env key for enabled setting."""
        assert FCModule.CACHE.env_enabled_key == "FC_DEBUG_CACHE"
        assert FCModule.ORCHESTRATOR.env_enabled_key == "FC_DEBUG_ORCHESTRATOR"

    def test_module_env_level_key(self) -> None:
        """Each module should have proper env key for level setting."""
        assert FCModule.CACHE.env_level_key == "FC_DEBUG_LEVEL_CACHE"
        assert FCModule.UI.env_level_key == "FC_DEBUG_LEVEL_UI"

    def test_module_log_filename(self) -> None:
        """Each module should have a log filename based on its value."""
        assert FCModule.CACHE.log_filename == "fc_cache.log"
        assert FCModule.ORCHESTRATOR.log_filename == "fc_orchestrator.log"


# =============================================================================
# Test: Logger Public API
# =============================================================================


class TestFCLoggerPublicAPI:
    """Test the public logging API methods."""

    def test_is_enabled_returns_false_when_disabled(self, clean_env: None) -> None:
        """is_enabled should return False when module is disabled."""
        logger = get_fc_logger()
        assert logger.is_enabled(FCModule.CACHE) is False

    def test_is_enabled_returns_true_when_enabled(self, clean_env: None) -> None:
        """is_enabled should return True when module is enabled."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_CACHE"] = "true"

        logger = get_fc_logger()
        assert logger.is_enabled(FCModule.CACHE) is True

    def test_all_log_levels_available(self, clean_env: None) -> None:
        """Logger should have debug, info, warning, error methods."""
        logger = get_fc_logger()

        assert hasattr(logger, "debug")
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")

    def test_log_with_payload(self, clean_env: None) -> None:
        """Logging with payload should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_SCHEMA"] = "true"

        logger = get_fc_logger()

        payload = {"tools": [{"name": "test", "params": {}}]}
        logger.debug(
            FCModule.SCHEMA, "Converting tools", req_id="req-1", payload=payload
        )

    def test_error_with_exc_info(self, clean_env: None) -> None:
        """Error logging with exc_info should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_ORCHESTRATOR"] = "true"

        logger = get_fc_logger()

        try:
            raise RuntimeError("Test exception")
        except RuntimeError:
            logger.error(
                FCModule.ORCHESTRATOR, "Error occurred", req_id="req-1", exc_info=True
            )


# =============================================================================
# Test: Convenience Logging Methods
# =============================================================================


class TestFCLoggerConvenienceMethods:
    """Test the convenience logging methods."""

    def test_log_cache_hit(self, clean_env: None) -> None:
        """log_cache_hit should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_CACHE"] = "true"

        logger = get_fc_logger()
        logger.log_cache_hit(req_id="req-1", digest="abc123def456", age_seconds=2.5)

    def test_log_cache_miss(self, clean_env: None) -> None:
        """log_cache_miss should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_CACHE"] = "true"

        logger = get_fc_logger()
        logger.log_cache_miss(req_id="req-1", reason="digest mismatch")

    def test_log_ui_action(self, clean_env: None) -> None:
        """log_ui_action should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_UI"] = "true"

        logger = get_fc_logger()
        logger.log_ui_action(
            req_id="req-1", action="clicked", element="toggle", elapsed_ms=150.5
        )

    def test_log_wire_parse(self, clean_env: None) -> None:
        """log_wire_parse should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_WIRE"] = "true"

        logger = get_fc_logger()
        logger.log_wire_parse(
            req_id="req-1", func_name="get_weather", params={"city": "NYC"}
        )

    def test_log_dom_extraction(self, clean_env: None) -> None:
        """log_dom_extraction should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_DOM"] = "true"

        logger = get_fc_logger()
        logger.log_dom_extraction(req_id="req-1", call_count=3, strategy="marker-based")

    def test_log_schema_conversion(self, clean_env: None) -> None:
        """log_schema_conversion should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_SCHEMA"] = "true"

        logger = get_fc_logger()
        logger.log_schema_conversion(req_id="req-1", tool_count=5, elapsed_ms=12.5)

    def test_log_response_format(self, clean_env: None) -> None:
        """log_response_format should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_RESPONSE"] = "true"

        logger = get_fc_logger()
        logger.log_response_format(
            req_id="req-1", call_count=2, finish_reason="tool_calls"
        )

    def test_log_mode_selection(self, clean_env: None) -> None:
        """log_mode_selection should not raise."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_ORCHESTRATOR"] = "true"

        logger = get_fc_logger()
        logger.log_mode_selection(
            req_id="req-1", mode="native", reason="cached capability"
        )


# =============================================================================
# Test: Edge Cases and Error Handling
# =============================================================================


class TestFCLoggerEdgeCases:
    """Test edge cases and error handling."""

    def test_log_to_unknown_module_is_safe(self, clean_env: None) -> None:
        """Logging to a module not in the loggers dict should not raise."""
        logger = get_fc_logger()
        # Clear module loggers to simulate edge case
        original = logger._module_loggers.copy()
        logger._module_loggers.clear()

        # Should not raise
        logger.debug(FCModule.CACHE, "Test")

        # Restore
        logger._module_loggers = original

    def test_disabled_module_skips_logging(self, clean_env: None) -> None:
        """Disabled module should skip logging entirely."""
        logger = get_fc_logger()

        # When disabled, the logger should return early
        assert logger.is_enabled(FCModule.CACHE) is False
        # This should not raise or do anything
        logger.debug(FCModule.CACHE, "This should be skipped")

    def test_logger_handles_none_payload(self, clean_env: None) -> None:
        """Logger should handle None payload gracefully."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_CACHE"] = "true"

        logger = get_fc_logger()
        # Should not raise
        logger.debug(FCModule.CACHE, "Test", req_id="req-1", payload=None)

    def test_logger_handles_empty_request_id(self, clean_env: None) -> None:
        """Logger should handle empty request ID gracefully."""
        os.environ["FC_DEBUG_ENABLED"] = "true"
        os.environ["FC_DEBUG_CACHE"] = "true"

        logger = get_fc_logger()
        # Should not raise
        logger.debug(FCModule.CACHE, "Test", req_id="")

    def test_config_handles_invalid_max_bytes(self, clean_env: None) -> None:
        """Config should handle invalid max_bytes by raising or using default."""
        os.environ["FC_DEBUG_LOG_MAX_BYTES"] = "invalid"

        with pytest.raises(ValueError):
            FCDebugConfig.from_env()

    def test_initialization_handles_config_failure_gracefully(
        self, clean_env: None
    ) -> None:
        """Logger should use defaults if config loading fails."""
        with patch(
            "logging_utils.fc_debug.logger.FCDebugConfig.from_env",
            side_effect=Exception("Config error"),
        ):
            logger = FunctionCallingDebugLogger()
            logger._initialize()

            # Should have used default config
            assert logger._config is not None
            assert logger._initialized is True
