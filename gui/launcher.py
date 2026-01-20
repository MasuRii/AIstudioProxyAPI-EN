#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Studio Proxy API - Simple GUI Launcher
Easy to use, modern interface launcher.

Features:
- Modern dark theme
- GNOME system tray support
- Account management (add, delete)
- Proxy settings
- Port configuration
- API test button
- Log saving

Usage:
    poetry run python simple_launcher.py
"""

import json
import os
import platform
import signal
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
import webbrowser

# Project directories - GUI is in gui/ subdirectory, so go up one level
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
GUI_DIR = Path(__file__).parent.absolute()
AUTH_PROFILES_DIR = PROJECT_ROOT / "auth_profiles"
SAVED_AUTH_DIR = AUTH_PROFILES_DIR / "saved"
ACTIVE_AUTH_DIR = AUTH_PROFILES_DIR / "active"
LAUNCH_SCRIPT = PROJECT_ROOT / "launch_camoufox.py"
CONFIG_FILE = GUI_DIR / "user_config.json"  # User-specific config (gitignored)
LOG_FILE = PROJECT_ROOT / "logs" / "gui_launcher.log"

# Default settings
DEFAULT_CONFIG = {
    "fastapi_port": 2048,
    "camoufox_port": 9222,
    "stream_port": 3120,
    "proxy_address": "",
    "proxy_enabled": False,
    "last_account": "",
    "dark_mode": True,
    "minimize_to_tray": True,
    "language": "en",  # Default language: en or zh
}

# =============================================================================
# Internationalization (i18n) - English/Chinese Support
# =============================================================================
LANG_TEXTS = {
    # Window title
    "title": {"en": "🚀 AI Studio Proxy API", "zh": "🚀 AI Studio 代理 API"},
    # Status messages
    "status_ready": {"en": "⚪ Ready", "zh": "⚪ 就绪"},
    "status_running": {"en": "🟢 Running", "zh": "🟢 运行中"},
    "status_stopping": {"en": "🟡 Stopping...", "zh": "🟡 停止中..."},
    "status_stopped": {"en": "⚪ Stopped", "zh": "⚪ 已停止"},
    "status_error": {"en": "🔴 Error", "zh": "🔴 错误"},
    # Tabs
    "tab_control": {"en": "🎮 Control", "zh": "🎮 控制"},
    "tab_accounts": {"en": "👤 Accounts", "zh": "👤 账户"},
    "tab_settings": {"en": "⚙️ Settings", "zh": "⚙️ 设置"},
    "tab_logs": {"en": "📋 Logs", "zh": "📋 日志"},
    # Control tab
    "quick_start": {"en": "⚡ Quick Start", "zh": "⚡ 快速启动"},
    "account_label": {"en": "Account:", "zh": "账户:"},
    "mode_label": {"en": "Mode:", "zh": "模式:"},
    "mode_headless": {"en": "Headless", "zh": "无头模式"},
    "mode_visible": {"en": "Visible", "zh": "有头模式"},
    "btn_start": {"en": "▶️ START", "zh": "▶️ 启动"},
    "btn_stop": {"en": "⏹️ STOP", "zh": "⏹️ 停止"},
    "api_info": {"en": "🌐 API Info", "zh": "🌐 API 信息"},
    "btn_test": {"en": "🔍 Test", "zh": "🔍 测试"},
    "btn_open_browser": {"en": "🌐 Open in Browser", "zh": "🌐 在浏览器中打开"},
    "status_card": {"en": "📊 Status", "zh": "📊 状态"},
    "service_stopped": {"en": "Service is stopped", "zh": "服务已停止"},
    "service_started": {"en": "Service started", "zh": "服务已启动"},
    "pid_label": {"en": "PID:", "zh": "进程ID:"},
    # Account tab
    "saved_accounts": {"en": "📋 Saved Accounts", "zh": "📋 已保存账户"},
    "btn_add_account": {"en": "➕ Add New Account", "zh": "➕ 添加新账户"},
    "btn_delete_account": {"en": "🗑️ Delete Selected", "zh": "🗑️ 删除选中"},
    "btn_refresh": {"en": "🔄 Refresh", "zh": "🔄 刷新"},
    "account_details": {"en": "ℹ️ Account Details", "zh": "ℹ️ 账户详情"},
    "select_account_hint": {
        "en": "Select an account to see details",
        "zh": "选择账户查看详情",
    },
    "file_label": {"en": "📁 File:", "zh": "📁 文件:"},
    "last_modified": {"en": "📅 Last modified:", "zh": "📅 最后修改:"},
    "size_label": {"en": "📊 Size:", "zh": "📊 大小:"},
    # Settings tab
    "port_settings": {"en": "🔌 Port Settings", "zh": "🔌 端口设置"},
    "fastapi_port": {"en": "FastAPI Port:", "zh": "FastAPI 端口:"},
    "stream_port": {"en": "Stream Port:", "zh": "流代理端口:"},
    "proxy_settings": {"en": "🌍 Proxy Settings", "zh": "🌍 代理设置"},
    "use_proxy": {"en": "Use Proxy", "zh": "使用代理"},
    "proxy_address": {"en": "Address:", "zh": "地址:"},
    "proxy_example": {
        "en": "Example: http://127.0.0.1:7890",
        "zh": "示例: http://127.0.0.1:7890",
    },
    "language_settings": {"en": "🌐 Language / 语言", "zh": "🌐 Language / 语言"},
    "btn_save_settings": {"en": "💾 Save Settings", "zh": "💾 保存设置"},
    "btn_reset_default": {"en": "🔄 Reset to Default", "zh": "🔄 恢复默认"},
    # Logs tab
    "btn_clear_logs": {"en": "🗑️ Clear", "zh": "🗑️ 清空"},
    "btn_save_logs": {"en": "💾 Save to File", "zh": "💾 保存到文件"},
    "btn_open_log_folder": {"en": "📂 Open Log File", "zh": "📂 打开日志文件"},
    # Dialog messages
    "new_account_title": {"en": "New Account", "zh": "新建账户"},
    "new_account_prompt": {
        "en": "Enter a name for the account\n(e.g.: my_gmail_account):",
        "zh": "请输入账户名称\n(例如: my_gmail_account):",
    },
    "invalid_filename": {
        "en": "Only letters, numbers, - and _ are allowed!",
        "zh": "只允许使用字母、数字、- 和 _！",
    },
    "confirm_delete": {
        "en": "Are you sure you want to delete '{name}'?",
        "zh": "确定要删除 '{name}' 吗？",
    },
    "confirm_title": {"en": "Confirm", "zh": "确认"},
    "warning_title": {"en": "Warning", "zh": "警告"},
    "error_title": {"en": "Error", "zh": "错误"},
    "success_title": {"en": "Success", "zh": "成功"},
    "select_account_warning": {
        "en": "Please select an account to delete",
        "zh": "请选择要删除的账户",
    },
    "select_account_error": {
        "en": "Please select an account!",
        "zh": "请选择一个账户！",
    },
    "service_already_running": {
        "en": "Service is already running!",
        "zh": "服务已在运行中！",
    },
    "api_running": {"en": "API is running! ✅", "zh": "API 运行正常！ ✅"},
    "api_not_responding": {
        "en": "Could not connect to API.\nIs the service running?",
        "zh": "无法连接到 API。\n服务是否在运行？",
    },
    "settings_saved": {"en": "Settings saved!", "zh": "设置已保存！"},
    "reset_confirm": {
        "en": "All settings will be reset to default. Continue?",
        "zh": "所有设置将恢复为默认值。继续吗？",
    },
    "exit_confirm": {
        "en": "Service is running. Stop and exit?",
        "zh": "服务正在运行。停止并退出吗？",
    },
    "logs_saved": {"en": "Logs saved:", "zh": "日志已保存:"},
    "logs_save_error": {"en": "Logs could not be saved:", "zh": "无法保存日志:"},
    "folder_open_error": {"en": "Folder could not be opened:", "zh": "无法打开文件夹:"},
    "account_delete_error": {
        "en": "Account could not be deleted:",
        "zh": "无法删除账户:",
    },
    "start_error": {"en": "Could not start:", "zh": "无法启动:"},
    # Log messages
    "log_ready": {
        "en": "🚀 AI Studio Proxy Simple Launcher ready",
        "zh": "🚀 AI Studio 代理启动器就绪",
    },
    "log_accounts_loaded": {
        "en": "✅ {count} account(s) loaded",
        "zh": "✅ 已加载 {count} 个账户",
    },
    "log_no_accounts": {
        "en": "⚠️ No saved accounts found",
        "zh": "⚠️ 未找到已保存的账户",
    },
    "log_adding_account": {
        "en": "🔐 Adding new account: {name}",
        "zh": "🔐 正在添加新账户: {name}",
    },
    "log_browser_login": {
        "en": "📌 Browser will open, log in to your Google account",
        "zh": "📌 浏览器将打开，请登录您的 Google 账户",
    },
    "log_auto_save": {
        "en": "📌 After logging in, account will be saved automatically",
        "zh": "📌 登录后，账户将自动保存",
    },
    "log_account_deleted": {
        "en": "🗑️ Account deleted: {name}",
        "zh": "🗑️ 账户已删除: {name}",
    },
    "log_testing_api": {"en": "🔍 Testing API: {url}", "zh": "🔍 正在测试 API: {url}"},
    "log_api_running": {"en": "✅ API is running!", "zh": "✅ API 运行正常！"},
    "log_api_status": {
        "en": "⚠️ API responded but status code: {code}",
        "zh": "⚠️ API 响应但状态码: {code}",
    },
    "log_api_error": {
        "en": "❌ Could not connect to API. Service may not be running.",
        "zh": "❌ 无法连接到 API。服务可能未运行。",
    },
    "log_api_test_error": {
        "en": "❌ API test error: {error}",
        "zh": "❌ API 测试错误: {error}",
    },
    "log_settings_saved": {"en": "💾 Settings saved", "zh": "💾 设置已保存"},
    "log_settings_reset": {
        "en": "🔄 Settings reset to default",
        "zh": "🔄 设置已恢复默认",
    },
    "log_checking_ports": {"en": "🔍 Checking ports...", "zh": "🔍 正在检查端口..."},
    "log_port_in_use": {
        "en": "🔍 Port {port} is in use, cleaning...",
        "zh": "🔍 端口 {port} 被占用，正在清理...",
    },
    "log_pid_terminated": {
        "en": "   ✅ PID {pid} terminated",
        "zh": "   ✅ PID {pid} 已终止",
    },
    "log_pid_error": {
        "en": "   ❌ PID {pid}: {error}",
        "zh": "   ❌ PID {pid}: {error}",
    },
    "log_port_still_in_use": {
        "en": "   ❌ Port {port} is still in use!",
        "zh": "   ❌ 端口 {port} 仍被占用！",
    },
    "log_starting": {
        "en": "🚀 Starting: {mode} mode",
        "zh": "🚀 正在启动: {mode} 模式",
    },
    "log_service_started": {
        "en": "✅ Service started (PID: {pid})",
        "zh": "✅ 服务已启动 (PID: {pid})",
    },
    "log_stopping": {"en": "🛑 Stopping...", "zh": "🛑 正在停止..."},
    "log_force_closing": {"en": "⚠️ Force closing...", "zh": "⚠️ 正在强制关闭..."},
    "log_stopped": {"en": "✅ Stopped", "zh": "✅ 已停止"},
    "log_stop_error": {"en": "❌ Stop error: {error}", "zh": "❌ 停止错误: {error}"},
    "log_service_ended": {"en": "✅ Service ended normally", "zh": "✅ 服务正常结束"},
    "log_service_error": {
        "en": "⚠️ Service stopped with error: {code}",
        "zh": "⚠️ 服务异常停止，错误码: {code}",
    },
    "log_minimized": {
        "en": "📌 Minimized to system tray",
        "zh": "📌 已最小化到系统托盘",
    },
    "log_accounts_refreshed": {
        "en": "🔄 Account list refreshed",
        "zh": "🔄 账户列表已刷新",
    },
    "log_language_changed": {
        "en": "🌐 Language changed to English",
        "zh": "🌐 语言已切换为中文",
    },
    "log_config_load_error": {
        "en": "⚠️ Configuration could not be loaded: {error}",
        "zh": "⚠️ 无法加载配置: {error}",
    },
    "log_config_save_error": {
        "en": "⚠️ Configuration could not be saved: {error}",
        "zh": "⚠️ 无法保存配置: {error}",
    },
    "log_logs_saved": {"en": "✅ Logs saved: {name}", "zh": "✅ 日志已保存: {name}"},
    "log_port_pid_error": {
        "en": "⚠️ Could not find port PID: {error}",
        "zh": "⚠️ 无法查找端口 PID: {error}",
    },
    "log_user_cancelled": {"en": "❌ User cancelled", "zh": "❌ 用户取消"},
    "log_port_clean_warning": {
        "en": "Some ports could not be cleaned. Continue?",
        "zh": "部分端口无法清理。是否继续？",
    },
    # API status
    "api_active": {
        "en": "✅ API is active and responding",
        "zh": "✅ API 活跃且响应正常",
    },
    "api_not_active": {"en": "❌ API is not responding", "zh": "❌ API 无响应"},
}

# Current language setting
current_language = "en"


def get_text(key: str, **kwargs) -> str:
    """Get translated text for the given key."""
    try:
        text = LANG_TEXTS[key][current_language]
        if kwargs:
            return text.format(**kwargs)
        return text
    except KeyError:
        # Fallback to English
        try:
            text = LANG_TEXTS[key]["en"]
            if kwargs:
                return text.format(**kwargs)
            return text
        except KeyError:
            return f"<{key}>"


# Modern Color Palette (Dark Theme)
COLORS = {
    "bg_dark": "#1a1a2e",
    "bg_medium": "#16213e",
    "bg_light": "#0f3460",
    "accent": "#e94560",
    "accent_hover": "#ff6b6b",
    "success": "#00d26a",
    "warning": "#ffc107",
    "error": "#dc3545",
    "text_primary": "#ffffff",
    "text_secondary": "#a0a0a0",
    "border": "#2d2d44",
}


class ModernStyle:
    """Modern style manager"""

    @staticmethod
    def apply(root):
        """Apply dark theme styles"""
        style = ttk.Style()

        # Set theme
        style.theme_use("clam")

        # Frame styles
        style.configure("TFrame", background=COLORS["bg_dark"])
        style.configure("Card.TFrame", background=COLORS["bg_medium"])

        # Label styles
        style.configure(
            "TLabel",
            background=COLORS["bg_dark"],
            foreground=COLORS["text_primary"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Header.TLabel",
            background=COLORS["bg_dark"],
            foreground=COLORS["text_primary"],
            font=("Segoe UI", 14, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background=COLORS["bg_dark"],
            foreground=COLORS["success"],
            font=("Segoe UI", 11, "bold"),
        )

        # LabelFrame styles
        style.configure(
            "TLabelframe",
            background=COLORS["bg_medium"],
            foreground=COLORS["text_primary"],
        )
        style.configure(
            "TLabelframe.Label",
            background=COLORS["bg_medium"],
            foreground=COLORS["accent"],
            font=("Segoe UI", 11, "bold"),
        )

        # Button styles
        style.configure(
            "TButton",
            background=COLORS["bg_light"],
            foreground=COLORS["text_primary"],
            font=("Segoe UI", 10),
            padding=(10, 5),
        )
        style.map(
            "TButton",
            background=[
                ("active", COLORS["accent"]),
                ("pressed", COLORS["accent_hover"]),
            ],
        )

        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground=COLORS["text_primary"],
            font=("Segoe UI", 10, "bold"),
        )

        # Entry styles
        style.configure(
            "TEntry",
            fieldbackground=COLORS["bg_light"],
            foreground=COLORS["text_primary"],
            insertcolor=COLORS["text_primary"],
        )

        # Combobox styles
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["bg_light"],
            background=COLORS["bg_light"],
            foreground=COLORS["text_primary"],
            arrowcolor=COLORS["text_primary"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["bg_light"])],
            selectbackground=[("readonly", COLORS["accent"])],
        )

        # Radiobutton styles - larger and more visible
        style.configure(
            "TRadiobutton",
            background=COLORS["bg_medium"],
            foreground=COLORS["text_primary"],
            font=("Segoe UI", 11),
            indicatorsize=20,
        )
        style.map(
            "TRadiobutton",
            indicatorcolor=[
                ("selected", COLORS["accent"]),
                ("!selected", COLORS["bg_light"]),
            ],
            background=[("active", COLORS["bg_light"])],
        )

        # Checkbutton styles - larger and more visible
        style.configure(
            "TCheckbutton",
            background=COLORS["bg_medium"],
            foreground=COLORS["text_primary"],
            font=("Segoe UI", 11),
            indicatorsize=18,
        )
        style.map(
            "TCheckbutton",
            indicatorcolor=[
                ("selected", COLORS["accent"]),
                ("!selected", COLORS["bg_light"]),
            ],
            background=[("active", COLORS["bg_light"])],
        )

        # Notebook styles
        style.configure("TNotebook", background=COLORS["bg_dark"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=COLORS["bg_medium"],
            foreground=COLORS["text_primary"],
            padding=(15, 8),
            font=("Segoe UI", 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["accent"])],
            foreground=[("selected", COLORS["text_primary"])],
        )

        # Root widget background
        root.configure(bg=COLORS["bg_dark"])


class TrayIcon:
    """GNOME system tray support - AppIndicator3 (Wayland) or pystray (X11)"""

    def __init__(self, app):
        self.app = app
        self.indicator = None
        self.supported = False
        self.backend = None  # "appindicator" or "pystray"

    def create_icon(self):
        """Create tray icon - try AppIndicator3 first, then pystray"""

        # 1. Try GNOME AppIndicator3 first (for Wayland)
        if self._try_appindicator():
            return

        # 2. Then try pystray (for X11)
        if self._try_pystray():
            return

        print("⚠️ System tray support not found. Tray disabled.")

    def _try_appindicator(self) -> bool:
        """Try to create tray with AppIndicator3"""
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import Gtk, AppIndicator3, GLib

            # Create menu
            menu = Gtk.Menu()

            # Menu items
            item_show = Gtk.MenuItem(label="📂 Show Window")
            item_show.connect(
                "activate", lambda w: GLib.idle_add(self.app._show_window)
            )
            menu.append(item_show)

            menu.append(Gtk.SeparatorMenuItem())

            item_start = Gtk.MenuItem(label="▶️ Start")
            item_start.connect("activate", lambda w: GLib.idle_add(self.app._start))
            menu.append(item_start)

            item_stop = Gtk.MenuItem(label="⏹️ Stop")
            item_stop.connect("activate", lambda w: GLib.idle_add(self.app._stop))
            menu.append(item_stop)

            menu.append(Gtk.SeparatorMenuItem())

            item_test = Gtk.MenuItem(label="🔍 API Test")
            item_test.connect("activate", lambda w: GLib.idle_add(self.app._api_test))
            menu.append(item_test)

            menu.append(Gtk.SeparatorMenuItem())

            item_quit = Gtk.MenuItem(label="❌ Exit")
            item_quit.connect(
                "activate", lambda w: GLib.idle_add(self.app._close_completely)
            )
            menu.append(item_quit)

            menu.show_all()

            # Create AppIndicator
            self.indicator = AppIndicator3.Indicator.new(
                "aistudio-proxy",
                "network-server",  # Use system icon
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.indicator.set_menu(menu)
            self.indicator.set_title("AI Studio Proxy")

            # Run GTK main loop in separate thread
            def gtk_main():
                try:
                    Gtk.main()
                except:
                    pass

            threading.Thread(target=gtk_main, daemon=True).start()

            self.supported = True
            self.backend = "appindicator"
            print("✅ GNOME AppIndicator3 tray started (Wayland compatible)")
            return True

        except Exception as e:
            print(f"⚠️ AppIndicator3 could not be started: {e}")
            return False

    def _try_pystray(self) -> bool:
        """Try to create tray with pystray"""
        try:
            import pystray
            from PIL import Image, ImageDraw

            # Create a simple icon
            size = 64
            image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.ellipse([4, 4, size - 4, size - 4], fill=COLORS["accent"])
            draw.ellipse([16, 16, size - 16, size - 16], fill=COLORS["bg_dark"])

            # Create menu
            menu = pystray.Menu(
                pystray.MenuItem("📂 Show Window", self._pystray_show),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("▶️ Start", self._pystray_start),
                pystray.MenuItem("⏹️ Stop", self._pystray_stop),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("🔍 API Test", self._pystray_test),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("❌ Exit", self._pystray_quit),
            )

            self.indicator = pystray.Icon(
                "AI Studio Proxy", image, "AI Studio Proxy", menu
            )
            threading.Thread(target=self.indicator.run, daemon=True).start()

            self.supported = True
            self.backend = "pystray"
            print("✅ pystray tray started (X11)")
            return True

        except Exception as e:
            print(f"⚠️ pystray could not be started: {e}")
            return False

    def _pystray_show(self, icon=None, item=None):
        self.app.root.after(0, self.app._show_window)

    def _pystray_start(self, icon=None, item=None):
        self.app.root.after(0, self.app._start)

    def _pystray_stop(self, icon=None, item=None):
        self.app.root.after(0, self.app._stop)

    def _pystray_test(self, icon=None, item=None):
        self.app.root.after(0, self.app._api_test)

    def _pystray_quit(self, icon=None, item=None):
        self.app.root.after(0, self.app._close_completely)

    def update_status(self, running: bool):
        """Update tray icon status"""
        if not self.supported:
            return
        # Status update - can be extended later

    def stop(self):
        """Stop tray icon"""
        try:
            if self.backend == "appindicator":
                import gi

                gi.require_version("Gtk", "3.0")
                from gi.repository import Gtk

                Gtk.main_quit()
            elif self.backend == "pystray" and self.indicator:
                self.indicator.stop()
        except:
            pass


class SimpleGUILauncher:
    """Simple GUI Launcher with bilingual support (English/Chinese)"""

    def __init__(self):
        global current_language

        self.root = tk.Tk()
        self.root.geometry("1050x700")
        self.root.minsize(800, 500)

        # Apply modern style
        ModernStyle.apply(self.root)

        # Load configuration
        self.config = self._load_config()

        # Set language from config
        current_language = self.config.get("language", "en")

        # Set window title
        self.root.title(get_text("title"))

        # Variables
        self.selected_account = tk.StringVar(value=self.config.get("last_account", ""))
        self.run_mode = tk.StringVar(value="headless")
        self.status = tk.StringVar(value=get_text("status_ready"))
        self.fastapi_port = tk.StringVar(
            value=str(self.config.get("fastapi_port", 2048))
        )
        self.stream_port = tk.StringVar(value=str(self.config.get("stream_port", 3120)))
        self.proxy_address = tk.StringVar(value=self.config.get("proxy_address", ""))
        self.proxy_enabled = tk.BooleanVar(
            value=self.config.get("proxy_enabled", False)
        )
        self.language_var = tk.StringVar(value=current_language)

        self.process: Optional[subprocess.Popen] = None
        self.log_thread: Optional[threading.Thread] = None
        self.running = False

        # Store widget references for language updates
        self.translatable_widgets = []

        # Tray icon
        self.tray = TrayIcon(self)

        # Create log directory
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Create interface
        self._create_interface()

        # Load accounts
        self._load_accounts()

        # Start tray icon
        if self.config.get("minimize_to_tray", True):
            self.tray.create_icon()

        # Close handler
        self.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration"""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception as e:
            print(f"⚠️ Configuration could not be loaded: {e}")
        return DEFAULT_CONFIG.copy()

    def _save_config(self):
        """Save configuration"""
        try:
            config = {
                "fastapi_port": int(self.fastapi_port.get() or 2048),
                "stream_port": int(self.stream_port.get() or 3120),
                "proxy_address": self.proxy_address.get(),
                "proxy_enabled": self.proxy_enabled.get(),
                "last_account": self.selected_account.get(),
                "dark_mode": True,
                "minimize_to_tray": True,
                "language": current_language,
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(f"⚠️ Configuration could not be saved: {e}")

    def _create_interface(self):
        """Create modern interface"""

        # Main container
        main_container = ttk.Frame(self.root, padding="15")
        main_container.pack(fill=tk.BOTH, expand=True)

        # === HEADER ===
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(
            header_frame, text="🚀 AI Studio Proxy API", style="Header.TLabel"
        ).pack(side=tk.LEFT)

        # Status indicator (top right)
        self.status_label = ttk.Label(
            header_frame, textvariable=self.status, style="Status.TLabel"
        )
        self.status_label.pack(side=tk.RIGHT)

        # === NOTEBOOK (Tabs) ===
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Main Control
        self.main_tab = ttk.Frame(notebook, padding="10")
        notebook.add(self.main_tab, text="🎮 Control")
        self._create_main_tab()

        # Tab 2: Account Management
        self.account_tab = ttk.Frame(notebook, padding="10")
        notebook.add(self.account_tab, text="👤 Accounts")
        self._create_account_tab()

        # Tab 3: Settings
        self.settings_tab = ttk.Frame(notebook, padding="10")
        notebook.add(self.settings_tab, text="⚙️ Settings")
        self._create_settings_tab()

        # Tab 4: Logs
        self.log_tab = ttk.Frame(notebook, padding="10")
        notebook.add(self.log_tab, text="📋 Logs")
        self._create_log_tab()

    def _create_main_tab(self):
        """Main control tab"""

        # Account selection (quick access)
        quick_frame = ttk.LabelFrame(self.main_tab, text="⚡ Quick Start", padding="15")
        quick_frame.pack(fill=tk.X, pady=(0, 15))

        row1 = ttk.Frame(quick_frame)
        row1.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(row1, text="Account:").pack(side=tk.LEFT)
        self.account_combo = ttk.Combobox(
            row1, textvariable=self.selected_account, state="readonly", width=30
        )
        self.account_combo.pack(side=tk.LEFT, padx=(10, 20))

        ttk.Label(row1, text="Mode:").pack(side=tk.LEFT)
        ttk.Radiobutton(
            row1, text="Headless", variable=self.run_mode, value="headless"
        ).pack(side=tk.LEFT, padx=(10, 5))
        ttk.Radiobutton(
            row1, text="Visible", variable=self.run_mode, value="debug"
        ).pack(side=tk.LEFT)

        # Large buttons
        btn_frame = ttk.Frame(quick_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.start_btn = tk.Button(
            btn_frame,
            text="▶️ START",
            command=self._start,
            bg=COLORS["success"],
            fg="white",
            font=("Segoe UI", 14, "bold"),
            height=2,
            width=15,
            cursor="hand2",
            activebackground=COLORS["accent"],
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10), expand=True, fill=tk.X)

        self.stop_btn = tk.Button(
            btn_frame,
            text="⏹️ STOP",
            command=self._stop,
            bg=COLORS["error"],
            fg="white",
            font=("Segoe UI", 14, "bold"),
            height=2,
            width=15,
            cursor="hand2",
            state=tk.DISABLED,
            activebackground=COLORS["accent_hover"],
        )
        self.stop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # Info cards
        info_frame = ttk.Frame(self.main_tab)
        info_frame.pack(fill=tk.X, pady=(15, 0))

        # API Info
        api_card = ttk.LabelFrame(info_frame, text="🌐 API Info", padding="10")
        api_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.api_url_label = ttk.Label(
            api_card, text=f"http://127.0.0.1:{self.fastapi_port.get()}"
        )
        self.api_url_label.pack(anchor=tk.W)

        api_btn_frame = ttk.Frame(api_card)
        api_btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(api_btn_frame, text="🔍 Test", command=self._api_test).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(
            api_btn_frame, text="🌐 Open in Browser", command=self._open_in_browser
        ).pack(side=tk.LEFT)

        # Status card
        status_card = ttk.LabelFrame(info_frame, text="📊 Status", padding="10")
        status_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.status_details = ttk.Label(status_card, text="Service is stopped")
        self.status_details.pack(anchor=tk.W)

        self.pid_label = ttk.Label(status_card, text="PID: -")
        self.pid_label.pack(anchor=tk.W)

    def _create_account_tab(self):
        """Account management tab"""

        # Account list
        list_frame = ttk.LabelFrame(
            self.account_tab, text="📋 Saved Accounts", padding="10"
        )
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Listbox
        self.account_listbox = tk.Listbox(
            list_frame,
            bg=COLORS["bg_light"],
            fg=COLORS["text_primary"],
            selectbackground=COLORS["accent"],
            font=("Consolas", 11),
            height=10,
        )
        self.account_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Account buttons
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(
            btn_frame, text="➕ Add New Account", command=self._add_new_account
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            btn_frame, text="🗑️ Delete Selected", command=self._delete_account
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="🔄 Refresh", command=self._load_accounts).pack(
            side=tk.LEFT
        )

        # Account details
        detail_frame = ttk.LabelFrame(
            self.account_tab, text="ℹ️ Account Details", padding="10"
        )
        detail_frame.pack(fill=tk.X)

        self.account_detail = ttk.Label(
            detail_frame, text="Select an account to see details"
        )
        self.account_detail.pack(anchor=tk.W)

        # Listbox selection event
        self.account_listbox.bind("<<ListboxSelect>>", self._account_selected)

    def _create_settings_tab(self):
        """Settings tab"""

        # Port settings
        port_frame = ttk.LabelFrame(
            self.settings_tab, text=get_text("port_settings"), padding="10"
        )
        port_frame.pack(fill=tk.X, pady=(0, 10))

        row1 = ttk.Frame(port_frame)
        row1.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(row1, text=get_text("fastapi_port")).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.fastapi_port, width=10).pack(
            side=tk.LEFT, padx=(10, 20)
        )

        ttk.Label(row1, text=get_text("stream_port")).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.stream_port, width=10).pack(
            side=tk.LEFT, padx=(10, 0)
        )

        # Proxy settings
        proxy_frame = ttk.LabelFrame(
            self.settings_tab, text=get_text("proxy_settings"), padding="10"
        )
        proxy_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Checkbutton(
            proxy_frame, text=get_text("use_proxy"), variable=self.proxy_enabled
        ).pack(anchor=tk.W)

        proxy_row = ttk.Frame(proxy_frame)
        proxy_row.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(proxy_row, text=get_text("proxy_address")).pack(side=tk.LEFT)
        ttk.Entry(proxy_row, textvariable=self.proxy_address, width=40).pack(
            side=tk.LEFT, padx=(10, 0)
        )

        ttk.Label(
            proxy_frame,
            text=get_text("proxy_example"),
            foreground=COLORS["text_secondary"],
        ).pack(anchor=tk.W, pady=(5, 0))

        # Language settings
        lang_frame = ttk.LabelFrame(
            self.settings_tab, text=get_text("language_settings"), padding="10"
        )
        lang_frame.pack(fill=tk.X, pady=(0, 10))

        lang_row = ttk.Frame(lang_frame)
        lang_row.pack(fill=tk.X)

        ttk.Radiobutton(
            lang_row,
            text="English",
            variable=self.language_var,
            value="en",
            command=self._change_language,
        ).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(
            lang_row,
            text="中文 (Chinese)",
            variable=self.language_var,
            value="zh",
            command=self._change_language,
        ).pack(side=tk.LEFT)

        # Save button
        save_frame = ttk.Frame(self.settings_tab)
        save_frame.pack(fill=tk.X, pady=(20, 0))

        ttk.Button(
            save_frame,
            text=get_text("btn_save_settings"),
            command=self._save_and_notify,
        ).pack(side=tk.LEFT)
        ttk.Button(
            save_frame, text=get_text("btn_reset_default"), command=self._reset_config
        ).pack(side=tk.LEFT, padx=(10, 0))

    def _change_language(self):
        """Change the UI language"""
        global current_language
        new_lang = self.language_var.get()
        if new_lang != current_language:
            current_language = new_lang
            self._save_config()
            self._log(get_text("log_language_changed"))
            # Update window title
            self.root.title(get_text("title"))
            # Notify user to restart for full effect
            messagebox.showinfo(
                get_text("success_title"),
                "Language changed. Some changes will take effect after restart.\n"
                "语言已更改。部分更改将在重启后生效。",
            )

    def _create_log_tab(self):
        """Log tab"""

        # Log area
        self.log_area = scrolledtext.ScrolledText(
            self.log_tab,
            height=20,
            state=tk.DISABLED,
            font=("Consolas", 9),
            bg=COLORS["bg_light"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"],
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Log buttons
        btn_frame = ttk.Frame(self.log_tab)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="🗑️ Clear", command=self._clear_logs).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(btn_frame, text="💾 Save to File", command=self._save_logs).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(
            btn_frame, text="📂 Open Log File", command=self._open_log_file
        ).pack(side=tk.LEFT)

    def _log(self, message: str, save_to_file: bool = True):
        """Add message to log area"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"

        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, f"{formatted}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)

        if save_to_file:
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{formatted}\n")
            except:
                pass

    def _clear_logs(self):
        """Clear log area"""
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state=tk.DISABLED)

    def _save_logs(self):
        """Save logs to file"""
        try:
            log_content = self.log_area.get(1.0, tk.END)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = PROJECT_ROOT / "logs" / f"session_{timestamp}.log"
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(log_content)

            self._log(f"✅ Logs saved: {save_path.name}")
            messagebox.showinfo("Success", f"Logs saved:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Logs could not be saved:\n{e}")

    def _open_log_file(self):
        """Open log file"""
        try:
            if platform.system() == "Linux":
                subprocess.Popen(["xdg-open", str(LOG_FILE.parent)])
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(LOG_FILE.parent)])
            else:
                os.startfile(str(LOG_FILE.parent))
        except Exception as e:
            messagebox.showerror("Error", f"Folder could not be opened:\n{e}")

    def _load_accounts(self):
        """Load saved accounts"""
        accounts = []

        if SAVED_AUTH_DIR.exists():
            for file in sorted(SAVED_AUTH_DIR.glob("*.json")):
                if file.name != ".gitkeep":
                    accounts.append(file.stem)

        # Update combobox
        self.account_combo["values"] = accounts

        # Update listbox
        self.account_listbox.delete(0, tk.END)
        for acc in accounts:
            self.account_listbox.insert(tk.END, f"  📧 {acc}")

        # Select last account
        last = self.config.get("last_account", "")
        if last and last in accounts:
            self.selected_account.set(last)
            try:
                idx = accounts.index(last)
                self.account_listbox.selection_set(idx)
            except:
                pass
        elif accounts:
            self.selected_account.set(accounts[0])

        if accounts:
            self._log(f"✅ {len(accounts)} account(s) loaded")
        else:
            self._log("⚠️ No saved accounts found")

    def _account_selected(self, event):
        """Show details when account is selected"""
        selection = self.account_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        account_name = self.account_listbox.get(idx).replace("  📧 ", "")

        # Read file info
        auth_file = SAVED_AUTH_DIR / f"{account_name}.json"
        if auth_file.exists():
            stat = auth_file.stat()
            mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            size_kb = stat.st_size / 1024

            self.account_detail.config(
                text=f"📁 File: {account_name}.json\n"
                f"📅 Last modified: {mod_time}\n"
                f"📊 Size: {size_kb:.1f} KB"
            )

        # Update combobox as well
        self.selected_account.set(account_name)

    def _add_new_account(self):
        """Add new account"""
        file_name = simpledialog.askstring(
            "New Account",
            "Enter a name for the account\n(e.g.: my_gmail_account):",
            parent=self.root,
        )

        if not file_name:
            return

        if not file_name.replace("_", "").replace("-", "").isalnum():
            messagebox.showerror("Error", "Only letters, numbers, - and _ are allowed!")
            return

        self._log(f"🔐 Adding new account: {file_name}")
        self._log("📌 Browser will open, log in to your Google account")
        self._log("📌 After logging in, account will be saved automatically")

        self._start_internal(mode="debug", save_auth_as=file_name, exit_on_save=True)

    def _delete_account(self):
        """Delete selected account"""
        selection = self.account_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an account to delete")
            return

        idx = selection[0]
        account_name = self.account_listbox.get(idx).replace("  📧 ", "")

        if not messagebox.askyesno(
            "Confirm", f"Are you sure you want to delete '{account_name}'?"
        ):
            return

        try:
            auth_file = SAVED_AUTH_DIR / f"{account_name}.json"
            if auth_file.exists():
                auth_file.unlink()

            # Also delete from active
            active_file = ACTIVE_AUTH_DIR / f"{account_name}.json"
            if active_file.exists():
                active_file.unlink()

            self._log(f"🗑️ Account deleted: {account_name}")
            self._load_accounts()

        except Exception as e:
            messagebox.showerror("Error", f"Account could not be deleted:\n{e}")

    def _api_test(self):
        """Test the API"""
        port = self.fastapi_port.get()
        url = f"http://127.0.0.1:{port}/health"

        self._log(f"🔍 Testing API: {url}")

        try:
            import urllib.request

            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    self._log("✅ API is running!")
                    self.status_details.config(text="✅ API is active and responding")
                    messagebox.showinfo("Success", "API is running! ✅")
                else:
                    self._log(f"⚠️ API responded but status code: {response.status}")
        except urllib.error.URLError:
            self._log("❌ Could not connect to API. Service may not be running.")
            self.status_details.config(text="❌ API is not responding")
            messagebox.showwarning(
                "Warning", "Could not connect to API.\nIs the service running?"
            )
        except Exception as e:
            self._log(f"❌ API test error: {e}")

    def _open_in_browser(self):
        """Open API in browser"""
        port = self.fastapi_port.get()
        webbrowser.open(f"http://127.0.0.1:{port}")

    def _save_and_notify(self):
        """Save settings and notify"""
        self._save_config()
        self._log("💾 Settings saved")
        messagebox.showinfo("Success", "Settings saved!")

        # Update API URL
        self.api_url_label.config(text=f"http://127.0.0.1:{self.fastapi_port.get()}")

    def _reset_config(self):
        """Reset to default settings"""
        if messagebox.askyesno(
            "Confirm", "All settings will be reset to default. Continue?"
        ):
            self.fastapi_port.set(str(DEFAULT_CONFIG["fastapi_port"]))
            self.stream_port.set(str(DEFAULT_CONFIG["stream_port"]))
            self.proxy_address.set("")
            self.proxy_enabled.set(False)
            self._save_config()
            self._log("🔄 Settings reset to default")

    def _is_port_in_use(self, port: int) -> bool:
        """Check if port is in use"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return False
            except OSError:
                return True

    def _find_port_pids(self, port: int) -> List[int]:
        """Find PIDs using the port"""
        pids = []
        try:
            if platform.system() == "Linux":
                result = subprocess.run(
                    ["lsof", "-t", "-i", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.stdout.strip():
                    pids = [int(p) for p in result.stdout.strip().split("\n") if p]
            elif platform.system() == "Windows":
                result = subprocess.run(
                    ["netstat", "-ano", "-p", "TCP"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.split("\n"):
                    if f":{port}" in line and "LISTENING" in line:
                        parts = line.split()
                        if parts:
                            try:
                                pids.append(int(parts[-1]))
                            except ValueError:
                                pass
        except Exception as e:
            self._log(f"⚠️ Could not find port PID: {e}")
        return list(set(pids))

    def _clean_ports(self) -> bool:
        """Clean ports"""
        ports = [
            int(self.fastapi_port.get() or 2048),
            9222,  # Camoufox
            int(self.stream_port.get() or 3120),
        ]
        cleaned = True

        for port in ports:
            if self._is_port_in_use(port):
                self._log(f"🔍 Port {port} is in use, cleaning...")
                pids = self._find_port_pids(port)

                for pid in pids:
                    try:
                        if platform.system() == "Windows":
                            subprocess.run(
                                ["taskkill", "/F", "/PID", str(pid)],
                                capture_output=True,
                                timeout=5,
                            )
                        else:
                            os.kill(pid, signal.SIGTERM)
                            time.sleep(0.5)
                            try:
                                os.kill(pid, 0)
                                os.kill(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        self._log(f"   ✅ PID {pid} terminated")
                    except Exception as e:
                        self._log(f"   ❌ PID {pid}: {e}")
                        cleaned = False

                time.sleep(1)
                if self._is_port_in_use(port):
                    self._log(f"   ❌ Port {port} is still in use!")
                    cleaned = False

        return cleaned

    def _start(self):
        """Start the service"""
        if self.running:
            messagebox.showwarning("Warning", "Service is already running!")
            return

        account = self.selected_account.get()
        if not account:
            messagebox.showerror("Error", "Please select an account!")
            return

        # Save last account
        self.config["last_account"] = account
        self._save_config()

        mode = self.run_mode.get()
        self._start_internal(mode=mode, account=account)

    def _start_internal(
        self,
        mode: str,
        account: str = None,
        save_auth_as: str = None,
        exit_on_save: bool = False,
    ):
        """Internal start function"""

        self._log("🔍 Checking ports...")
        if not self._clean_ports():
            if not messagebox.askyesno(
                "Warning", "Some ports could not be cleaned. Continue?"
            ):
                self._log("❌ User cancelled")
                return

        # Build command
        cmd = [sys.executable, str(LAUNCH_SCRIPT)]

        if mode == "headless":
            cmd.append("--headless")
        elif mode == "debug":
            cmd.append("--debug")

        # Port settings
        cmd.extend(["--server-port", self.fastapi_port.get()])
        cmd.extend(["--stream-port", self.stream_port.get()])

        # Account
        if account:
            auth_file = SAVED_AUTH_DIR / f"{account}.json"
            if auth_file.exists():
                cmd.extend(["--active-auth-json", str(auth_file)])

        # Save
        if save_auth_as:
            cmd.extend(["--save-auth-as", save_auth_as])
            cmd.append("--auto-save-auth")

        if exit_on_save:
            cmd.append("--exit-on-auth-save")

        # Proxy
        if self.proxy_enabled.get() and self.proxy_address.get():
            cmd.extend(["--internal-camoufox-proxy", self.proxy_address.get()])

        self._log(f"🚀 Starting: {mode} mode")

        # Environment variables
        env = os.environ.copy()
        env["DIRECT_LAUNCH"] = "true"

        # When saving auth (new account), skip manual Enter prompt after login
        # Login completion will be detected automatically by URL change
        if save_auth_as:
            env["SUPPRESS_LOGIN_WAIT"] = "true"

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE if save_auth_as else None,
                text=True,
                bufsize=1,
                cwd=str(PROJECT_ROOT),
                env=env,
            )

            self.running = True
            self.status.set("🟢 Running")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_details.config(text="Service started")
            self.pid_label.config(text=f"PID: {self.process.pid}")

            self.tray.update_status(True)

            self.log_thread = threading.Thread(target=self._read_logs, daemon=True)
            self.log_thread.start()

            self._log(f"✅ Service started (PID: {self.process.pid})")

        except Exception as e:
            self._log(f"❌ Start error: {e}")
            messagebox.showerror("Error", f"Could not start:\n{e}")
            self.running = False

    def _read_logs(self):
        """Log reading thread"""
        try:
            while self.process and self.process.poll() is None:
                line = self.process.stdout.readline()
                if line:
                    self.root.after(
                        0, lambda l=line.strip(): self._log(l, save_to_file=False)
                    )

            exit_code = self.process.returncode if self.process else -1
            self.root.after(0, lambda: self._service_ended(exit_code))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"❌ Log error: {e}"))

    def _service_ended(self, exit_code: int):
        """When service ends"""
        self.running = False
        self.process = None

        if exit_code == 0:
            self.status.set("⚪ Stopped")
            self._log("✅ Service ended normally")
        else:
            self.status.set(f"🔴 Error ({exit_code})")
            self._log(f"⚠️ Service stopped with error: {exit_code}")

        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_details.config(text="Service is stopped")
        self.pid_label.config(text="PID: -")

        self.tray.update_status(False)

        # Refresh account list (important after adding new account)
        self._load_accounts()
        self._log("🔄 Account list refreshed")

    def _stop(self):
        """Stop the service"""
        if not self.running or not self.process:
            return

        self._log("🛑 Stopping...")
        self.status.set("🟡 Stopping...")

        try:
            if platform.system() == "Windows":
                self.process.terminate()
            else:
                self.process.send_signal(signal.SIGINT)

            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._log("⚠️ Force closing...")
                self.process.kill()
                self.process.wait(timeout=3)

            self._log("✅ Stopped")
        except Exception as e:
            self._log(f"❌ Stop error: {e}")

        self._service_ended(0)

    def _show_window(self):
        """Show window"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _minimize_to_tray(self):
        """Minimize to tray"""
        if self.tray.supported and self.running:
            self.root.withdraw()
            self._log("📌 Minimized to system tray")
        else:
            self._close_completely()

    def _close_completely(self):
        """Close completely"""
        if self.running:
            if messagebox.askyesno("Confirm", "Service is running. Stop and exit?"):
                self._stop()
            else:
                return

        self._save_config()
        self.tray.stop()
        self.root.destroy()

    def run(self):
        """Run the application"""
        self._log("🚀 AI Studio Proxy Simple Launcher ready")
        self.root.mainloop()


def main():
    """Main function"""
    SAVED_AUTH_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_AUTH_DIR.mkdir(parents=True, exist_ok=True)

    app = SimpleGUILauncher()
    app.run()


if __name__ == "__main__":
    main()
