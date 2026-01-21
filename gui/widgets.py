"""
GUI Launcher Custom Widgets

Extended widgets for the GUI including collapsible frames and setting editors.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from .config import COLORS, DIMENSIONS, FONTS


class CTkCollapsibleFrame(ctk.CTkFrame):
    """
    A collapsible frame widget that can be expanded/collapsed by clicking the header.

    The header shows a title with an expand/collapse indicator, and the content
    area can contain any widgets.
    """

    def __init__(
        self,
        master: Any,
        title: str,
        expanded: bool = False,
        on_toggle: Optional[Callable[[bool], None]] = None,
        **kwargs,
    ):
        """
        Initialize the collapsible frame.

        Args:
            master: Parent widget
            title: Title text for the header
            expanded: Initial expanded state
            on_toggle: Callback when expanded state changes
            **kwargs: Additional CTkFrame arguments
        """
        # Set default frame styling
        kwargs.setdefault("fg_color", COLORS["bg_medium"])
        kwargs.setdefault("corner_radius", DIMENSIONS["corner_radius"])

        super().__init__(master, **kwargs)

        self._title = title
        self._expanded = expanded
        self._on_toggle = on_toggle
        self._content_widgets: List[Any] = []

        # Configure grid
        self.grid_columnconfigure(0, weight=1)

        # Create header
        self._create_header()

        # Create content container
        self._content_frame = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )

        # Initial state
        if self._expanded:
            self._content_frame.grid(
                row=1, column=0, sticky="ew", padx=10, pady=(0, 10)
            )

        self._update_header_text()

    def _create_header(self) -> None:
        """Create the clickable header."""
        self._header_frame = ctk.CTkFrame(
            self,
            fg_color="transparent",
            cursor="hand2",
        )
        self._header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self._header_frame.grid_columnconfigure(1, weight=1)

        # Expand/collapse indicator and title
        self._header_label = ctk.CTkLabel(
            self._header_frame,
            text="",
            font=ctk.CTkFont(
                family=FONTS["family"], size=FONTS["size_large"], weight="bold"
            ),
            text_color=COLORS["accent"],
            cursor="hand2",
        )
        self._header_label.grid(row=0, column=0, sticky="w")

        # Bind click events
        self._header_frame.bind("<Button-1>", self._toggle)
        self._header_label.bind("<Button-1>", self._toggle)

    def _update_header_text(self) -> None:
        """Update header text based on expanded state."""
        indicator = "▼" if self._expanded else "▶"
        self._header_label.configure(text=f"{indicator} {self._title}")

    def _toggle(self, event=None) -> None:
        """Toggle expanded/collapsed state."""
        self._expanded = not self._expanded
        self._update_header_text()

        if self._expanded:
            self._content_frame.grid(
                row=1, column=0, sticky="ew", padx=10, pady=(0, 10)
            )
        else:
            self._content_frame.grid_forget()

        if self._on_toggle:
            self._on_toggle(self._expanded)

    def expand(self) -> None:
        """Expand the frame."""
        if not self._expanded:
            self._toggle()

    def collapse(self) -> None:
        """Collapse the frame."""
        if self._expanded:
            self._toggle()

    def is_expanded(self) -> bool:
        """Check if frame is expanded."""
        return self._expanded

    def set_title(self, title: str) -> None:
        """Update the title text."""
        self._title = title
        self._update_header_text()

    def get_content_frame(self) -> ctk.CTkFrame:
        """Get the content frame to add widgets to."""
        return self._content_frame


class CTkSettingRow(ctk.CTkFrame):
    """
    A single setting row with label and appropriate input widget.

    Supports:
    - bool: CTkSwitch
    - int/float: CTkEntry with validation
    - choice: CTkComboBox
    - string: CTkEntry
    """

    def __init__(
        self,
        master: Any,
        key: str,
        label: str,
        value: Any,
        type_hint: str,
        tooltip: Optional[str] = None,
        on_change: Optional[Callable[[str, Any], None]] = None,
        **kwargs,
    ):
        """
        Initialize a setting row.

        Args:
            master: Parent widget
            key: Setting key (env variable name)
            label: Display label
            value: Current value
            type_hint: Type hint (bool, int, float, choice:a,b,c, or string)
            tooltip: Optional tooltip text
            on_change: Callback when value changes (receives key and new value)
        """
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self._key = key
        self._type_hint = type_hint
        self._on_change = on_change
        self._value_var: Any = None

        # Configure grid
        self.grid_columnconfigure(0, weight=0, minsize=280)
        self.grid_columnconfigure(1, weight=1)

        # Create label
        self._label = ctk.CTkLabel(
            self,
            text=label,
            font=ctk.CTkFont(size=FONTS["size_normal"]),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        self._label.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)

        # Create input widget based on type
        self._create_input(value)

        # Add tooltip if provided
        if tooltip:
            from .utils import CTkTooltip

            CTkTooltip(self._label, tooltip)
            if hasattr(self, "_input_widget"):
                CTkTooltip(self._input_widget, tooltip)

    def _create_input(self, value: Any) -> None:
        """Create the appropriate input widget."""
        if self._type_hint == "bool":
            self._value_var = ctk.BooleanVar(value=bool(value))
            self._input_widget = ctk.CTkSwitch(
                self,
                text="",
                variable=self._value_var,
                command=self._on_value_change,
                fg_color=COLORS["bg_light"],
                progress_color=COLORS["accent"],
                button_color=COLORS["text_primary"],
                button_hover_color=COLORS["accent_hover"],
            )
            self._input_widget.grid(row=0, column=1, sticky="w", pady=5)

        elif self._type_hint == "int":
            self._value_var = ctk.StringVar(value=str(value))
            self._value_var.trace_add("write", lambda *args: self._on_value_change())
            self._input_widget = ctk.CTkEntry(
                self,
                textvariable=self._value_var,
                width=150,
                height=32,
                fg_color=COLORS["bg_light"],
                border_color=COLORS["border"],
                text_color=COLORS["text_primary"],
            )
            self._input_widget.grid(row=0, column=1, sticky="w", pady=5)

        elif self._type_hint == "float":
            self._value_var = ctk.StringVar(value=str(value))
            self._value_var.trace_add("write", lambda *args: self._on_value_change())
            self._input_widget = ctk.CTkEntry(
                self,
                textvariable=self._value_var,
                width=150,
                height=32,
                fg_color=COLORS["bg_light"],
                border_color=COLORS["border"],
                text_color=COLORS["text_primary"],
            )
            self._input_widget.grid(row=0, column=1, sticky="w", pady=5)

        elif self._type_hint.startswith("choice:"):
            choices = self._type_hint.replace("choice:", "").split(",")
            self._value_var = ctk.StringVar(value=str(value))
            self._input_widget = ctk.CTkComboBox(
                self,
                values=choices,
                variable=self._value_var,
                command=lambda v: self._on_value_change(),
                width=180,
                height=32,
                fg_color=COLORS["bg_light"],
                border_color=COLORS["border"],
                button_color=COLORS["accent"],
                button_hover_color=COLORS["accent_hover"],
                dropdown_fg_color=COLORS["bg_medium"],
                dropdown_hover_color=COLORS["bg_light"],
                text_color=COLORS["text_primary"],
                dropdown_text_color=COLORS["text_primary"],
            )
            self._input_widget.grid(row=0, column=1, sticky="w", pady=5)

        else:
            # Default: string entry
            self._value_var = ctk.StringVar(value=str(value) if value else "")
            self._value_var.trace_add("write", lambda *args: self._on_value_change())
            self._input_widget = ctk.CTkEntry(
                self,
                textvariable=self._value_var,
                width=250,
                height=32,
                fg_color=COLORS["bg_light"],
                border_color=COLORS["border"],
                text_color=COLORS["text_primary"],
            )
            self._input_widget.grid(row=0, column=1, sticky="w", pady=5)

    def _on_value_change(self) -> None:
        """Handle value change."""
        if self._on_change:
            self._on_change(self._key, self.get_value())

    def get_value(self) -> Any:
        """Get the current value with proper type conversion."""
        if self._type_hint == "bool":
            return self._value_var.get()
        elif self._type_hint == "int":
            try:
                return int(self._value_var.get())
            except ValueError:
                return 0
        elif self._type_hint == "float":
            try:
                return float(self._value_var.get())
            except ValueError:
                return 0.0
        else:
            return self._value_var.get()

    def set_value(self, value: Any) -> None:
        """Set the value."""
        if self._type_hint == "bool":
            self._value_var.set(bool(value))
        else:
            self._value_var.set(str(value))

    def get_key(self) -> str:
        """Get the setting key."""
        return self._key

    def set_modified_indicator(self, modified: bool) -> None:
        """Show/hide modified indicator on the label."""
        base_label = self._label.cget("text").replace(" *", "")
        if modified:
            self._label.configure(text=f"{base_label} *", text_color=COLORS["warning"])
        else:
            self._label.configure(text=base_label, text_color=COLORS["text_primary"])


class CTkEnvSettingsPanel(ctk.CTkScrollableFrame):
    """
    A scrollable panel containing all environment settings organized by category.

    Features:
    - Collapsible category sections
    - Tracks modified values
    - Provides save/reload/reset functionality
    """

    def __init__(
        self,
        master: Any,
        env_manager: Any,
        on_save: Optional[Callable[[], None]] = None,
        on_change: Optional[Callable[[bool], None]] = None,
        **kwargs,
    ):
        """
        Initialize the settings panel.

        Args:
            master: Parent widget
            env_manager: EnvManager instance
            on_save: Callback when settings are saved
            on_change: Callback when dirty state changes (receives is_dirty)
        """
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self._env_manager = env_manager
        self._on_save = on_save
        self._on_change = on_change
        self._setting_rows: Dict[str, CTkSettingRow] = {}
        self._category_frames: Dict[str, CTkCollapsibleFrame] = {}
        self._is_dirty = False

        # Build the UI
        self._build_settings_ui()

    def _build_settings_ui(self) -> None:
        """Build the settings UI with collapsible categories."""
        from .i18n import get_text

        # Get category order
        category_order = [
            "server",
            "logging",
            "auth",
            "cookie",
            "browser",
            "api",
            "function_calling",
            "timeouts",
            "misc",
        ]

        for cat_key in category_order:
            keys = self._env_manager.get_category_keys(cat_key)
            if not keys:
                continue

            # Create collapsible frame for category
            cat_title = get_text(f"cat_{cat_key}")
            frame = CTkCollapsibleFrame(
                self,
                title=cat_title,
                expanded=False,
            )
            frame.pack(fill="x", pady=(0, 10))
            self._category_frames[cat_key] = frame

            # Get content frame and add settings
            content = frame.get_content_frame()
            content.grid_columnconfigure(0, weight=1)

            for idx, key in enumerate(sorted(keys)):
                schema = self._env_manager.get_schema_info(key)
                if not schema:
                    continue

                default_val, type_hint, description, _ = schema
                current_val = self._env_manager.get(key)

                row = CTkSettingRow(
                    content,
                    key=key,
                    label=description,
                    value=current_val,
                    type_hint=type_hint,
                    on_change=self._on_setting_change,
                )
                row.grid(row=idx, column=0, sticky="ew", padx=5, pady=2)
                self._setting_rows[key] = row

    def _on_setting_change(self, key: str, value: Any) -> None:
        """Handle individual setting change."""
        self._env_manager.set(key, value)

        # Update modified indicator
        schema = self._env_manager.get_schema_info(key)
        if schema:
            default_val = schema[0]
            is_modified = value != default_val
            if key in self._setting_rows:
                self._setting_rows[key].set_modified_indicator(is_modified)

        # Check overall dirty state
        new_dirty = self._env_manager.is_dirty()
        if new_dirty != self._is_dirty:
            self._is_dirty = new_dirty
            if self._on_change:
                self._on_change(new_dirty)

    def save(self) -> bool:
        """Save all settings to .env file."""
        success = self._env_manager.save()
        if success:
            self._is_dirty = False
            # Clear all modified indicators
            for row in self._setting_rows.values():
                row.set_modified_indicator(False)
            if self._on_change:
                self._on_change(False)
            if self._on_save:
                self._on_save()
        return success

    def reload(self) -> None:
        """Reload settings from .env file."""
        self._env_manager.load()

        # Update all setting rows
        for key, row in self._setting_rows.items():
            value = self._env_manager.get(key)
            row.set_value(value)
            row.set_modified_indicator(False)

        self._is_dirty = False
        if self._on_change:
            self._on_change(False)

    def reset_to_defaults(self) -> None:
        """Reset all settings to default values."""
        self._env_manager.reset_to_defaults()

        # Update all setting rows
        for key, row in self._setting_rows.items():
            schema = self._env_manager.get_schema_info(key)
            if schema:
                row.set_value(schema[0])
                row.set_modified_indicator(False)

        self._is_dirty = True
        if self._on_change:
            self._on_change(True)

    def is_dirty(self) -> bool:
        """Check if there are unsaved changes."""
        return self._is_dirty

    def expand_all(self) -> None:
        """Expand all category frames."""
        for frame in self._category_frames.values():
            frame.expand()

    def collapse_all(self) -> None:
        """Collapse all category frames."""
        for frame in self._category_frames.values():
            frame.collapse()

    def get_modified_keys(self) -> List[str]:
        """Get list of modified setting keys."""
        return self._env_manager.get_modified_keys()
