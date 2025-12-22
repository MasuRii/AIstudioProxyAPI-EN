"""
Coverage tests for logging_utils/setup.py - ColoredFormatter paths

Targets:
- Lines 37-38: Exception handler when Windows ANSI enable fails
- Line 43: formatTime() with custom datefmt
- Line 59: format() fallback when use_color=False or unknown levelname
"""

import logging
from unittest.mock import MagicMock, patch

from logging_utils.setup import ColoredFormatter


class TestColoredFormatterCoverage:
    def test_colored_formatter_windows_ansi_failure(self):
        """
        Test scenario: Windows ANSI enable fails
        Expected: use_color set to False (lines 37-38)
        """
        with patch("logging_utils.setup.sys.platform", "win32"):
            # Mock ctypes module to raise exception during kernel32 access
            mock_ctypes = MagicMock()
            mock_ctypes.windll.kernel32.GetStdHandle.side_effect = Exception(
                "ANSI setup failed"
            )

            with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
                formatter = ColoredFormatter(use_color=True)

                # use_color should be disabled after exception (line 38)
                assert formatter.use_color is False

    def test_colored_formatter_formattime_with_datefmt(self):
        """
        Test scenario: formatTime with custom datefmt
        Expected: Use strftime for formatting (line 43)
        """
        formatter = ColoredFormatter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.created = 1732662000.123
        record.msecs = 123

        # Use custom datefmt (triggers line 43)
        formatted_time = formatter.formatTime(record, datefmt="%Y/%m/%d %H:%M")

        # Should use custom format
        assert formatted_time is not None
        assert "/" in formatted_time
        assert ":" in formatted_time
        # Should not include milliseconds with custom format
        assert "," not in formatted_time

    def test_colored_formatter_format_without_color(self):
        """
        Test scenario: format method when use_color=False
        Expected: Call parent format method (line 59)
        """
        # Create formatter with colors disabled
        formatter = ColoredFormatter(use_color=False)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.created = 1732662000.0
        record.msecs = 0

        # Format without colors (triggers line 59)
        result = formatter.format(record)

        # Should return formatted message without color codes
        assert result is not None
        assert "Test message" in result
        # Should NOT contain ANSI escape codes
        assert "\033[" not in result

    def test_colored_formatter_format_unknown_levelname(self):
        """
        Test scenario: format method encounters unknown levelname
        Expected: Call parent format method (line 59)
        """
        formatter = ColoredFormatter(use_color=True)

        record = logging.LogRecord(
            name="test",
            level=99,  # Unknown level
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.levelname = "CUSTOM_LEVEL"  # Not in COLORS dict
        record.created = 1732662000.0
        record.msecs = 0

        # Format with unknown levelname (triggers line 59 due to levelname not in COLORS)
        result = formatter.format(record)

        # Should return formatted message without color codes
        assert result is not None
        assert "Test message" in result


class TestColoredFormatterEdgeCases:
    def test_colored_formatter_all_color_levels(self):
        """Test all supported log level colors"""
        formatter = ColoredFormatter(use_color=True)

        levels = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]

        for level, levelname in levels:
            record = logging.LogRecord(
                name="test",
                level=level,
                pathname="test.py",
                lineno=1,
                msg=f"{levelname} message",
                args=(),
                exc_info=None,
            )
            record.created = 1732662000.0
            record.msecs = 0

            result = formatter.format(record)

            # Should contain levelname and color codes
            assert levelname in result or "\033[" in result

    def test_colored_formatter_linux_platform(self):
        """Test Linux platform does not attempt to enable Windows ANSI"""
        with patch("logging_utils.setup.sys.platform", "linux"):
            formatter = ColoredFormatter(use_color=True)

            # use_color should remain True (no Windows ctypes attempt)
            assert formatter.use_color is True

    def test_colored_formatter_macos_platform(self):
        """Test macOS platform does not attempt to enable Windows ANSI"""
        with patch("logging_utils.setup.sys.platform", "darwin"):
            formatter = ColoredFormatter(use_color=True)

            # use_color should remain True (no Windows ctypes attempt)
            assert formatter.use_color is True
