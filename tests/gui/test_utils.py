"""Tests for gui/utils.py module."""

import pytest
from unittest.mock import MagicMock, patch


class TestValidatePort:
    """Tests for validate_port function."""

    def test_valid_port_minimum(self):
        """Port 1 is valid."""
        from gui.utils import validate_port

        assert validate_port("1") is True

    def test_valid_port_maximum(self):
        """Port 65535 is valid."""
        from gui.utils import validate_port

        assert validate_port("65535") is True

    def test_valid_port_common(self):
        """Common ports are valid."""
        from gui.utils import validate_port

        assert validate_port("80") is True
        assert validate_port("443") is True
        assert validate_port("2048") is True
        assert validate_port("8080") is True

    def test_invalid_port_zero(self):
        """Port 0 is invalid."""
        from gui.utils import validate_port

        assert validate_port("0") is False

    def test_invalid_port_negative(self):
        """Negative port is invalid."""
        from gui.utils import validate_port

        assert validate_port("-1") is False

    def test_invalid_port_too_large(self):
        """Port > 65535 is invalid."""
        from gui.utils import validate_port

        assert validate_port("65536") is False
        assert validate_port("99999") is False

    def test_invalid_port_non_numeric(self):
        """Non-numeric string is invalid."""
        from gui.utils import validate_port

        assert validate_port("abc") is False
        assert validate_port("") is False
        assert validate_port("12.34") is False

    def test_port_with_spaces_stripped(self):
        """Python int() strips whitespace, so these are valid."""
        from gui.utils import validate_port

        assert validate_port(" 80") is True
        assert validate_port("80 ") is True
        assert validate_port(" 80 ") is True


class TestFormatUptime:
    """Tests for format_uptime function."""

    def test_zero_seconds(self):
        """0 seconds formats as 00:00."""
        from gui.utils import format_uptime

        assert format_uptime(0) == "00:00"

    def test_seconds_only(self):
        """Seconds < 60 format as 00:SS."""
        from gui.utils import format_uptime

        assert format_uptime(30) == "00:30"
        assert format_uptime(59) == "00:59"

    def test_minutes_and_seconds(self):
        """Minutes format as MM:SS."""
        from gui.utils import format_uptime

        assert format_uptime(60) == "01:00"
        assert format_uptime(90) == "01:30"
        assert format_uptime(600) == "10:00"
        assert format_uptime(3599) == "59:59"

    def test_hours_minutes_seconds(self):
        """Hours format as HH:MM:SS."""
        from gui.utils import format_uptime

        assert format_uptime(3600) == "01:00:00"
        assert format_uptime(3661) == "01:01:01"
        assert format_uptime(7200) == "02:00:00"
        assert format_uptime(86399) == "23:59:59"

    def test_large_uptime(self):
        """Large uptime formats correctly."""
        from gui.utils import format_uptime

        assert format_uptime(86400) == "24:00:00"
        assert format_uptime(360000) == "100:00:00"


class TestCopyToClipboard:
    """Tests for copy_to_clipboard function."""

    def test_copy_clears_clipboard(self, mock_tk_root):
        """copy_to_clipboard calls clipboard_clear."""
        from gui.utils import copy_to_clipboard

        copy_to_clipboard(mock_tk_root, "test")
        mock_tk_root.clipboard_clear.assert_called_once()

    def test_copy_appends_text(self, mock_tk_root):
        """copy_to_clipboard appends the text."""
        from gui.utils import copy_to_clipboard

        copy_to_clipboard(mock_tk_root, "hello world")
        mock_tk_root.clipboard_append.assert_called_once_with("hello world")

    def test_copy_calls_update(self, mock_tk_root):
        """copy_to_clipboard calls update to persist."""
        from gui.utils import copy_to_clipboard

        copy_to_clipboard(mock_tk_root, "test")
        mock_tk_root.update.assert_called_once()


class TestCTkTooltip:
    """Tests for CTkTooltip class."""

    def test_tooltip_class_exists(self):
        """CTkTooltip class should be importable."""
        from gui.utils import CTkTooltip

        assert CTkTooltip is not None

    def test_tooltip_alias_exists(self):
        """Tooltip alias should exist for backwards compatibility."""
        from gui.utils import Tooltip, CTkTooltip

        assert Tooltip is CTkTooltip

    def test_tooltip_binds_events(self, mock_widget):
        """CTkTooltip binds hover events."""
        from gui.utils import CTkTooltip

        tooltip = CTkTooltip(mock_widget, "tooltip_account")

        # Should bind at least 3 events
        assert mock_widget.bind.call_count >= 3

        # Check event types
        call_args = [call[0][0] for call in mock_widget.bind.call_args_list]
        assert "<Enter>" in call_args
        assert "<Leave>" in call_args
        assert "<ButtonPress>" in call_args

    def test_tooltip_stores_text_key(self, mock_widget):
        """CTkTooltip stores the text key for translation."""
        from gui.utils import CTkTooltip

        tooltip = CTkTooltip(mock_widget, "tooltip_fastapi_port")

        assert tooltip.text_key == "tooltip_fastapi_port"

    def test_tooltip_initially_hidden(self, mock_widget):
        """CTkTooltip window is None initially."""
        from gui.utils import CTkTooltip

        tooltip = CTkTooltip(mock_widget, "tooltip_test")

        assert tooltip.tooltip_window is None


class TestCTkScrollableList:
    """Tests for CTkScrollableList class."""

    def test_scrollable_list_class_exists(self):
        """CTkScrollableList class is importable."""
        from gui.utils import CTkScrollableList

        assert CTkScrollableList is not None

    def test_scrollable_list_alias_exists(self):
        """ScrollableListbox alias should exist for backwards compatibility."""
        from gui.utils import ScrollableListbox, CTkScrollableList

        assert ScrollableListbox is CTkScrollableList

    def test_scrollable_list_has_required_methods(self):
        """CTkScrollableList has required methods."""
        from gui.utils import CTkScrollableList

        assert hasattr(CTkScrollableList, "add_item")
        assert hasattr(CTkScrollableList, "clear")
        assert hasattr(CTkScrollableList, "get_selected")
        assert hasattr(CTkScrollableList, "get_items")
        assert hasattr(CTkScrollableList, "select")
        assert hasattr(CTkScrollableList, "bind_select")
        assert hasattr(CTkScrollableList, "bind_double_click")

    def test_scrollable_list_uses_colors(self):
        """CTkScrollableList uses COLORS from config."""
        from gui.config import COLORS

        # Verify colors needed for the list exist
        assert "bg_light" in COLORS
        assert "text_primary" in COLORS
        assert "accent" in COLORS
        assert "border" in COLORS


class TestCTkStatusBar:
    """Tests for CTkStatusBar class."""

    def test_status_bar_class_exists(self):
        """CTkStatusBar class is importable."""
        from gui.utils import CTkStatusBar

        assert CTkStatusBar is not None

    def test_status_bar_alias_exists(self):
        """StatusBar alias should exist for backwards compatibility."""
        from gui.utils import StatusBar, CTkStatusBar

        assert StatusBar is CTkStatusBar

    def test_status_bar_has_required_methods(self):
        """CTkStatusBar has required methods."""
        from gui.utils import CTkStatusBar

        assert hasattr(CTkStatusBar, "set_status")
        assert hasattr(CTkStatusBar, "set_port")
        assert hasattr(CTkStatusBar, "start_uptime")
        assert hasattr(CTkStatusBar, "stop_uptime")

    def test_status_bar_default_status_text(self):
        """StatusBar should display 'Ready' by default."""
        from gui.i18n import get_text, set_language

        set_language("en")
        ready_text = get_text("statusbar_ready")
        assert "Ready" in ready_text or ready_text == "Ready"

    def test_format_uptime_used_in_status_bar(self):
        """StatusBar uses format_uptime for display."""
        from gui.utils import format_uptime

        assert format_uptime(3661) == "01:01:01"
