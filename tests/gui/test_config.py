"""Tests for gui/config.py module."""

import pytest
import re
from pathlib import Path


class TestConfigPaths:
    """Tests for path configurations."""

    def test_project_root_exists(self):
        """PROJECT_ROOT should point to valid directory."""
        from gui.config import PROJECT_ROOT

        assert PROJECT_ROOT.exists()
        assert PROJECT_ROOT.is_dir()

    def test_gui_dir_exists(self):
        """GUI_DIR should point to the gui module directory."""
        from gui.config import GUI_DIR

        assert GUI_DIR.exists()
        assert GUI_DIR.is_dir()
        assert GUI_DIR.name == "gui"

    def test_auth_profiles_dir_structure(self):
        """AUTH_PROFILES_DIR should be under PROJECT_ROOT."""
        from gui.config import PROJECT_ROOT, AUTH_PROFILES_DIR

        assert AUTH_PROFILES_DIR == PROJECT_ROOT / "auth_profiles"

    def test_saved_auth_dir_structure(self):
        """SAVED_AUTH_DIR should be under AUTH_PROFILES_DIR."""
        from gui.config import AUTH_PROFILES_DIR, SAVED_AUTH_DIR

        assert SAVED_AUTH_DIR == AUTH_PROFILES_DIR / "saved"

    def test_active_auth_dir_structure(self):
        """ACTIVE_AUTH_DIR should be under AUTH_PROFILES_DIR."""
        from gui.config import AUTH_PROFILES_DIR, ACTIVE_AUTH_DIR

        assert ACTIVE_AUTH_DIR == AUTH_PROFILES_DIR / "active"

    def test_launch_script_path(self):
        """LAUNCH_SCRIPT should point to launch_camoufox.py."""
        from gui.config import PROJECT_ROOT, LAUNCH_SCRIPT

        assert LAUNCH_SCRIPT == PROJECT_ROOT / "launch_camoufox.py"
        assert LAUNCH_SCRIPT.exists()

    def test_config_file_path(self):
        """CONFIG_FILE should be in GUI_DIR."""
        from gui.config import GUI_DIR, CONFIG_FILE

        assert CONFIG_FILE == GUI_DIR / "user_config.json"

    def test_log_file_path(self):
        """LOG_FILE should be in PROJECT_ROOT/logs."""
        from gui.config import PROJECT_ROOT, LOG_FILE

        assert LOG_FILE == PROJECT_ROOT / "logs" / "gui_launcher.log"


class TestConfigVersion:
    """Tests for version string."""

    def test_version_format(self):
        """VERSION should be a valid semver string."""
        from gui.config import VERSION

        assert isinstance(VERSION, str)
        parts = VERSION.split(".")
        assert len(parts) >= 2
        assert all(p.isdigit() for p in parts[:2])


class TestDefaultConfig:
    """Tests for DEFAULT_CONFIG dictionary."""

    def test_default_config_has_required_keys(self):
        """DEFAULT_CONFIG should have all required keys."""
        from gui.config import DEFAULT_CONFIG

        required_keys = [
            "fastapi_port",
            "camoufox_port",
            "stream_port",
            "proxy_address",
            "proxy_enabled",
            "last_account",
            "appearance_mode",
            "minimize_to_tray",
            "language",
        ]

        for key in required_keys:
            assert key in DEFAULT_CONFIG, f"Missing key: {key}"

    def test_default_ports_are_valid(self):
        """Default ports should be in valid range."""
        from gui.config import DEFAULT_CONFIG

        assert 1 <= DEFAULT_CONFIG["fastapi_port"] <= 65535
        assert 1 <= DEFAULT_CONFIG["camoufox_port"] <= 65535
        assert 1 <= DEFAULT_CONFIG["stream_port"] <= 65535

    def test_default_ports_are_different(self):
        """Default ports should not conflict."""
        from gui.config import DEFAULT_CONFIG

        ports = [
            DEFAULT_CONFIG["fastapi_port"],
            DEFAULT_CONFIG["camoufox_port"],
            DEFAULT_CONFIG["stream_port"],
        ]
        assert len(set(ports)) == 3, "Ports should be unique"

    def test_default_language_is_valid(self):
        """Default language should be 'en' or 'zh'."""
        from gui.config import DEFAULT_CONFIG

        assert DEFAULT_CONFIG["language"] in ("en", "zh")

    def test_default_booleans(self):
        """Boolean defaults should be booleans."""
        from gui.config import DEFAULT_CONFIG

        assert isinstance(DEFAULT_CONFIG["proxy_enabled"], bool)
        assert isinstance(DEFAULT_CONFIG["minimize_to_tray"], bool)
        # appearance_mode is a string, not a bool
        assert isinstance(DEFAULT_CONFIG["appearance_mode"], str)
        assert DEFAULT_CONFIG["appearance_mode"] in ("dark", "light", "system")


class TestCustomTkinterSettings:
    """Tests for CustomTkinter theme settings."""

    def test_ctk_appearance_mode(self):
        """CTK_APPEARANCE_MODE should be valid."""
        from gui.config import CTK_APPEARANCE_MODE

        assert CTK_APPEARANCE_MODE in ("dark", "light", "system")

    def test_ctk_color_theme(self):
        """CTK_COLOR_THEME should be valid."""
        from gui.config import CTK_COLOR_THEME

        valid_themes = ("blue", "dark-blue", "green")
        assert CTK_COLOR_THEME in valid_themes


class TestColors:
    """Tests for COLORS dictionary."""

    def test_colors_has_required_keys(self):
        """COLORS should have all required color keys."""
        from gui.config import COLORS

        required_keys = [
            "bg_dark",
            "bg_medium",
            "bg_light",
            "accent",
            "accent_hover",
            "success",
            "warning",
            "error",
            "text_primary",
            "text_secondary",
            "border",
        ]

        for key in required_keys:
            assert key in COLORS, f"Missing color: {key}"

    def test_colors_are_valid_hex_or_special(self):
        """Colors should be valid hex codes, tuples of hex codes, or special values."""
        from gui.config import COLORS

        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        special_values = {"transparent"}

        def is_valid_color(color):
            """Check if a single color value is valid."""
            return hex_pattern.match(color) or color in special_values

        for name, color in COLORS.items():
            if isinstance(color, tuple):
                # CustomTkinter tuple format: (light_color, dark_color)
                assert len(color) == 2, f"Color tuple {name} should have 2 values"
                for c in color:
                    assert is_valid_color(c), f"Invalid color in tuple for {name}: {c}"
            else:
                # Single color value
                assert is_valid_color(color), f"Invalid color for {name}: {color}"

    def test_has_semantic_colors(self):
        """Should have semantic color variants."""
        from gui.config import COLORS

        # Success colors
        assert "success" in COLORS
        assert "success_hover" in COLORS

        # Error colors
        assert "error" in COLORS
        assert "error_hover" in COLORS


class TestFonts:
    """Tests for FONTS configuration."""

    def test_fonts_has_required_keys(self):
        """FONTS should have all required keys."""
        from gui.config import FONTS

        required_keys = [
            "family",
            "family_mono",
            "size_small",
            "size_normal",
            "size_large",
            "size_header",
        ]

        for key in required_keys:
            assert key in FONTS, f"Missing font key: {key}"

    def test_font_sizes_are_positive(self):
        """Font sizes should be positive integers."""
        from gui.config import FONTS

        size_keys = [k for k in FONTS if k.startswith("size_")]
        for key in size_keys:
            assert isinstance(FONTS[key], int)
            assert FONTS[key] > 0


class TestDimensions:
    """Tests for DIMENSIONS configuration."""

    def test_dimensions_has_corner_radius(self):
        """DIMENSIONS should have corner radius values."""
        from gui.config import DIMENSIONS

        assert "corner_radius" in DIMENSIONS
        assert "corner_radius_small" in DIMENSIONS

    def test_dimensions_are_positive(self):
        """Dimension values should be positive."""
        from gui.config import DIMENSIONS

        for key, value in DIMENSIONS.items():
            assert isinstance(value, int)
            assert value > 0


class TestUrls:
    """Tests for URL constants."""

    def test_github_url_format(self):
        """GITHUB_URL should be a valid GitHub URL."""
        from gui.config import GITHUB_URL

        assert GITHUB_URL.startswith("https://github.com/")

    def test_docs_url_references_github(self):
        """DOCS_URL should reference the GitHub README."""
        from gui.config import GITHUB_URL, DOCS_URL

        assert DOCS_URL.startswith(GITHUB_URL)
        assert "#readme" in DOCS_URL


class TestColorUtilityFunctions:
    """Tests for color utility functions."""

    def test_get_color_returns_dark_mode_by_default(self):
        """get_color should return dark mode color by default."""
        from gui.config import get_color

        # Test with accent color (same in both modes)
        assert get_color("accent") == "#e94560"

    def test_get_color_returns_light_mode(self):
        """get_color should return light mode color when specified."""
        from gui.config import get_color

        # bg_dark is different in light vs dark mode
        light_color = get_color("bg_dark", "light")
        dark_color = get_color("bg_dark", "dark")

        assert light_color == "#e8e8e8"
        assert dark_color == "#1a1a2e"
        assert light_color != dark_color

    def test_get_color_with_plain_string(self):
        """get_color should handle plain string colors."""
        from gui.config import get_color

        # text_on_color is a plain string, not a tuple
        result = get_color("text_on_color")
        assert result == "#ffffff"

    def test_get_color_with_unknown_key(self):
        """get_color should return default for unknown keys."""
        from gui.config import get_color

        result = get_color("nonexistent_color")
        assert result == "#ffffff"  # default fallback

    def test_get_current_color_function_exists(self):
        """get_current_color function should exist."""
        from gui.config import get_current_color

        # Just verify it can be called (it uses ctk which may not be set up)
        assert callable(get_current_color)
