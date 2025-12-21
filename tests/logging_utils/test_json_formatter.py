# -*- coding: utf-8 -*-
"""
Tests for JSONFormatter in logging_utils/core/rendering.py

Coverage target: 80%+
"""

import json
import logging

import pytest

from logging_utils.core.rendering import JSONFormatter


class TestJSONFormatter:
    """Tests for JSONFormatter class."""

    @pytest.fixture(autouse=True)
    def clean_context(self):
        """Clear context variables before each test to prevent leakage."""
        from logging_utils.core.context import request_id_var, source_var

        # Get tokens for any existing values and reset them
        try:
            _old_req_id = request_id_var.get()
            token1 = request_id_var.set("")
        except LookupError:
            token1 = None

        try:
            _old_source = source_var.get()
            token2 = source_var.set("SYS")
        except LookupError:
            token2 = None

        yield

        # Cleanup
        if token1:
            request_id_var.reset(token1)
        if token2:
            source_var.reset(token2)

    @pytest.fixture
    def formatter(self):
        """Create JSONFormatter instance."""
        return JSONFormatter()

    @pytest.fixture
    def sample_record(self):
        """Create a sample log record."""
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        return record

    def test_format_basic_record(self, formatter, sample_record):
        """Test formatting a basic log record."""
        output = formatter.format(sample_record)

        # Should be valid JSON
        parsed = json.loads(output)

        assert "timestamp" in parsed
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert parsed["logger"] == "test_logger"
        assert "source" in parsed  # Default source

    def test_format_with_request_id_context(self, formatter, sample_record):
        """Test formatting includes request_id from context."""
        from logging_utils.core.context import request_id_var

        token = request_id_var.set("req12345")
        try:
            output = formatter.format(sample_record)
            parsed = json.loads(output)

            assert parsed["request_id"] == "req12345"
        finally:
            request_id_var.reset(token)

    def test_format_with_source_context(self, formatter, sample_record):
        """Test formatting includes source from context."""
        from logging_utils.core.context import source_var

        token = source_var.set("API")
        try:
            output = formatter.format(sample_record)
            parsed = json.loads(output)

            assert "API" in parsed["source"]
        finally:
            source_var.reset(token)

    def test_format_without_context(self, formatter, sample_record):
        """Test formatting works without context variables set."""
        output = formatter.format(sample_record)
        parsed = json.loads(output)

        # Should have default values
        assert "source" in parsed
        assert "request_id" not in parsed or parsed.get("request_id") == ""

    def test_format_with_exception(self, formatter):
        """Test formatting includes exception info."""
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="/test/path.py",
            lineno=42,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "exception" in parsed
        assert parsed["exception"]["type"] == "ValueError"
        assert parsed["exception"]["message"] == "Test error"
        assert "traceback" in parsed["exception"]
        assert "ValueError: Test error" in parsed["exception"]["traceback"]

    def test_format_includes_extra_fields(self, formatter, sample_record):
        """Test formatting includes funcName, lineno, pathname."""
        sample_record.funcName = "test_function"
        sample_record.lineno = 123
        sample_record.pathname = "/test/module.py"

        output = formatter.format(sample_record)
        parsed = json.loads(output)

        assert parsed["funcName"] == "test_function"
        assert parsed["lineno"] == 123
        assert parsed["pathname"] == "/test/module.py"

    def test_format_timestamp_iso8601(self, formatter, sample_record):
        """Test timestamp is in ISO 8601 format."""
        output = formatter.format(sample_record)
        parsed = json.loads(output)

        timestamp = parsed["timestamp"]
        # Should be like: 2024-12-15T15:30:00.123Z
        assert "T" in timestamp
        assert timestamp.endswith("Z")
        assert len(timestamp) == 24  # YYYY-MM-DDTHH:MM:SS.mmmZ

    def test_format_different_log_levels(self, formatter):
        """Test formatting works for all log levels."""
        levels = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]

        for level, level_name in levels:
            record = logging.LogRecord(
                name="test",
                level=level,
                pathname="",
                lineno=1,
                msg=f"Test {level_name}",
                args=(),
                exc_info=None,
            )

            output = formatter.format(record)
            parsed = json.loads(output)

            assert parsed["level"] == level_name
            assert parsed["message"] == f"Test {level_name}"

    def test_format_unicode_message(self, formatter):
        """Test formatting handles unicode characters."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=1,
            msg="测试中文消息 🎉",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "测试中文消息" in parsed["message"]
        assert "🎉" in parsed["message"]

    def test_format_message_with_args(self, formatter):
        """Test formatting with format args."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=1,
            msg="User %s logged in with id %d",
            args=("john", 42),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "john" in parsed["message"]
        assert "42" in parsed["message"]

    def test_format_empty_message(self, formatter):
        """Test formatting empty message."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=1,
            msg="",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["message"] == ""

    def test_format_strips_request_id_whitespace(self, formatter, sample_record):
        """Test formatting strips whitespace from request_id."""
        from logging_utils.core.context import request_id_var

        token = request_id_var.set("  abc123  ")
        try:
            output = formatter.format(sample_record)
            parsed = json.loads(output)

            assert parsed["request_id"] == "abc123"
        finally:
            request_id_var.reset(token)

    def test_format_empty_request_id_excluded(self, formatter, sample_record):
        """Test empty request_id is not included in output."""
        from logging_utils.core.context import request_id_var

        token = request_id_var.set("   ")  # All whitespace
        try:
            output = formatter.format(sample_record)
            parsed = json.loads(output)

            # Empty request_id should not be in output
            assert "request_id" not in parsed or parsed["request_id"] == ""
        finally:
            request_id_var.reset(token)


class TestJSONFormatterIntegration:
    """Integration tests for JSONFormatter with logging handlers."""

    def test_with_stream_handler(self):
        """Test JSONFormatter works with StreamHandler."""
        import io

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        logger = logging.getLogger("test_json_integration")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("Integration test message")

        output = stream.getvalue()
        parsed = json.loads(output.strip())

        assert parsed["message"] == "Integration test message"
        assert parsed["level"] == "INFO"

    def test_multiple_log_entries(self):
        """Test multiple log entries produce valid JSON lines."""
        import io

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        logger = logging.getLogger("test_json_multi")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("First message")
        logger.warning("Second message")
        logger.error("Third message")

        output = stream.getvalue()
        lines = output.strip().split("\n")

        assert len(lines) == 3

        for line in lines:
            parsed = json.loads(line)
            assert "timestamp" in parsed
            assert "level" in parsed
            assert "message" in parsed
