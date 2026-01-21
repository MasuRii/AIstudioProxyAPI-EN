"""
AI Studio Proxy API - GUI Launcher Module

This module provides a modern, user-friendly desktop GUI for managing
the AI Studio Proxy API service.

Features:
- Modern dark theme with custom styling
- Bilingual support (English/Chinese)
- System tray support (Linux/Windows/macOS)
- Account management (create, import, export)
- Port and proxy configuration
- Real-time log streaming

Architecture:
- app.py      - Main GUILauncher class
- config.py   - Constants, paths, colors, defaults
- i18n.py     - Translations and get_text()
- styles.py   - ModernStyle theme class
- tray.py     - TrayIcon system tray integration
- utils.py    - Tooltip, ScrollableListbox, StatusBar, helpers

Usage:
    poetry run python -m gui

Or:
    from gui import GUILauncher, main
    main()
"""

from .app import GUILauncher, main

__all__ = ["GUILauncher", "main"]
