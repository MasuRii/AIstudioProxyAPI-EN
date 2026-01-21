"""Tests for gui/theme.py module."""

import pytest
from unittest.mock import patch, MagicMock


class TestGetAppearanceMode:
    """Tests for get_appearance_mode function."""

    def test_returns_default_mode(self):
        """Should return the default mode on first call."""
        from gui import theme

        # Reset module state
        theme._current_mode = "dark"
        assert theme.get_appearance_mode() == "dark"

    def test_returns_current_mode_after_set(self):
        """Should return the mode that was set."""
        from gui import theme

        theme._current_mode = "light"
        assert theme.get_appearance_mode() == "light"

        theme._current_mode = "system"
        assert theme.get_appearance_mode() == "system"


class TestSetAppearanceMode:
    """Tests for set_appearance_mode function."""

    @patch("gui.theme.ctk")
    def test_sets_dark_mode(self, mock_ctk):
        """Should set dark mode correctly."""
        from gui import theme

        theme._on_change_callbacks = []
        theme.set_appearance_mode("dark")

        assert theme._current_mode == "dark"
        mock_ctk.set_appearance_mode.assert_called_with("dark")

    @patch("gui.theme.ctk")
    def test_sets_light_mode(self, mock_ctk):
        """Should set light mode correctly."""
        from gui import theme

        theme._on_change_callbacks = []
        theme.set_appearance_mode("light")

        assert theme._current_mode == "light"
        mock_ctk.set_appearance_mode.assert_called_with("light")

    @patch("gui.theme.ctk")
    def test_sets_system_mode(self, mock_ctk):
        """Should set system mode correctly."""
        from gui import theme

        theme._on_change_callbacks = []
        theme.set_appearance_mode("system")

        assert theme._current_mode == "system"
        mock_ctk.set_appearance_mode.assert_called_with("system")

    @patch("gui.theme.ctk")
    def test_invalid_mode_defaults_to_dark(self, mock_ctk):
        """Should default to dark for invalid mode."""
        from gui import theme

        theme._on_change_callbacks = []
        theme.set_appearance_mode("invalid")

        assert theme._current_mode == "dark"
        mock_ctk.set_appearance_mode.assert_called_with("dark")

    @patch("gui.theme.ctk")
    def test_notifies_callbacks(self, mock_ctk):
        """Should notify registered callbacks on mode change."""
        from gui import theme

        callback = MagicMock()
        theme._on_change_callbacks = [callback]

        theme.set_appearance_mode("light")

        callback.assert_called_once_with("light")

    @patch("gui.theme.ctk")
    def test_handles_callback_exception(self, mock_ctk):
        """Should continue even if callback raises exception."""
        from gui import theme

        bad_callback = MagicMock(side_effect=Exception("Test error"))
        good_callback = MagicMock()
        theme._on_change_callbacks = [bad_callback, good_callback]

        # Should not raise
        theme.set_appearance_mode("dark")

        bad_callback.assert_called_once()
        good_callback.assert_called_once_with("dark")


class TestToggleAppearanceMode:
    """Tests for toggle_appearance_mode function."""

    @patch("gui.theme.ctk")
    def test_toggle_from_dark_to_light(self, mock_ctk):
        """Should toggle from dark to light."""
        from gui import theme

        theme._current_mode = "dark"
        theme._on_change_callbacks = []

        result = theme.toggle_appearance_mode()

        assert result == "light"
        assert theme._current_mode == "light"

    @patch("gui.theme.ctk")
    def test_toggle_from_light_to_dark(self, mock_ctk):
        """Should toggle from light to dark."""
        from gui import theme

        theme._current_mode = "light"
        theme._on_change_callbacks = []

        result = theme.toggle_appearance_mode()

        assert result == "dark"
        assert theme._current_mode == "dark"

    @patch("gui.theme.ctk")
    def test_toggle_from_system_to_dark(self, mock_ctk):
        """Should toggle from system to dark (system is treated as not-dark)."""
        from gui import theme

        theme._current_mode = "system"
        theme._on_change_callbacks = []

        result = theme.toggle_appearance_mode()

        assert result == "dark"
        assert theme._current_mode == "dark"


class TestIsDarkMode:
    """Tests for is_dark_mode function."""

    def test_dark_mode_returns_true(self):
        """Should return True when mode is dark."""
        from gui import theme

        theme._current_mode = "dark"
        assert theme.is_dark_mode() is True

    def test_light_mode_returns_false(self):
        """Should return False when mode is light."""
        from gui import theme

        theme._current_mode = "light"
        assert theme.is_dark_mode() is False

    @patch("gui.theme.ctk")
    def test_system_mode_checks_actual(self, mock_ctk):
        """Should check actual system setting when mode is system."""
        from gui import theme

        theme._current_mode = "system"

        mock_ctk.get_appearance_mode.return_value = "Dark"
        assert theme.is_dark_mode() is True

        mock_ctk.get_appearance_mode.return_value = "Light"
        assert theme.is_dark_mode() is False


class TestThemeCallbacks:
    """Tests for callback registration functions."""

    def test_on_theme_change_registers_callback(self):
        """Should register a callback."""
        from gui import theme

        theme._on_change_callbacks = []
        callback = MagicMock()

        theme.on_theme_change(callback)

        assert callback in theme._on_change_callbacks

    def test_on_theme_change_prevents_duplicates(self):
        """Should not register the same callback twice."""
        from gui import theme

        theme._on_change_callbacks = []
        callback = MagicMock()

        theme.on_theme_change(callback)
        theme.on_theme_change(callback)

        assert len(theme._on_change_callbacks) == 1

    def test_remove_theme_callback(self):
        """Should remove a registered callback."""
        from gui import theme

        callback = MagicMock()
        theme._on_change_callbacks = [callback]

        theme.remove_theme_callback(callback)

        assert callback not in theme._on_change_callbacks

    def test_remove_nonexistent_callback_no_error(self):
        """Should not error when removing non-existent callback."""
        from gui import theme

        theme._on_change_callbacks = []
        callback = MagicMock()

        # Should not raise
        theme.remove_theme_callback(callback)


class TestGetModeDisplayName:
    """Tests for get_mode_display_name function."""

    def test_dark_mode_display_name(self):
        """Should return dark mode display name with emoji."""
        from gui.theme import get_mode_display_name

        assert get_mode_display_name("dark") == "🌙 Dark"

    def test_light_mode_display_name(self):
        """Should return light mode display name with emoji."""
        from gui.theme import get_mode_display_name

        assert get_mode_display_name("light") == "☀️ Light"

    def test_system_mode_display_name(self):
        """Should return system mode display name with emoji."""
        from gui.theme import get_mode_display_name

        assert get_mode_display_name("system") == "💻 System"

    def test_unknown_mode_returns_mode(self):
        """Should return the mode itself for unknown modes."""
        from gui.theme import get_mode_display_name

        assert get_mode_display_name("unknown") == "unknown"


class TestGetAvailableModes:
    """Tests for get_available_modes function."""

    def test_returns_all_modes(self):
        """Should return all available modes."""
        from gui.theme import get_available_modes

        modes = get_available_modes()

        assert "dark" in modes
        assert "light" in modes
        assert "system" in modes
        assert len(modes) == 3

    def test_returns_list(self):
        """Should return a list."""
        from gui.theme import get_available_modes

        assert isinstance(get_available_modes(), list)


class TestInitTheme:
    """Tests for init_theme function."""

    @patch("gui.theme.ctk")
    def test_init_with_default_dark(self, mock_ctk):
        """Should initialize with dark mode by default."""
        from gui import theme

        theme._on_change_callbacks = []
        theme.init_theme()

        assert theme._current_mode == "dark"
        mock_ctk.set_appearance_mode.assert_called_with("dark")

    @patch("gui.theme.ctk")
    def test_init_with_custom_mode(self, mock_ctk):
        """Should initialize with specified mode."""
        from gui import theme

        theme._on_change_callbacks = []
        theme.init_theme("light")

        assert theme._current_mode == "light"
        mock_ctk.set_appearance_mode.assert_called_with("light")
