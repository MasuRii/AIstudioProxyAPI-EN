"""
AI Studio Proxy API - GUI Launcher Module

This module provides a modern, user-friendly desktop GUI for managing
the AI Studio Proxy API service.

Features:
- Modern dark theme
- Bilingual support (English/Chinese)
- System tray support (Linux/Windows/macOS)
- Account management
- Port and proxy configuration
- Real-time logs

Usage:
    poetry run python -m gui

Or:
    poetry run python gui/launcher.py
"""

from .launcher import SimpleGUILauncher, main

__all__ = ["SimpleGUILauncher", "main"]
