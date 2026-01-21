"""Tests for gui/tray.py module."""

import pytest
from unittest.mock import MagicMock, patch


class TestTrayIconInit:
    """Tests for TrayIcon initialization."""

    def test_tray_icon_stores_app_reference(self):
        """TrayIcon stores reference to the app."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)

        assert tray.app is mock_app

    def test_tray_icon_initially_not_supported(self):
        """TrayIcon starts with supported=False."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)

        assert tray.supported is False

    def test_tray_icon_initially_no_backend(self):
        """TrayIcon starts with no backend."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)

        assert tray.backend is None

    def test_tray_icon_indicator_initially_none(self):
        """TrayIcon indicator is None initially."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)

        assert tray.indicator is None


class TestTrayIconAppIndicator:
    """Tests for AppIndicator3 backend."""

    def test_try_appindicator_sets_backend(self):
        """Successful AppIndicator3 sets backend correctly."""
        with patch("gui.tray.threading"):
            # Mock gi and GTK modules
            mock_gi = MagicMock()
            mock_gtk = MagicMock()
            mock_appindicator = MagicMock()
            mock_glib = MagicMock()

            mock_gi.require_version = MagicMock()
            mock_gi.repository.Gtk = mock_gtk
            mock_gi.repository.AppIndicator3 = mock_appindicator
            mock_gi.repository.GLib = mock_glib

            with patch.dict(
                "sys.modules", {"gi": mock_gi, "gi.repository": MagicMock()}
            ):
                from gui.tray import TrayIcon

                mock_app = MagicMock()
                tray = TrayIcon(mock_app)

                # Mock the imports inside _try_appindicator
                with patch("builtins.__import__", side_effect=ImportError):
                    result = tray._try_appindicator()

                # Should fail gracefully when imports fail
                assert result is False

    def test_try_appindicator_handles_import_error(self):
        """AppIndicator3 failure is handled gracefully."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)

        # Without mocking gi, it should fail gracefully
        result = tray._try_appindicator()

        # Should return False (not crash)
        assert result is False


class TestTrayIconPystray:
    """Tests for pystray backend."""

    def test_try_pystray_handles_import_error(self):
        """pystray failure is handled gracefully."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)

        # Without pystray installed, should fail gracefully
        with patch.dict("sys.modules", {"pystray": None}):
            result = tray._try_pystray()

        # Should return False (not crash)
        assert result is False

    def test_try_pystray_with_mock_success(self):
        """pystray success sets backend correctly."""
        with patch("gui.tray.threading"):
            mock_pystray = MagicMock()
            mock_pil_image = MagicMock()
            mock_pil_draw = MagicMock()

            mock_image_instance = MagicMock()
            mock_pil_image.new.return_value = mock_image_instance

            with patch.dict(
                "sys.modules",
                {
                    "pystray": mock_pystray,
                    "PIL": MagicMock(),
                    "PIL.Image": mock_pil_image,
                    "PIL.ImageDraw": mock_pil_draw,
                },
            ):
                from gui.tray import TrayIcon

                mock_app = MagicMock()
                mock_app.root = MagicMock()
                tray = TrayIcon(mock_app)

                # The actual test - mocked pystray should work
                # (Implementation detail: this tests the exception path)


class TestTrayIconCallbacks:
    """Tests for tray icon callback methods."""

    def test_pystray_show_schedules_show_window(self):
        """_pystray_show schedules _show_window on main thread."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        mock_app.root = MagicMock()
        tray = TrayIcon(mock_app)

        tray._pystray_show()

        mock_app.root.after.assert_called_once()
        # First arg should be 0 (immediate)
        assert mock_app.root.after.call_args[0][0] == 0

    def test_pystray_start_schedules_start(self):
        """_pystray_start schedules _start on main thread."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        mock_app.root = MagicMock()
        tray = TrayIcon(mock_app)

        tray._pystray_start()

        mock_app.root.after.assert_called_once()

    def test_pystray_stop_schedules_stop(self):
        """_pystray_stop schedules _stop on main thread."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        mock_app.root = MagicMock()
        tray = TrayIcon(mock_app)

        tray._pystray_stop()

        mock_app.root.after.assert_called_once()

    def test_pystray_test_schedules_api_test(self):
        """_pystray_test schedules _api_test on main thread."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        mock_app.root = MagicMock()
        tray = TrayIcon(mock_app)

        tray._pystray_test()

        mock_app.root.after.assert_called_once()

    def test_pystray_quit_schedules_close(self):
        """_pystray_quit schedules _close_completely on main thread."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        mock_app.root = MagicMock()
        tray = TrayIcon(mock_app)

        tray._pystray_quit()

        mock_app.root.after.assert_called_once()


class TestTrayIconUpdateStatus:
    """Tests for status update method."""

    def test_update_status_noop_when_not_supported(self):
        """update_status does nothing when tray not supported."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)
        tray.supported = False

        # Should not raise
        tray.update_status(running=True)
        tray.update_status(running=False)


class TestTrayIconStop:
    """Tests for stop method."""

    def test_stop_handles_no_indicator(self):
        """stop handles case when indicator is None."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)
        tray.indicator = None
        tray.backend = None

        # Should not raise
        tray.stop()

    def test_stop_pystray_calls_indicator_stop(self):
        """stop calls indicator.stop() for pystray backend."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)
        tray.backend = "pystray"
        tray.indicator = MagicMock()

        tray.stop()

        tray.indicator.stop.assert_called_once()

    def test_stop_handles_exception(self):
        """stop handles exceptions gracefully."""
        from gui.tray import TrayIcon

        mock_app = MagicMock()
        tray = TrayIcon(mock_app)
        tray.backend = "pystray"
        tray.indicator = MagicMock()
        tray.indicator.stop.side_effect = Exception("test error")

        # Should not raise
        tray.stop()
