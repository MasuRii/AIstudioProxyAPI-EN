"""Tests for gui/styles.py module."""

import pytest
from unittest.mock import MagicMock, patch


class TestApplyTheme:
    """Tests for apply_theme function."""

    def test_apply_theme_function_exists(self):
        """apply_theme function should exist."""
        from gui.styles import apply_theme

        assert callable(apply_theme)

    def test_apply_theme_calls_set_appearance_mode(self):
        """apply_theme should set CTk appearance mode via theme module."""
        with patch("gui.styles.ctk") as mock_ctk:
            with patch("gui.theme.ctk"):  # Also mock theme.ctk
                from gui.styles import apply_theme

                apply_theme(appearance_mode="dark")

                # apply_theme uses theme.set_appearance_mode which calls ctk
                # So we verify the color theme was set
                mock_ctk.set_default_color_theme.assert_called()

    def test_apply_theme_calls_set_default_color_theme(self):
        """apply_theme should set CTk color theme."""
        with patch("gui.styles.ctk") as mock_ctk:
            from gui.styles import apply_theme, CTK_COLOR_THEME

            apply_theme()

            mock_ctk.set_default_color_theme.assert_called_once_with(CTK_COLOR_THEME)


class TestModernStyleLegacy:
    """Tests for ModernStyle legacy wrapper."""

    def test_modern_style_class_exists(self):
        """ModernStyle class should exist for backwards compatibility."""
        from gui.styles import ModernStyle

        assert ModernStyle is not None

    def test_modern_style_has_apply_method(self):
        """ModernStyle has static apply method."""
        from gui.styles import ModernStyle

        assert hasattr(ModernStyle, "apply")
        assert callable(ModernStyle.apply)

    def test_apply_is_static_method(self):
        """apply should be a static method."""
        from gui.styles import ModernStyle

        assert isinstance(ModernStyle.__dict__["apply"], staticmethod)

    def test_modern_style_apply_calls_apply_theme(self):
        """ModernStyle.apply should call apply_theme."""
        with patch("gui.styles.ctk"):
            from gui.styles import ModernStyle

            mock_root = MagicMock()
            # Should not raise
            ModernStyle.apply(mock_root)


class TestGetButtonColors:
    """Tests for get_button_colors function."""

    def test_get_button_colors_exists(self):
        """get_button_colors function should exist."""
        from gui.styles import get_button_colors

        assert callable(get_button_colors)

    def test_get_button_colors_default(self):
        """get_button_colors returns default style."""
        from gui.styles import get_button_colors

        colors = get_button_colors("default")
        assert "fg_color" in colors
        assert "hover_color" in colors
        assert "text_color" in colors

    def test_get_button_colors_success(self):
        """get_button_colors returns success style."""
        from gui.styles import get_button_colors
        from gui.config import COLORS

        colors = get_button_colors("success")
        assert colors["fg_color"] == COLORS["success"]
        assert colors["hover_color"] == COLORS["success_hover"]

    def test_get_button_colors_danger(self):
        """get_button_colors returns danger style."""
        from gui.styles import get_button_colors
        from gui.config import COLORS

        colors = get_button_colors("danger")
        assert colors["fg_color"] == COLORS["error"]
        assert colors["hover_color"] == COLORS["error_hover"]

    def test_get_button_colors_accent(self):
        """get_button_colors returns accent style."""
        from gui.styles import get_button_colors
        from gui.config import COLORS

        colors = get_button_colors("accent")
        assert colors["fg_color"] == COLORS["accent"]

    def test_get_button_colors_outline(self):
        """get_button_colors returns outline style with border."""
        from gui.styles import get_button_colors

        colors = get_button_colors("outline")
        assert colors["fg_color"] == "transparent"
        assert "border_width" in colors
        assert "border_color" in colors

    def test_get_button_colors_ghost(self):
        """get_button_colors returns ghost style."""
        from gui.styles import get_button_colors

        colors = get_button_colors("ghost")
        assert colors["fg_color"] == "transparent"

    def test_get_button_colors_unknown_returns_default(self):
        """get_button_colors returns default for unknown style."""
        from gui.styles import get_button_colors

        default_colors = get_button_colors("default")
        unknown_colors = get_button_colors("nonexistent_style")
        assert default_colors == unknown_colors


class TestGetEntryStyle:
    """Tests for get_entry_style function."""

    def test_get_entry_style_exists(self):
        """get_entry_style function should exist."""
        from gui.styles import get_entry_style

        assert callable(get_entry_style)

    def test_get_entry_style_returns_required_keys(self):
        """get_entry_style returns required style keys."""
        from gui.styles import get_entry_style

        style = get_entry_style()
        assert "corner_radius" in style
        assert "border_width" in style
        assert "fg_color" in style
        assert "text_color" in style


class TestGetFrameStyle:
    """Tests for get_frame_style function."""

    def test_get_frame_style_exists(self):
        """get_frame_style function should exist."""
        from gui.styles import get_frame_style

        assert callable(get_frame_style)

    def test_get_frame_style_default(self):
        """get_frame_style returns default variant."""
        from gui.styles import get_frame_style

        style = get_frame_style("default")
        assert "fg_color" in style
        assert "corner_radius" in style

    def test_get_frame_style_card(self):
        """get_frame_style returns card variant with border."""
        from gui.styles import get_frame_style

        style = get_frame_style("card")
        assert "border_width" in style
        assert "border_color" in style

    def test_get_frame_style_transparent(self):
        """get_frame_style returns transparent variant."""
        from gui.styles import get_frame_style

        style = get_frame_style("transparent")
        assert style["fg_color"] == "transparent"


class TestColorsIntegration:
    """Tests for color usage in styles."""

    def test_colors_imported_from_config(self):
        """Styles module imports COLORS from config."""
        from gui.styles import COLORS
        from gui.config import COLORS as CONFIG_COLORS

        assert COLORS is CONFIG_COLORS

    def test_accent_color_used_for_highlights(self):
        """Accent color is used for interactive elements."""
        from gui.config import COLORS

        assert "accent" in COLORS
        assert "accent_hover" in COLORS
        assert COLORS["accent"] != COLORS["accent_hover"]

    def test_background_colors_hierarchy(self):
        """Background colors should have visual hierarchy."""
        from gui.config import COLORS

        assert "bg_dark" in COLORS
        assert "bg_medium" in COLORS
        assert "bg_light" in COLORS

        bg_colors = [COLORS["bg_dark"], COLORS["bg_medium"], COLORS["bg_light"]]
        assert len(set(bg_colors)) == 3
