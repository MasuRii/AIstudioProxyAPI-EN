"""
GUI Launcher Configuration

Contains all constants, paths, colors, and default settings.
"""

from pathlib import Path

# =============================================================================
# Paths
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
GUI_DIR = Path(__file__).parent.absolute()
AUTH_PROFILES_DIR = PROJECT_ROOT / "auth_profiles"
SAVED_AUTH_DIR = AUTH_PROFILES_DIR / "saved"
ACTIVE_AUTH_DIR = AUTH_PROFILES_DIR / "active"
LAUNCH_SCRIPT = PROJECT_ROOT / "launch_camoufox.py"
CONFIG_FILE = GUI_DIR / "user_config.json"
LOG_FILE = PROJECT_ROOT / "logs" / "gui_launcher.log"
CUSTOM_THEME_FILE = GUI_DIR / "theme.json"

# =============================================================================
# Version
# =============================================================================
VERSION = "2.0.0"  # Major version bump for CustomTkinter migration

# =============================================================================
# Default Configuration
# =============================================================================
DEFAULT_CONFIG = {
    "fastapi_port": 2048,
    "camoufox_port": 9222,
    "stream_port": 3120,
    "proxy_address": "",
    "proxy_enabled": False,
    "last_account": "",
    "appearance_mode": "dark",  # "dark", "light", or "system"
    "minimize_to_tray": True,
    "language": "en",
}

# =============================================================================
# CustomTkinter Theme Settings
# =============================================================================
CTK_APPEARANCE_MODE = "dark"  # "dark", "light", or "system"
CTK_COLOR_THEME = "dark-blue"  # Built-in: "blue", "dark-blue", "green"

# =============================================================================
# Modern Color Palette (for custom widgets and fallbacks)
# CustomTkinter uses tuple format: (light_mode_color, dark_mode_color)
# =============================================================================
COLORS = {
    # Background hierarchy - (light, dark)
    "bg_dark": ("#e8e8e8", "#1a1a2e"),
    "bg_medium": ("#f0f0f0", "#16213e"),
    "bg_light": ("#ffffff", "#0f3460"),
    # Accent colors - same for both modes for brand consistency
    "accent": ("#e94560", "#e94560"),
    "accent_hover": ("#d63850", "#ff6b6b"),
    "accent_light": ("#ff8a8a", "#ff8a8a"),
    # Semantic colors - slightly adjusted for visibility in light mode
    "success": ("#00b359", "#00d26a"),
    "success_hover": ("#00994d", "#00ff7f"),
    "warning": ("#e6ad00", "#ffc107"),
    "warning_hover": ("#cc9900", "#ffda44"),
    "error": ("#c82333", "#dc3545"),
    "error_hover": ("#a71d2a", "#ff4d5e"),
    # Text colors - (light, dark)
    "text_primary": ("#1a1a1a", "#ffffff"),
    "text_secondary": ("#555555", "#a0a0a0"),
    "text_muted": ("#888888", "#6c757d"),
    # Text for colored buttons (always white for contrast)
    "text_on_color": "#ffffff",
    # Border and dividers - (light, dark)
    "border": ("#cccccc", "#2d2d44"),
    "border_light": ("#dddddd", "#3d3d5c"),
    # Special
    "transparent": "transparent",
}

# =============================================================================
# Font Configuration
# =============================================================================
FONTS = {
    "family": "Segoe UI",  # Falls back to system font if not available
    "family_mono": "Consolas",
    "size_small": 11,
    "size_normal": 13,
    "size_large": 15,
    "size_header": 20,
    "size_title": 24,
}

# =============================================================================
# Widget Dimensions
# =============================================================================
DIMENSIONS = {
    "corner_radius": 10,
    "corner_radius_small": 6,
    "corner_radius_large": 15,
    "border_width": 2,
    "button_height": 40,
    "button_height_large": 50,
    "entry_height": 38,
    "padding": 15,
    "padding_small": 8,
}

# =============================================================================
# URLs
# =============================================================================
GITHUB_URL = "https://github.com/MasuRii/AIstudioProxyAPI-EN"
DOCS_URL = f"{GITHUB_URL}#readme"
