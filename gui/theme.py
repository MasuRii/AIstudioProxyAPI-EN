"""
GUI Launcher Theme Manager

Handles light/dark mode switching with persistence.
"""

import customtkinter as ctk
from typing import Literal, Callable, List

# Type alias for appearance modes
AppearanceMode = Literal["dark", "light", "system"]

# Module-level state
_current_mode: AppearanceMode = "dark"
_on_change_callbacks: List[Callable[[AppearanceMode], None]] = []


def get_appearance_mode() -> AppearanceMode:
    """Get the current appearance mode."""
    return _current_mode


def set_appearance_mode(mode: AppearanceMode) -> None:
    """
    Set the appearance mode and apply it.

    Args:
        mode: One of "dark", "light", or "system"
    """
    global _current_mode

    if mode not in ("dark", "light", "system"):
        mode = "dark"  # Default fallback

    _current_mode = mode
    ctk.set_appearance_mode(mode)

    # Notify listeners
    for callback in _on_change_callbacks:
        try:
            callback(mode)
        except Exception:
            pass


def toggle_appearance_mode() -> AppearanceMode:
    """
    Toggle between dark and light mode.

    Returns:
        The new appearance mode after toggle
    """
    if _current_mode == "dark":
        set_appearance_mode("light")
    else:
        set_appearance_mode("dark")

    return _current_mode


def is_dark_mode() -> bool:
    """Check if currently in dark mode."""
    if _current_mode == "system":
        # Check actual system setting
        return ctk.get_appearance_mode().lower() == "dark"
    return _current_mode == "dark"


def on_theme_change(callback: Callable[[AppearanceMode], None]) -> None:
    """
    Register a callback to be called when theme changes.

    Args:
        callback: Function that takes the new mode as argument
    """
    if callback not in _on_change_callbacks:
        _on_change_callbacks.append(callback)


def remove_theme_callback(callback: Callable[[AppearanceMode], None]) -> None:
    """Remove a previously registered callback."""
    if callback in _on_change_callbacks:
        _on_change_callbacks.remove(callback)


def get_mode_display_name(mode: AppearanceMode) -> str:
    """
    Get a user-friendly display name for the mode.

    Args:
        mode: The appearance mode

    Returns:
        Display name with emoji
    """
    names = {
        "dark": "🌙 Dark",
        "light": "☀️ Light",
        "system": "💻 System",
    }
    return names.get(mode, mode)


def get_available_modes() -> List[AppearanceMode]:
    """Get list of available appearance modes."""
    return ["dark", "light", "system"]


# Initialize with CustomTkinter's default
def init_theme(mode: AppearanceMode = "dark") -> None:
    """
    Initialize the theme system.

    Should be called once at application startup.

    Args:
        mode: Initial appearance mode
    """
    set_appearance_mode(mode)
