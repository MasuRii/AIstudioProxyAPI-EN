"""
GUI Launcher Utilities

Helper functions and widgets for the CustomTkinter GUI.
"""

import customtkinter as ctk
from typing import Callable, Optional, List
import time

from .config import COLORS, FONTS, DIMENSIONS
from .i18n import get_text


class CTkTooltip:
    """
    Modern tooltip widget for CustomTkinter.

    Shows a tooltip on hover with smooth appearance.

    Usage:
        CTkTooltip(widget, "tooltip_key")
    """

    def __init__(self, widget: ctk.CTkBaseClass, text_key: str):
        self.widget = widget
        self.text_key = text_key
        self.tooltip_window: Optional[ctk.CTkToplevel] = None
        self._scheduled_id = None

        widget.bind("<Enter>", self._schedule_show)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule_show(self, event=None) -> None:
        """Schedule tooltip to appear after delay."""
        self._cancel_schedule()
        self._scheduled_id = self.widget.after(500, self._show)

    def _cancel_schedule(self) -> None:
        """Cancel scheduled tooltip."""
        if self._scheduled_id:
            self.widget.after_cancel(self._scheduled_id)
            self._scheduled_id = None

    def _show(self) -> None:
        """Show the tooltip."""
        if self.tooltip_window:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        # Remove window decorations and make it float
        self.tooltip_window.attributes("-topmost", True)

        # Tooltip frame with rounded corners
        frame = ctk.CTkFrame(
            self.tooltip_window,
            fg_color=COLORS["bg_medium"],
            corner_radius=DIMENSIONS["corner_radius_small"],
            border_width=1,
            border_color=COLORS["border"],
        )
        frame.pack(fill="both", expand=True)

        label = ctk.CTkLabel(
            frame,
            text=get_text(self.text_key),
            font=ctk.CTkFont(family=FONTS["family"], size=FONTS["size_small"]),
            text_color=COLORS["text_primary"],
            wraplength=300,
        )
        label.pack(padx=10, pady=6)

    def _hide(self, event=None) -> None:
        """Hide the tooltip."""
        self._cancel_schedule()
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


# Alias for backwards compatibility
Tooltip = CTkTooltip


class CTkScrollableList(ctk.CTkScrollableFrame):
    """
    A scrollable list widget with selectable items.

    Replaces the old tk.Listbox with a modern CTk implementation.

    Usage:
        sl = CTkScrollableList(parent)
        sl.add_item("Item 1")
        sl.add_item("Item 2", icon="📧")
        sl.bind_select(callback)
    """

    def __init__(self, parent, height: int = 300, **kwargs):
        super().__init__(
            parent,
            height=height,
            fg_color=COLORS["bg_light"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            **kwargs,
        )

        self.items: List[ctk.CTkButton] = []
        self.selected_index: Optional[int] = None
        self._on_select: Optional[Callable] = None
        self._on_double_click: Optional[Callable] = None

    def add_item(self, text: str, icon: str = "") -> None:
        """Add an item to the list."""
        display_text = f"{icon}  {text}" if icon else text

        item = ctk.CTkButton(
            self,
            text=display_text,
            anchor="w",
            height=36,
            corner_radius=DIMENSIONS["corner_radius_small"],
            fg_color="transparent",
            hover_color=COLORS["bg_medium"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family=FONTS["family"], size=FONTS["size_normal"]),
            command=lambda idx=len(self.items): self._select(idx),
        )
        item.pack(fill="x", padx=4, pady=2)
        item.bind("<Double-1>", lambda e, idx=len(self.items): self._double_click(idx))
        self.items.append(item)

    def clear(self) -> None:
        """Clear all items."""
        for item in self.items:
            item.destroy()
        self.items.clear()
        self.selected_index = None

    def _select(self, index: int) -> None:
        """Handle item selection."""
        # Deselect previous
        if self.selected_index is not None and self.selected_index < len(self.items):
            self.items[self.selected_index].configure(
                fg_color="transparent",
                text_color=COLORS["text_primary"],
            )

        # Select new
        self.selected_index = index
        if index < len(self.items):
            self.items[index].configure(
                fg_color=COLORS["accent"],
                text_color=COLORS["text_on_color"],  # White text on colored background
            )

        if self._on_select:
            self._on_select(index)

    def _double_click(self, index: int) -> None:
        """Handle double click."""
        self._select(index)
        if self._on_double_click:
            self._on_double_click(index)

    def bind_select(self, callback: Callable[[int], None]) -> None:
        """Bind selection callback."""
        self._on_select = callback

    def bind_double_click(self, callback: Callable[[int], None]) -> None:
        """Bind double-click callback."""
        self._on_double_click = callback

    def get_selected(self) -> Optional[str]:
        """Get selected item text."""
        if self.selected_index is not None and self.selected_index < len(self.items):
            text = self.items[self.selected_index].cget("text")
            # Remove icon prefix if present
            if "  " in text:
                return text.split("  ", 1)[1]
            return text
        return None

    def get_selected_index(self) -> Optional[int]:
        """Get selected index."""
        return self.selected_index

    def select(self, index: int) -> None:
        """Select item by index."""
        if 0 <= index < len(self.items):
            self._select(index)

    def get_items(self) -> List[str]:
        """Get all item texts (without icons)."""
        result = []
        for item in self.items:
            text = item.cget("text")
            if "  " in text:
                result.append(text.split("  ", 1)[1])
            else:
                result.append(text)
        return result


# Backwards compatibility alias
ScrollableListbox = CTkScrollableList


class CTkStatusBar(ctk.CTkFrame):
    """
    Modern status bar widget for the bottom of the window.

    Features:
    - Status text
    - Port display
    - Uptime counter

    Usage:
        sb = CTkStatusBar(root)
        sb.set_status("Ready")
        sb.set_port(2048)
        sb.start_uptime()
    """

    def __init__(self, parent):
        super().__init__(
            parent,
            height=32,
            fg_color=COLORS["bg_medium"],
            corner_radius=0,
        )

        # Prevent frame from shrinking
        self.pack_propagate(False)

        # Left - status text
        self.status_label = ctk.CTkLabel(
            self,
            text=get_text("statusbar_ready"),
            font=ctk.CTkFont(family=FONTS["family"], size=FONTS["size_small"]),
            text_color=COLORS["text_secondary"],
        )
        self.status_label.pack(side="left", padx=15)

        # Right - port info
        self.port_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family=FONTS["family"], size=FONTS["size_small"]),
            text_color=COLORS["text_secondary"],
        )
        self.port_label.pack(side="right", padx=15)

        # Uptime (next to port)
        self.uptime_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family=FONTS["family_mono"], size=FONTS["size_small"]),
            text_color=COLORS["success"],
        )
        self.uptime_label.pack(side="right", padx=(0, 20))

        # Uptime tracking
        self._start_time: Optional[float] = None
        self._uptime_job = None

    def set_status(self, status: str) -> None:
        """Set the status text."""
        self.status_label.configure(text=status)

    def set_port(self, port: int) -> None:
        """Set the port display."""
        self.port_label.configure(text=f"{get_text('statusbar_port')} {port}")

    def start_uptime(self) -> None:
        """Start the uptime counter."""
        self._start_time = time.time()
        self._update_uptime()

    def stop_uptime(self) -> None:
        """Stop the uptime counter."""
        if self._uptime_job:
            self.after_cancel(self._uptime_job)
            self._uptime_job = None
        self._start_time = None
        self.uptime_label.configure(text="")

    def _update_uptime(self) -> None:
        """Update the uptime display."""
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            self.uptime_label.configure(
                text=f"{get_text('statusbar_uptime')} {format_uptime(elapsed)}"
            )
            self._uptime_job = self.after(1000, self._update_uptime)


# Backwards compatibility alias
StatusBar = CTkStatusBar


# =============================================================================
# Pure Utility Functions
# =============================================================================


def validate_port(port_str: str) -> bool:
    """Validate that a string is a valid port number (1-65535)."""
    try:
        port = int(port_str)
        return 1 <= port <= 65535
    except ValueError:
        return False


def format_uptime(seconds: int) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def copy_to_clipboard(root, text: str) -> None:
    """Copy text to system clipboard."""
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()  # Required for clipboard to persist
