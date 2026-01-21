"""
GUI Launcher System Tray

Cross-platform system tray support with AppIndicator3 (Linux/GNOME) and pystray fallback.
"""

import threading
from typing import TYPE_CHECKING, Optional

from .config import COLORS

if TYPE_CHECKING:
    from .app import GUILauncher


class TrayIcon:
    """Cross-platform system tray support"""

    def __init__(self, app: "GUILauncher"):
        self.app = app
        self.indicator = None
        self.supported = False
        self.backend: Optional[str] = None  # "appindicator" or "pystray"

    def create_icon(self) -> None:
        """Create tray icon - try AppIndicator3 first, then pystray"""
        # Try GNOME AppIndicator3 first (for Wayland)
        if self._try_appindicator():
            return

        # Then try pystray (for X11)
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
                "network-server",
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.indicator.set_menu(menu)
            self.indicator.set_title("AI Studio Proxy")

            # Run GTK main loop in separate thread
            def gtk_main():
                try:
                    Gtk.main()
                except Exception:
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
            # Draw accent-colored circle
            accent_rgb = tuple(
                int(COLORS["accent"].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)
            )
            bg_rgb = tuple(
                int(COLORS["bg_dark"].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)
            )
            draw.ellipse([4, 4, size - 4, size - 4], fill=accent_rgb)
            draw.ellipse([16, 16, size - 16, size - 16], fill=bg_rgb)

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

    def update_status(self, running: bool) -> None:
        """Update tray icon status"""
        if not self.supported:
            return
        # Status update - can be extended later

    def stop(self) -> None:
        """Stop tray icon"""
        try:
            if self.backend == "appindicator":
                import gi

                gi.require_version("Gtk", "3.0")
                from gi.repository import Gtk

                Gtk.main_quit()
            elif self.backend == "pystray" and self.indicator:
                self.indicator.stop()
        except Exception:
            pass
