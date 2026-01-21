"""
GUI Launcher Styles

CustomTkinter theme configuration and custom widget styles.
"""

import customtkinter as ctk
from typing import Optional

from .config import CTK_COLOR_THEME, COLORS, FONTS, DIMENSIONS


def apply_theme(root: Optional[ctk.CTk] = None, appearance_mode: str = "dark") -> None:
    """
    Apply the modern theme using CustomTkinter's built-in theming.

    CustomTkinter handles most styling automatically. This function sets
    the appearance mode and color theme globally.

    Args:
        root: Optional CTk root window (for any additional configuration)
        appearance_mode: "dark", "light", or "system"
    """
    # Import here to avoid circular imports
    from .theme import set_appearance_mode

    # Set appearance mode via theme module
    set_appearance_mode(appearance_mode)

    # Set color theme
    ctk.set_default_color_theme(CTK_COLOR_THEME)


def get_button_colors(style: str = "default") -> dict:
    """
    Get color configuration for CTkButton based on style.

    Args:
        style: One of "default", "success", "danger", "accent", "outline"

    Returns:
        Dictionary of color parameters for CTkButton
    """
    styles = {
        "default": {
            "fg_color": COLORS["bg_light"],
            "hover_color": COLORS["border_light"],
            "text_color": COLORS["text_primary"],
        },
        "success": {
            "fg_color": COLORS["success"],
            "hover_color": COLORS["success_hover"],
            "text_color": COLORS["text_on_color"],  # Always white for contrast
        },
        "danger": {
            "fg_color": COLORS["error"],
            "hover_color": COLORS["error_hover"],
            "text_color": COLORS["text_on_color"],  # Always white for contrast
        },
        "accent": {
            "fg_color": COLORS["accent"],
            "hover_color": COLORS["accent_hover"],
            "text_color": COLORS["text_on_color"],  # Always white for contrast
        },
        "outline": {
            "fg_color": "transparent",
            "hover_color": COLORS["bg_light"],
            "text_color": COLORS["text_primary"],
            "border_width": DIMENSIONS["border_width"],
            "border_color": COLORS["accent"],
        },
        "ghost": {
            "fg_color": "transparent",
            "hover_color": COLORS["bg_medium"],
            "text_color": COLORS["text_secondary"],
        },
    }
    return styles.get(style, styles["default"])


def get_entry_style() -> dict:
    """Get standard entry field styling."""
    return {
        "corner_radius": DIMENSIONS["corner_radius_small"],
        "border_width": DIMENSIONS["border_width"],
        "border_color": COLORS["border"],
        "fg_color": COLORS["bg_light"],
        "text_color": COLORS["text_primary"],
        "placeholder_text_color": COLORS["text_muted"],
    }


def get_frame_style(variant: str = "default") -> dict:
    """
    Get frame styling parameters.

    Args:
        variant: One of "default", "card", "transparent"
    """
    variants = {
        "default": {
            "fg_color": COLORS["bg_dark"],
            "corner_radius": 0,
        },
        "card": {
            "fg_color": COLORS["bg_medium"],
            "corner_radius": DIMENSIONS["corner_radius"],
            "border_width": 1,
            "border_color": COLORS["border"],
        },
        "transparent": {
            "fg_color": "transparent",
            "corner_radius": 0,
        },
    }
    return variants.get(variant, variants["default"])


# Legacy compatibility - ModernStyle class that just calls apply_theme
class ModernStyle:
    """Legacy compatibility wrapper for apply_theme()."""

    @staticmethod
    def apply(root) -> None:
        """Apply theme - for backwards compatibility."""
        apply_theme(root)
