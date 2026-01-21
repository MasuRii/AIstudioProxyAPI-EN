"""
GUI Launcher Main Application

Modern GUI using CustomTkinter for a sleek, contemporary look.
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
import webbrowser
from datetime import datetime
from tkinter import messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from .config import (
    COLORS,
    CONFIG_FILE,
    DEFAULT_CONFIG,
    DIMENSIONS,
    DOCS_URL,
    ENV_EXAMPLE_FILE,
    ENV_FILE,
    FONTS,
    GITHUB_URL,
    LAUNCH_SCRIPT,
    LOG_FILE,
    PROJECT_ROOT,
    SAVED_AUTH_DIR,
    ACTIVE_AUTH_DIR,
    VERSION,
)
from .env_manager import EnvManager, get_env_manager
from .widgets import CTkCollapsibleFrame, CTkEnvSettingsPanel
from .i18n import get_language, get_text, set_language
from .styles import apply_theme, get_button_colors
from .theme import get_appearance_mode, set_appearance_mode, get_available_modes
from .tray import TrayIcon
from .utils import (
    CTkScrollableList,
    CTkStatusBar,
    CTkTooltip,
    copy_to_clipboard,
    validate_port,
)


class GUILauncher:
    """Modern GUI Launcher with CustomTkinter and bilingual support."""

    def __init__(self):
        # Load configuration first
        self.config = self._load_config()

        # Apply theme with saved appearance mode
        appearance_mode = self.config.get("appearance_mode", "dark")
        apply_theme(appearance_mode=appearance_mode)

        # Initialize EnvManager for advanced settings
        self.env_manager = get_env_manager(ENV_FILE, ENV_EXAMPLE_FILE)

        # Create main window
        self.root = ctk.CTk()
        self.root.geometry("1100x800")
        self.root.minsize(900, 650)

        # Set language from config
        set_language(self.config.get("language", "en"))

        # Set window title
        self.root.title(get_text("title"))

        # Initialize variables
        self._init_variables()

        # Process state
        self.process: Optional[subprocess.Popen] = None
        self.log_thread: Optional[threading.Thread] = None
        self.running = False

        # Tray icon
        self.tray = TrayIcon(self)

        # Create log directory
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Build UI
        self._create_main_ui()

        # Load accounts
        self._load_accounts()

        # Bind keyboard shortcuts
        self._bind_shortcuts()

        # Start tray icon
        if self.config.get("minimize_to_tray", True):
            self.tray.create_icon()

        # Close handler
        self.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)

    def _init_variables(self):
        """Initialize tkinter variables."""
        self.selected_account = ctk.StringVar(value=self.config.get("last_account", ""))
        self.run_mode = ctk.StringVar(value="headless")
        self.status = ctk.StringVar(value=get_text("status_ready"))
        self.fastapi_port = ctk.StringVar(
            value=str(self.config.get("fastapi_port", 2048))
        )
        self.stream_port = ctk.StringVar(
            value=str(self.config.get("stream_port", 3120))
        )
        self.proxy_address = ctk.StringVar(value=self.config.get("proxy_address", ""))
        self.proxy_enabled = ctk.BooleanVar(
            value=self.config.get("proxy_enabled", False)
        )
        self.language_var = ctk.StringVar(value=get_language())
        self.appearance_mode_var = ctk.StringVar(
            value=self.config.get("appearance_mode", "dark")
        )
        # Advanced settings state
        self.advanced_settings_expanded = ctk.BooleanVar(
            value=self.config.get("advanced_settings_expanded", False)
        )
        self.advanced_settings_dirty = ctk.BooleanVar(value=False)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception as e:
            print(f"⚠️ Configuration could not be loaded: {e}")
        return DEFAULT_CONFIG.copy()

    def _save_config(self):
        """Save configuration to file."""
        try:
            config = {
                "fastapi_port": int(self.fastapi_port.get() or 2048),
                "stream_port": int(self.stream_port.get() or 3120),
                "proxy_address": self.proxy_address.get(),
                "proxy_enabled": self.proxy_enabled.get(),
                "last_account": self.selected_account.get(),
                "appearance_mode": get_appearance_mode(),
                "minimize_to_tray": True,
                "language": get_language(),
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(get_text("log_config_save_error", error=str(e)))

    def _bind_shortcuts(self):
        """Bind keyboard shortcuts."""
        self.root.bind("<Control-s>", lambda e: self._start())
        self.root.bind("<Control-S>", lambda e: self._start())
        self.root.bind("<Control-x>", lambda e: self._stop())
        self.root.bind("<Control-X>", lambda e: self._stop())
        self.root.bind("<Control-q>", lambda e: self._close_completely())
        self.root.bind("<Control-Q>", lambda e: self._close_completely())
        self.root.bind("<F5>", lambda e: self._load_accounts())

    # =========================================================================
    # Main UI
    # =========================================================================
    def _create_main_ui(self):
        """Create the main user interface."""
        # Configure grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        # Header
        self._create_header()

        # Main content with tabs
        self._create_tabview()

        # Status bar
        self.status_bar = CTkStatusBar(self.root)
        self.status_bar.grid(row=2, column=0, sticky="ew")
        self.status_bar.set_port(int(self.fastapi_port.get()))

    def _create_header(self):
        """Create the header section."""
        header = ctk.CTkFrame(self.root, fg_color="transparent", height=60)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))
        header.grid_columnconfigure(1, weight=1)

        # Title
        title_label = ctk.CTkLabel(
            header,
            text=get_text("title"),
            font=ctk.CTkFont(
                family=FONTS["family"], size=FONTS["size_title"], weight="bold"
            ),
            text_color=COLORS["text_primary"],
        )
        title_label.grid(row=0, column=0, sticky="w")

        # Status badge
        self.status_badge = ctk.CTkLabel(
            header,
            textvariable=self.status,
            font=ctk.CTkFont(
                family=FONTS["family"], size=FONTS["size_normal"], weight="bold"
            ),
            text_color=COLORS["success"],
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius_small"],
            padx=15,
            pady=5,
        )
        self.status_badge.grid(row=0, column=2, sticky="e")

        # Menu buttons
        menu_frame = ctk.CTkFrame(header, fg_color="transparent")
        menu_frame.grid(row=0, column=1, sticky="e", padx=(0, 20))

        ctk.CTkButton(
            menu_frame,
            text="📖 Docs",
            width=80,
            height=32,
            fg_color="transparent",
            hover_color=COLORS["bg_medium"],
            text_color=COLORS["text_primary"],
            command=lambda: webbrowser.open(DOCS_URL),
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            menu_frame,
            text="⚙️ About",
            width=80,
            height=32,
            fg_color="transparent",
            hover_color=COLORS["bg_medium"],
            text_color=COLORS["text_primary"],
            command=self._show_about,
        ).pack(side="left", padx=5)

    def _create_tabview(self):
        """Create the tab view with all tabs."""
        self.tabview = ctk.CTkTabview(
            self.root,
            fg_color=COLORS["bg_dark"],
            segmented_button_fg_color=COLORS["bg_medium"],
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent_hover"],
            segmented_button_unselected_color=COLORS["bg_medium"],
            segmented_button_unselected_hover_color=COLORS["bg_light"],
            text_color=COLORS["text_primary"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))

        # Add tabs
        self.tabview.add(get_text("tab_control"))
        self.tabview.add(get_text("tab_accounts"))
        self.tabview.add(get_text("tab_settings"))
        self.tabview.add(get_text("tab_logs"))

        # Build tab content
        self._create_control_tab()
        self._create_accounts_tab()
        self._create_settings_tab()
        self._create_logs_tab()

    def _create_control_tab(self):
        """Create the Control tab."""
        tab = self.tabview.tab(get_text("tab_control"))
        tab.grid_columnconfigure(0, weight=1)

        # Quick Start Card
        quick_card = ctk.CTkFrame(
            tab,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        quick_card.grid(row=0, column=0, sticky="ew", pady=(10, 15), padx=10)
        quick_card.grid_columnconfigure(1, weight=1)

        # Card header
        ctk.CTkLabel(
            quick_card,
            text=get_text("quick_start"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(15, 10))

        # Account selector
        ctk.CTkLabel(
            quick_card,
            text=get_text("account_label"),
            font=ctk.CTkFont(size=FONTS["size_normal"]),
            text_color=COLORS["text_primary"],
        ).grid(row=1, column=0, sticky="w", padx=(20, 10), pady=10)

        self.account_combo = ctk.CTkComboBox(
            quick_card,
            variable=self.selected_account,
            width=250,
            height=38,
            corner_radius=DIMENSIONS["corner_radius_small"],
            fg_color=COLORS["bg_light"],
            border_color=COLORS["border"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_medium"],
            dropdown_hover_color=COLORS["bg_light"],
            text_color=COLORS["text_primary"],
            dropdown_text_color=COLORS["text_primary"],
        )
        self.account_combo.grid(row=1, column=1, sticky="w", padx=10, pady=10)
        CTkTooltip(self.account_combo, "tooltip_account")

        # Mode selector
        ctk.CTkLabel(
            quick_card,
            text=get_text("mode_label"),
            font=ctk.CTkFont(size=FONTS["size_normal"]),
            text_color=COLORS["text_primary"],
        ).grid(row=1, column=2, sticky="w", padx=(30, 10), pady=10)

        mode_frame = ctk.CTkFrame(quick_card, fg_color="transparent")
        mode_frame.grid(row=1, column=3, sticky="w", padx=(0, 20), pady=10)

        headless_rb = ctk.CTkRadioButton(
            mode_frame,
            text=get_text("mode_headless"),
            variable=self.run_mode,
            value="headless",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
        )
        headless_rb.pack(side="left", padx=(0, 15))
        CTkTooltip(headless_rb, "tooltip_headless")

        visible_rb = ctk.CTkRadioButton(
            mode_frame,
            text=get_text("mode_visible"),
            variable=self.run_mode,
            value="debug",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
        )
        visible_rb.pack(side="left")
        CTkTooltip(visible_rb, "tooltip_visible")

        # Action buttons
        btn_frame = ctk.CTkFrame(quick_card, fg_color="transparent")
        btn_frame.grid(
            row=2, column=0, columnspan=4, sticky="ew", padx=20, pady=(10, 20)
        )
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_btn = ctk.CTkButton(
            btn_frame,
            text=get_text("btn_start"),
            command=self._start,
            height=DIMENSIONS["button_height_large"],
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            fg_color=COLORS["success"],
            hover_color=COLORS["success_hover"],
            text_color=COLORS["text_on_color"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        CTkTooltip(self.start_btn, "tooltip_start")

        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text=get_text("btn_stop"),
            command=self._stop,
            height=DIMENSIONS["button_height_large"],
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            fg_color=COLORS["error"],
            hover_color=COLORS["error_hover"],
            text_color=COLORS["text_on_color"],
            corner_radius=DIMENSIONS["corner_radius"],
            state="disabled",
        )
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        CTkTooltip(self.stop_btn, "tooltip_stop")

        # Info cards row
        info_frame = ctk.CTkFrame(tab, fg_color="transparent")
        info_frame.grid(row=1, column=0, sticky="ew", pady=10, padx=10)
        info_frame.grid_columnconfigure((0, 1), weight=1)

        # API Info card
        self._create_api_info_card(info_frame)

        # Status card
        self._create_status_card(info_frame)

    def _create_api_info_card(self, parent):
        """Create the API info card."""
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(
            card,
            text=get_text("api_info"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=20, pady=(15, 10))

        # URL display
        url_frame = ctk.CTkFrame(card, fg_color=COLORS["bg_light"], corner_radius=8)
        url_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.api_url_label = ctk.CTkLabel(
            url_frame,
            text=f"http://127.0.0.1:{self.fastapi_port.get()}",
            font=ctk.CTkFont(family=FONTS["family_mono"], size=FONTS["size_normal"]),
            text_color=COLORS["text_primary"],
        )
        self.api_url_label.pack(side="left", padx=15, pady=10)

        copy_btn = ctk.CTkButton(
            url_frame,
            text="📋",
            width=40,
            height=32,
            fg_color="transparent",
            hover_color=COLORS["bg_medium"],
            command=self._copy_api_url,
        )
        copy_btn.pack(side="right", padx=10)
        CTkTooltip(copy_btn, "tooltip_copy_url")

        # Action buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkButton(
            btn_frame,
            text=get_text("btn_test"),
            width=100,
            command=self._api_test,
            **get_button_colors("outline"),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text=get_text("btn_open_browser"),
            width=140,
            command=self._open_in_browser,
            **get_button_colors("ghost"),
        ).pack(side="left")

    def _create_status_card(self, parent):
        """Create the status card."""
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(
            card,
            text=get_text("status_card"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=20, pady=(15, 10))

        self.status_details = ctk.CTkLabel(
            card,
            text=get_text("service_stopped"),
            font=ctk.CTkFont(size=FONTS["size_normal"]),
            text_color=COLORS["text_secondary"],
        )
        self.status_details.pack(anchor="w", padx=20, pady=5)

        self.pid_label = ctk.CTkLabel(
            card,
            text=f"{get_text('pid_label')} -",
            font=ctk.CTkFont(size=FONTS["size_normal"]),
            text_color=COLORS["text_muted"],
        )
        self.pid_label.pack(anchor="w", padx=20, pady=(5, 15))

    def _create_accounts_tab(self):
        """Create the Accounts tab."""
        tab = self.tabview.tab(get_text("tab_accounts"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # Main container
        main_frame = ctk.CTkFrame(tab, fg_color="transparent")
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # Account list card
        list_card = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        list_card.grid(row=0, column=0, sticky="nsew")
        list_card.grid_columnconfigure(0, weight=1)
        list_card.grid_rowconfigure(1, weight=1)

        # Card header
        header_frame = ctk.CTkFrame(list_card, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))

        ctk.CTkLabel(
            header_frame,
            text=get_text("saved_accounts"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).pack(side="left")

        # Action buttons in header
        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side="right")

        add_btn = ctk.CTkButton(
            btn_frame,
            text=get_text("btn_add_account"),
            width=150,
            height=36,
            command=self._add_new_account,
            fg_color=COLORS["success"],
            hover_color=COLORS["success_hover"],
            text_color=COLORS["text_on_color"],
        )
        add_btn.pack(side="left", padx=(0, 10))
        CTkTooltip(add_btn, "tooltip_add_account")

        del_btn = ctk.CTkButton(
            btn_frame,
            text=get_text("btn_delete_account"),
            width=130,
            height=36,
            command=self._delete_account,
            fg_color=COLORS["error"],
            hover_color=COLORS["error_hover"],
            text_color=COLORS["text_on_color"],
        )
        del_btn.pack(side="left", padx=(0, 10))
        CTkTooltip(del_btn, "tooltip_delete_account")

        ctk.CTkButton(
            btn_frame,
            text=get_text("btn_refresh"),
            width=100,
            height=36,
            command=self._load_accounts,
            **get_button_colors("outline"),
        ).pack(side="left")

        # Account list
        self.account_list = CTkScrollableList(list_card, height=350)
        self.account_list.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 15))
        self.account_list.bind_select(self._account_selected)
        self.account_list.bind_double_click(self._account_double_click)

        # Account details card
        detail_card = ctk.CTkFrame(
            main_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        detail_card.grid(row=1, column=0, sticky="ew", pady=(15, 0))

        ctk.CTkLabel(
            detail_card,
            text=get_text("account_details"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=20, pady=(15, 10))

        self.account_detail = ctk.CTkLabel(
            detail_card,
            text=get_text("select_account_hint"),
            font=ctk.CTkFont(size=FONTS["size_normal"]),
            text_color=COLORS["text_secondary"],
            justify="left",
        )
        self.account_detail.pack(anchor="w", padx=20, pady=(0, 15))

    def _create_settings_tab(self):
        """Create the Settings tab with basic and advanced settings."""
        tab = self.tabview.tab(get_text("tab_settings"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # Create scrollable container for all settings
        settings_scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=COLORS["bg_dark"],
            scrollbar_fg_color=COLORS["bg_medium"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        settings_scroll.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        settings_scroll.grid_columnconfigure(0, weight=1)

        # Store reference for scroll binding
        self._settings_scroll = settings_scroll

        # Port settings card
        port_card = ctk.CTkFrame(
            settings_scroll,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        port_card.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 10))

        ctk.CTkLabel(
            port_card,
            text=get_text("port_settings"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(15, 10))

        ctk.CTkLabel(
            port_card,
            text=get_text("fastapi_port"),
            text_color=COLORS["text_primary"],
        ).grid(row=1, column=0, sticky="w", padx=(20, 10), pady=10)
        fastapi_entry = ctk.CTkEntry(
            port_card,
            textvariable=self.fastapi_port,
            width=120,
            height=38,
            text_color=COLORS["text_primary"],
        )
        fastapi_entry.grid(row=1, column=1, sticky="w", padx=10, pady=10)
        CTkTooltip(fastapi_entry, "tooltip_fastapi_port")

        ctk.CTkLabel(
            port_card,
            text=get_text("stream_port"),
            text_color=COLORS["text_primary"],
        ).grid(row=1, column=2, sticky="w", padx=(30, 10), pady=10)
        stream_entry = ctk.CTkEntry(
            port_card,
            textvariable=self.stream_port,
            width=120,
            height=38,
            text_color=COLORS["text_primary"],
        )
        stream_entry.grid(row=1, column=3, sticky="w", padx=(10, 20), pady=(10, 15))
        CTkTooltip(stream_entry, "tooltip_stream_port")

        # Proxy settings card
        proxy_card = ctk.CTkFrame(
            settings_scroll,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        proxy_card.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 10))

        ctk.CTkLabel(
            proxy_card,
            text=get_text("proxy_settings"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=20, pady=(15, 10))

        ctk.CTkCheckBox(
            proxy_card,
            text=get_text("use_proxy"),
            variable=self.proxy_enabled,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", padx=20, pady=5)

        proxy_frame = ctk.CTkFrame(proxy_card, fg_color="transparent")
        proxy_frame.pack(fill="x", padx=20, pady=(5, 5))

        ctk.CTkLabel(
            proxy_frame,
            text=get_text("proxy_address"),
            text_color=COLORS["text_primary"],
        ).pack(side="left")
        proxy_entry = ctk.CTkEntry(
            proxy_frame,
            textvariable=self.proxy_address,
            width=300,
            height=38,
            placeholder_text="http://127.0.0.1:7890",
            text_color=COLORS["text_primary"],
        )
        proxy_entry.pack(side="left", padx=(10, 0))
        CTkTooltip(proxy_entry, "tooltip_proxy")

        ctk.CTkLabel(
            proxy_card,
            text=get_text("proxy_example"),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=20, pady=(0, 15))

        # Language settings card
        lang_card = ctk.CTkFrame(
            settings_scroll,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        lang_card.grid(row=2, column=0, sticky="ew", padx=5, pady=(0, 10))

        ctk.CTkLabel(
            lang_card,
            text=get_text("language_settings"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=20, pady=(15, 10))

        lang_frame = ctk.CTkFrame(lang_card, fg_color="transparent")
        lang_frame.pack(anchor="w", padx=20, pady=(0, 15))

        ctk.CTkRadioButton(
            lang_frame,
            text="🇺🇸 English",
            variable=self.language_var,
            value="en",
            command=self._change_language,
            fg_color=COLORS["accent"],
            text_color=COLORS["text_primary"],
        ).pack(side="left", padx=(0, 30))

        ctk.CTkRadioButton(
            lang_frame,
            text="🇨🇳 中文",
            variable=self.language_var,
            value="zh",
            command=self._change_language,
            fg_color=COLORS["accent"],
            text_color=COLORS["text_primary"],
        ).pack(side="left")

        # Theme settings card
        theme_card = ctk.CTkFrame(
            settings_scroll,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        theme_card.grid(row=3, column=0, sticky="ew", padx=5, pady=(0, 10))

        ctk.CTkLabel(
            theme_card,
            text=get_text("theme_settings"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=20, pady=(15, 10))

        theme_frame = ctk.CTkFrame(theme_card, fg_color="transparent")
        theme_frame.pack(anchor="w", padx=20, pady=(0, 15))

        dark_rb = ctk.CTkRadioButton(
            theme_frame,
            text=get_text("theme_dark"),
            variable=self.appearance_mode_var,
            value="dark",
            command=self._change_appearance_mode,
            fg_color=COLORS["accent"],
            text_color=COLORS["text_primary"],
        )
        dark_rb.pack(side="left", padx=(0, 20))
        CTkTooltip(dark_rb, "tooltip_theme")

        light_rb = ctk.CTkRadioButton(
            theme_frame,
            text=get_text("theme_light"),
            variable=self.appearance_mode_var,
            value="light",
            command=self._change_appearance_mode,
            fg_color=COLORS["accent"],
            text_color=COLORS["text_primary"],
        )
        light_rb.pack(side="left", padx=(0, 20))

        system_rb = ctk.CTkRadioButton(
            theme_frame,
            text=get_text("theme_system"),
            variable=self.appearance_mode_var,
            value="system",
            command=self._change_appearance_mode,
            fg_color=COLORS["accent"],
            text_color=COLORS["text_primary"],
        )
        system_rb.pack(side="left")

        # Basic settings save buttons
        save_frame = ctk.CTkFrame(settings_scroll, fg_color="transparent")
        save_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=(5, 15))

        ctk.CTkButton(
            save_frame,
            text=get_text("btn_save_settings"),
            command=self._save_and_notify,
            height=40,
            fg_color=COLORS["success"],
            hover_color=COLORS["success_hover"],
            text_color=COLORS["text_on_color"],
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            save_frame,
            text=get_text("btn_reset_default"),
            command=self._reset_config,
            height=40,
            **get_button_colors("outline"),
        ).pack(side="left")

        # =========================================================================
        # Advanced Settings Section (Collapsible)
        # =========================================================================
        self._create_advanced_settings_section(settings_scroll, row=5)

        # Bind mouse wheel scrolling AFTER all widgets are created
        self._bind_settings_scroll_events(settings_scroll)

    def _create_advanced_settings_section(self, parent, row: int):
        """Create the collapsible advanced settings section."""
        # Advanced settings toggle button
        self.advanced_toggle_btn = ctk.CTkButton(
            parent,
            text=get_text("show_advanced"),
            command=self._toggle_advanced_settings,
            height=40,
            fg_color=COLORS["bg_medium"],
            hover_color=COLORS["bg_light"],
            text_color=COLORS["accent"],
            border_width=1,
            border_color=COLORS["accent"],
        )
        self.advanced_toggle_btn.grid(
            row=row, column=0, sticky="ew", padx=5, pady=(10, 5)
        )

        # Advanced settings container (hidden by default)
        self.advanced_settings_frame = ctk.CTkFrame(
            parent,
            fg_color=COLORS["bg_dark"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        # Don't grid initially - will be shown when toggled
        self.advanced_settings_frame.grid_columnconfigure(0, weight=1)

        # Header with hint text
        header_frame = ctk.CTkFrame(
            self.advanced_settings_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 10))

        ctk.CTkLabel(
            header_frame,
            text=get_text("advanced_settings"),
            font=ctk.CTkFont(size=FONTS["size_large"], weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=20, pady=(15, 5))

        ctk.CTkLabel(
            header_frame,
            text=get_text("advanced_settings_hint"),
            font=ctk.CTkFont(size=FONTS["size_small"]),
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=20, pady=(0, 10))

        # Status indicator for unsaved changes
        self.advanced_status_label = ctk.CTkLabel(
            header_frame,
            text="",
            font=ctk.CTkFont(size=FONTS["size_small"]),
            text_color=COLORS["warning"],
        )
        self.advanced_status_label.pack(anchor="w", padx=20, pady=(0, 15))

        # Action buttons for advanced settings
        adv_btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        adv_btn_frame.pack(fill="x", padx=20, pady=(0, 15))

        self.adv_save_btn = ctk.CTkButton(
            adv_btn_frame,
            text=get_text("btn_apply_env"),
            command=self._save_advanced_settings,
            height=36,
            width=140,
            fg_color=COLORS["success"],
            hover_color=COLORS["success_hover"],
            text_color=COLORS["text_on_color"],
        )
        self.adv_save_btn.pack(side="left", padx=(0, 10))

        self.adv_hot_reload_btn = ctk.CTkButton(
            adv_btn_frame,
            text=get_text("btn_hot_reload"),
            command=self._hot_reload_advanced_settings,
            height=36,
            width=140,
            fg_color=COLORS["warning"],
            hover_color=COLORS["warning_hover"],
            text_color=COLORS["text_on_color"],
        )
        self.adv_hot_reload_btn.pack(side="left", padx=(0, 10))
        CTkTooltip(self.adv_hot_reload_btn, "tooltip_env_hot_reload")

        ctk.CTkButton(
            adv_btn_frame,
            text=get_text("btn_reload_env"),
            command=self._reload_advanced_settings,
            height=36,
            width=140,
            **get_button_colors("outline"),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            adv_btn_frame,
            text=get_text("btn_reset_env"),
            command=self._reset_advanced_settings,
            height=36,
            width=140,
            **get_button_colors("ghost"),
        ).pack(side="left")

        # Environment settings panel with all categories
        self.env_settings_panel = CTkEnvSettingsPanel(
            self.advanced_settings_frame,
            env_manager=self.env_manager,
            on_save=lambda: self._log(get_text("log_env_saved")),
            on_change=self._on_advanced_settings_change,
            height=400,
        )
        self.env_settings_panel.grid(
            row=1, column=0, sticky="nsew", padx=5, pady=(0, 10)
        )

        # Store row for toggling
        self._advanced_settings_row = row + 1
        self._advanced_settings_parent = parent

        # Initialize based on saved state
        if self.advanced_settings_expanded.get():
            self._show_advanced_settings()

    def _toggle_advanced_settings(self):
        """Toggle the advanced settings visibility."""
        if self.advanced_settings_expanded.get():
            self._hide_advanced_settings()
        else:
            self._show_advanced_settings()

    def _show_advanced_settings(self):
        """Show the advanced settings section."""
        self.advanced_settings_expanded.set(True)
        self.advanced_toggle_btn.configure(text=get_text("hide_advanced"))
        self.advanced_settings_frame.grid(
            row=self._advanced_settings_row,
            column=0,
            sticky="nsew",
            padx=0,
            pady=(0, 10),
        )
        # Save expanded state
        self.config["advanced_settings_expanded"] = True
        self._save_config()
        self._log(get_text("log_env_loaded"))

    def _hide_advanced_settings(self):
        """Hide the advanced settings section."""
        # Check for unsaved changes
        if self.env_settings_panel.is_dirty():
            if messagebox.askyesno(
                get_text("confirm_title"),
                get_text("env_unsaved_changes"),
            ):
                self._save_advanced_settings()

        self.advanced_settings_expanded.set(False)
        self.advanced_toggle_btn.configure(text=get_text("show_advanced"))
        self.advanced_settings_frame.grid_forget()
        # Save collapsed state
        self.config["advanced_settings_expanded"] = False
        self._save_config()

    def _on_advanced_settings_change(self, is_dirty: bool):
        """Handle advanced settings dirty state change."""
        self.advanced_settings_dirty.set(is_dirty)
        if is_dirty:
            self.advanced_status_label.configure(
                text=get_text("env_modified_indicator"),
                text_color=COLORS["warning"],
            )
        else:
            self.advanced_status_label.configure(text="")

    def _save_advanced_settings(self):
        """Save advanced settings to .env file."""
        if self.env_settings_panel.save():
            self._log(get_text("log_env_saved"))
            messagebox.showinfo(
                get_text("success_title"),
                get_text("env_saved"),
            )
        else:
            messagebox.showerror(
                get_text("error_title"),
                get_text("env_save_error"),
            )

    def _reload_advanced_settings(self):
        """Reload advanced settings from .env file."""
        self.env_settings_panel.reload()
        self._log(get_text("env_reloaded"))

    def _reset_advanced_settings(self):
        """Reset advanced settings to defaults."""
        if messagebox.askyesno(
            get_text("confirm_title"),
            get_text("env_reset_confirm"),
        ):
            self.env_settings_panel.reset_to_defaults()
            self._log(get_text("log_env_reset"))

    def _hot_reload_advanced_settings(self):
        """Apply settings via hot reload to running proxy."""
        if self.running:
            # Warn user that proxy is running
            if not messagebox.askyesno(
                get_text("warning_title"),
                get_text("env_hot_reload_confirm"),
            ):
                return

        # Save first
        if not self.env_settings_panel.save():
            messagebox.showerror(
                get_text("error_title"),
                get_text("env_save_error"),
            )
            return

        # Apply to environment
        self.env_manager.apply_to_environment()

        # Trigger hot reload callbacks
        modified_count = len(self.env_settings_panel.get_modified_keys())
        self.env_manager.trigger_hot_reload()

        self._log(get_text("log_env_hot_reload", count=modified_count))

        if self.running:
            messagebox.showinfo(
                get_text("success_title"),
                get_text("env_hot_reload_warning"),
            )

    def _create_logs_tab(self):
        """Create the Logs tab."""
        tab = self.tabview.tab(get_text("tab_logs"))
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # Log textbox
        self.log_area = ctk.CTkTextbox(
            tab,
            font=ctk.CTkFont(family=FONTS["family_mono"], size=FONTS["size_small"]),
            fg_color=COLORS["bg_light"],
            text_color=COLORS["text_primary"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            state="disabled",
        )
        self.log_area.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 10))

        # Button row
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text=get_text("btn_clear_logs"),
            command=self._clear_logs,
            width=100,
            **get_button_colors("ghost"),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text=get_text("btn_save_logs"),
            command=self._save_logs,
            width=120,
            **get_button_colors("outline"),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text=get_text("btn_open_log_folder"),
            command=self._open_log_folder,
            width=140,
            **get_button_colors("ghost"),
        ).pack(side="left")

    # =========================================================================
    # Logging
    # =========================================================================
    def _log(self, message: str, save_to_file: bool = True):
        """Add message to log area."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"

        self.log_area.configure(state="normal")
        self.log_area.insert("end", f"{formatted}\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

        if save_to_file:
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{formatted}\n")
            except Exception:
                pass

    def _clear_logs(self):
        """Clear log area."""
        self.log_area.configure(state="normal")
        self.log_area.delete("1.0", "end")
        self.log_area.configure(state="disabled")

    def _save_logs(self):
        """Save logs to file."""
        try:
            log_content = self.log_area.get("1.0", "end")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = PROJECT_ROOT / "logs" / f"session_{timestamp}.log"
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(log_content)

            self._log(get_text("log_logs_saved", name=save_path.name))
            messagebox.showinfo(
                get_text("success_title"), f"{get_text('logs_saved')}\n{save_path}"
            )
        except Exception as e:
            messagebox.showerror(
                get_text("error_title"), f"{get_text('logs_save_error')}\n{e}"
            )

    def _open_log_folder(self):
        """Open log folder in file manager."""
        try:
            log_dir = str(LOG_FILE.parent)
            if platform.system() == "Linux":
                subprocess.Popen(["xdg-open", log_dir])
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", log_dir])
            else:
                os.startfile(log_dir)
        except Exception as e:
            messagebox.showerror(
                get_text("error_title"), f"{get_text('folder_open_error')}\n{e}"
            )

    # =========================================================================
    # Account Management
    # =========================================================================
    def _load_accounts(self):
        """Load saved accounts."""
        accounts = []

        if SAVED_AUTH_DIR.exists():
            for file in sorted(SAVED_AUTH_DIR.glob("*.json")):
                if file.name != ".gitkeep":
                    accounts.append(file.stem)

        # Update combobox
        self.account_combo.configure(values=accounts)

        # Update list
        self.account_list.clear()
        for acc in accounts:
            self.account_list.add_item(acc, icon="📧")

        # Select last account
        last = self.config.get("last_account", "")
        if last and last in accounts:
            self.selected_account.set(last)
            try:
                idx = accounts.index(last)
                self.account_list.select(idx)
            except Exception:
                pass
        elif accounts:
            self.selected_account.set(accounts[0])

        if accounts:
            self._log(get_text("log_accounts_loaded", count=len(accounts)))
        else:
            self._log(get_text("log_no_accounts"))

    def _account_selected(self, index: int):
        """Handle account selection."""
        items = self.account_list.get_items()
        if index < len(items):
            account_name = items[index]

            # Update detail view
            auth_file = SAVED_AUTH_DIR / f"{account_name}.json"
            if auth_file.exists():
                stat = auth_file.stat()
                mod_time = datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
                size_kb = stat.st_size / 1024

                self.account_detail.configure(
                    text=f"{get_text('file_label')} {account_name}.json\n"
                    f"{get_text('last_modified')} {mod_time}\n"
                    f"{get_text('size_label')} {size_kb:.1f} KB"
                )

            self.selected_account.set(account_name)

    def _account_double_click(self, index: int):
        """Handle double-click on account - select and go to Control tab."""
        items = self.account_list.get_items()
        if index < len(items):
            self.selected_account.set(items[index])
            self.tabview.set(get_text("tab_control"))

    def _add_new_account(self):
        """Add new account."""
        dialog = ctk.CTkInputDialog(
            text=get_text("new_account_prompt"),
            title=get_text("new_account_title"),
        )
        file_name = dialog.get_input()

        if not file_name:
            return

        if not file_name.replace("_", "").replace("-", "").isalnum():
            messagebox.showerror(get_text("error_title"), get_text("invalid_filename"))
            return

        self._log(get_text("log_adding_account", name=file_name))
        self._log(get_text("log_browser_login"))
        self._log(get_text("log_auto_save"))

        self._start_internal(mode="debug", save_auth_as=file_name, exit_on_save=True)

    def _delete_account(self):
        """Delete selected account."""
        account_name = self.account_list.get_selected()
        if not account_name:
            messagebox.showwarning(
                get_text("warning_title"), get_text("select_account_warning")
            )
            return

        if not messagebox.askyesno(
            get_text("confirm_title"),
            get_text("confirm_delete", name=account_name),
        ):
            return

        try:
            auth_file = SAVED_AUTH_DIR / f"{account_name}.json"
            if auth_file.exists():
                auth_file.unlink()

            active_file = ACTIVE_AUTH_DIR / f"{account_name}.json"
            if active_file.exists():
                active_file.unlink()

            self._log(get_text("log_account_deleted", name=account_name))
            self._load_accounts()

        except Exception as e:
            messagebox.showerror(
                get_text("error_title"), f"{get_text('account_delete_error')}\n{e}"
            )

    # =========================================================================
    # API & Browser
    # =========================================================================
    def _copy_api_url(self):
        """Copy API URL to clipboard."""
        url = f"http://127.0.0.1:{self.fastapi_port.get()}"
        copy_to_clipboard(self.root, url)
        self._log(get_text("copied_to_clipboard"))

    def _api_test(self):
        """Test the API endpoint."""
        port = self.fastapi_port.get()
        url = f"http://127.0.0.1:{port}/health"

        self._log(get_text("log_testing_api", url=url))

        try:
            import urllib.request
            import urllib.error

            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    self._log(get_text("log_api_running"))
                    self.status_details.configure(text=get_text("api_active"))
                    messagebox.showinfo(
                        get_text("success_title"), get_text("api_running")
                    )
                else:
                    self._log(get_text("log_api_status", code=response.status))
        except urllib.error.URLError:
            self._log(get_text("log_api_error"))
            self.status_details.configure(text=get_text("api_not_active"))
            messagebox.showwarning(
                get_text("warning_title"), get_text("api_not_responding")
            )
        except Exception as e:
            self._log(get_text("log_api_test_error", error=str(e)))

    def _open_in_browser(self):
        """Open API in browser."""
        port = self.fastapi_port.get()
        webbrowser.open(f"http://127.0.0.1:{port}")

    # =========================================================================
    # Settings
    # =========================================================================
    def _change_language(self):
        """Change the UI language."""
        new_lang = self.language_var.get()
        if new_lang != get_language():
            set_language(new_lang)
            self._save_config()
            self._log(get_text("log_language_changed"))
            self.root.title(get_text("title"))
            messagebox.showinfo(
                get_text("success_title"),
                "Language changed. Some changes will take effect after restart.\n"
                "语言已更改。部分更改将在重启后生效。",
            )

    def _change_appearance_mode(self):
        """Change the appearance mode (dark/light/system)."""
        new_mode = self.appearance_mode_var.get()
        if new_mode != get_appearance_mode():
            set_appearance_mode(new_mode)
            self._save_config()
            self._log(get_text("log_theme_changed", mode=new_mode))

    def _bind_settings_scroll_events(self, scrollable_frame):
        """Bind mouse wheel scroll events to settings scrollable frame."""
        self._bind_scroll_to_widget(scrollable_frame, scrollable_frame)

    def _bind_scroll_to_widget(self, widget, target_scrollable):
        """Recursively bind scroll events to widget and children.

        Skips any nested CTkScrollableFrame widgets since they handle
        their own scrolling independently.
        """
        # Skip if this is a nested scrollable frame (not the target itself)
        # Let nested scrollable frames handle their own scrolling
        if widget is not target_scrollable and isinstance(
            widget, ctk.CTkScrollableFrame
        ):
            return

        if platform.system() == "Linux":
            widget.bind(
                "<Button-4>", lambda e: self._on_scroll(target_scrollable, -3), add="+"
            )
            widget.bind(
                "<Button-5>", lambda e: self._on_scroll(target_scrollable, 3), add="+"
            )
        else:
            widget.bind(
                "<MouseWheel>",
                lambda e: self._on_mousewheel(e, target_scrollable),
                add="+",
            )

        # Recursively bind to children
        for child in widget.winfo_children():
            self._bind_scroll_to_widget(child, target_scrollable)

    def _on_mousewheel(self, event, target):
        """Handle mouse wheel on Windows/macOS."""
        if hasattr(target, "_parent_canvas") and target._parent_canvas:
            if platform.system() == "Darwin":
                target._parent_canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                target._parent_canvas.yview_scroll(
                    int(-1 * (event.delta / 120)), "units"
                )

    def _on_scroll(self, target, delta):
        """Handle scroll on Linux."""
        if hasattr(target, "_parent_canvas") and target._parent_canvas:
            target._parent_canvas.yview_scroll(delta, "units")

    def _save_and_notify(self):
        """Save settings and notify user."""
        # Validate ports
        if not validate_port(self.fastapi_port.get()):
            messagebox.showerror(get_text("error_title"), get_text("invalid_port"))
            return
        if not validate_port(self.stream_port.get()):
            messagebox.showerror(get_text("error_title"), get_text("invalid_port"))
            return
        if self.fastapi_port.get() == self.stream_port.get():
            messagebox.showerror(get_text("error_title"), get_text("port_conflict"))
            return

        self._save_config()
        self._log(get_text("log_settings_saved"))
        messagebox.showinfo(get_text("success_title"), get_text("settings_saved"))

        # Update API URL display
        self.api_url_label.configure(text=f"http://127.0.0.1:{self.fastapi_port.get()}")
        self.status_bar.set_port(int(self.fastapi_port.get()))

    def _reset_config(self):
        """Reset to default settings."""
        if messagebox.askyesno(get_text("confirm_title"), get_text("reset_confirm")):
            self.fastapi_port.set(str(DEFAULT_CONFIG["fastapi_port"]))
            self.stream_port.set(str(DEFAULT_CONFIG["stream_port"]))
            self.proxy_address.set("")
            self.proxy_enabled.set(False)
            self._save_config()
            self._log(get_text("log_settings_reset"))

    def _show_about(self):
        """Show about dialog."""
        about_text = f"""
{get_text("title")}

{get_text("about_version")} {VERSION}

{get_text("about_description")}

{get_text("about_credits")}
• @CJackHwang - Original author
• @beng1z - GUI Launcher
• @MasuRii - English fork maintainer
• Linux.do Community

GitHub: {GITHUB_URL}
        """
        messagebox.showinfo(get_text("about_title"), about_text.strip())

    # =========================================================================
    # Service Control
    # =========================================================================
    def _is_port_in_use(self, port: int) -> bool:
        """Check if port is in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return False
            except OSError:
                return True

    def _find_port_pids(self, port: int) -> List[int]:
        """Find PIDs using the port."""
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
            self._log(get_text("log_port_pid_error", error=str(e)))
        return list(set(pids))

    def _clean_ports(self) -> bool:
        """Clean up ports before starting."""
        ports = [
            int(self.fastapi_port.get() or 2048),
            9222,  # Camoufox
            int(self.stream_port.get() or 3120),
        ]
        cleaned = True

        for port in ports:
            if self._is_port_in_use(port):
                self._log(get_text("log_port_in_use", port=port))
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
                        self._log(get_text("log_pid_terminated", pid=pid))
                    except Exception as e:
                        self._log(get_text("log_pid_error", pid=pid, error=str(e)))
                        cleaned = False

                time.sleep(1)
                if self._is_port_in_use(port):
                    self._log(get_text("log_port_still_in_use", port=port))
                    cleaned = False

        return cleaned

    def _start(self):
        """Start the service."""
        if self.running:
            messagebox.showwarning(
                get_text("warning_title"), get_text("service_already_running")
            )
            return

        account = self.selected_account.get()
        if not account:
            messagebox.showerror(
                get_text("error_title"), get_text("select_account_error")
            )
            return

        # Save last account
        self.config["last_account"] = account
        self._save_config()

        mode = self.run_mode.get()
        self._start_internal(mode=mode, account=account)

    def _start_internal(
        self,
        mode: str,
        account: Optional[str] = None,
        save_auth_as: Optional[str] = None,
        exit_on_save: bool = False,
    ):
        """Internal start function."""
        self._log(get_text("log_checking_ports"))
        if not self._clean_ports():
            if not messagebox.askyesno(
                get_text("warning_title"), get_text("log_port_clean_warning")
            ):
                self._log(get_text("log_user_cancelled"))
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

        self._log(get_text("log_starting", mode=mode))

        # Environment variables
        env = os.environ.copy()
        env["DIRECT_LAUNCH"] = "true"

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
            self.status.set(get_text("status_running"))
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.status_details.configure(text=get_text("service_started"))
            self.pid_label.configure(text=f"{get_text('pid_label')} {self.process.pid}")

            # Update status badge color
            self.status_badge.configure(text_color=COLORS["success"])

            self.tray.update_status(True)
            self.status_bar.start_uptime()

            self.log_thread = threading.Thread(target=self._read_logs, daemon=True)
            self.log_thread.start()

            self._log(get_text("log_service_started", pid=self.process.pid))

        except Exception as e:
            self._log(f"❌ {get_text('start_error')} {e}")
            messagebox.showerror(
                get_text("error_title"), f"{get_text('start_error')}\n{e}"
            )
            self.running = False

    def _read_logs(self):
        """Log reading thread."""
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
        """Handle service ending."""
        self.running = False
        self.process = None

        if exit_code == 0:
            self.status.set(get_text("status_stopped"))
            self._log(get_text("log_service_ended"))
        else:
            self.status.set(f"{get_text('status_error')} ({exit_code})")
            self._log(get_text("log_service_error", code=exit_code))

        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_details.configure(text=get_text("service_stopped"))
        self.pid_label.configure(text=f"{get_text('pid_label')} -")

        # Update status badge color
        self.status_badge.configure(text_color=COLORS["text_secondary"])

        self.tray.update_status(False)
        self.status_bar.stop_uptime()

        # Refresh account list
        self._load_accounts()
        self._log(get_text("log_accounts_refreshed"))

    def _stop(self):
        """Stop the service."""
        if not self.running or not self.process:
            return

        self._log(get_text("log_stopping"))
        self.status.set(get_text("status_stopping"))

        try:
            if platform.system() == "Windows":
                self.process.terminate()
            else:
                self.process.send_signal(signal.SIGINT)

            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._log(get_text("log_force_closing"))
                self.process.kill()
                self.process.wait(timeout=3)

            self._log(get_text("log_stopped"))
        except Exception as e:
            self._log(get_text("log_stop_error", error=str(e)))

        self._service_ended(0)

    # =========================================================================
    # Window Management
    # =========================================================================
    def _show_window(self):
        """Show window."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _minimize_to_tray(self):
        """Minimize to tray or close."""
        if self.tray.supported and self.running:
            self.root.withdraw()
            self._log(get_text("log_minimized"))
        else:
            self._close_completely()

    def _close_completely(self):
        """Close the application completely."""
        if self.running:
            if messagebox.askyesno(get_text("confirm_title"), get_text("exit_confirm")):
                self._stop()
            else:
                return

        self._save_config()
        self.tray.stop()
        self.root.destroy()

    def run(self):
        """Run the application."""
        self._log(get_text("log_ready"))
        self.root.mainloop()


def main():
    """Main entry point."""
    SAVED_AUTH_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_AUTH_DIR.mkdir(parents=True, exist_ok=True)

    app = GUILauncher()
    app.run()


if __name__ == "__main__":
    main()
