"""
Tests for launcher/internal.py - Internal Camoufox launch mode.

Tests the run_internal_camoufox function which handles the --internal-launch-mode
argument for starting Camoufox in a subprocess with specific configurations.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestRunInternalCamoufox:
    """Tests for run_internal_camoufox function."""

    def test_exits_when_launch_server_missing(self) -> None:
        """Verify sys.exit(1) when launch_server is None."""
        from launcher.internal import run_internal_camoufox

        mock_args = MagicMock()

        with pytest.raises(SystemExit) as exc_info:
            run_internal_camoufox(
                mock_args, launch_server=None, DefaultAddons=MagicMock()
            )

        assert exc_info.value.code == 1

    def test_exits_when_default_addons_missing(self) -> None:
        """Verify sys.exit(1) when DefaultAddons is None."""
        from launcher.internal import run_internal_camoufox

        mock_args = MagicMock()

        with pytest.raises(SystemExit) as exc_info:
            run_internal_camoufox(
                mock_args, launch_server=MagicMock(), DefaultAddons=None
            )

        assert exc_info.value.code == 1

    def test_headless_mode_launch(self) -> None:
        """Verify headless mode calls launch_server with headless=True."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="headless",
            internal_auth_file=None,
            internal_camoufox_port=9222,
            internal_camoufox_proxy=None,
            internal_camoufox_os="random",
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_proxy.return_value = {"camoufox_proxy": None, "source": "默认无代理"}
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        assert exc_info.value.code == 0
        mock_launch_server.assert_called_once()
        call_kwargs = mock_launch_server.call_args
        assert call_kwargs[1]["headless"] is True

    def test_virtual_headless_mode_launch(self) -> None:
        """Verify virtual_headless mode calls launch_server with headless='virtual'."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="virtual_headless",
            internal_auth_file=None,
            internal_camoufox_port=9222,
            internal_camoufox_proxy=None,
            internal_camoufox_os="random",
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_proxy.return_value = {"camoufox_proxy": None, "source": "默认无代理"}
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        assert exc_info.value.code == 0
        mock_launch_server.assert_called_once()
        call_kwargs = mock_launch_server.call_args
        assert call_kwargs[1]["headless"] == "virtual"

    def test_debug_mode_launch(self) -> None:
        """Verify debug mode calls launch_server with headless=False."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="debug",
            internal_auth_file=None,
            internal_camoufox_port=9222,
            internal_camoufox_proxy=None,
            internal_camoufox_os="linux",
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_proxy.return_value = {"camoufox_proxy": None, "source": "默认无代理"}
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        assert exc_info.value.code == 0
        mock_launch_server.assert_called_once()
        call_kwargs = mock_launch_server.call_args
        assert call_kwargs[1]["headless"] is False

    def test_with_auth_file(self) -> None:
        """Verify storage_state is set when auth file is provided."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="headless",
            internal_auth_file="/path/to/auth.json",
            internal_camoufox_port=9222,
            internal_camoufox_proxy=None,
            internal_camoufox_os="random",
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit),
        ):
            mock_proxy.return_value = {"camoufox_proxy": None, "source": "默认无代理"}
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        call_args = mock_launch_server.call_args[1]
        assert call_args["storage_state"] == "/path/to/auth.json"

    def test_with_proxy(self) -> None:
        """Verify proxy is set when provided."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="headless",
            internal_auth_file=None,
            internal_camoufox_port=9222,
            internal_camoufox_proxy="http://proxy:8080",
            internal_camoufox_os="random",
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit),
        ):
            mock_proxy.return_value = {
                "camoufox_proxy": "http://proxy:8080",
                "source": "命令行参数",
            }
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        call_args = mock_launch_server.call_args[1]
        assert call_args["proxy"] == {"server": "http://proxy:8080"}

    def test_os_list_comma_separated(self) -> None:
        """Verify comma-separated OS list is handled correctly."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="headless",
            internal_auth_file=None,
            internal_camoufox_port=9222,
            internal_camoufox_proxy=None,
            internal_camoufox_os="windows,linux,macos",
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit),
        ):
            mock_proxy.return_value = {"camoufox_proxy": None, "source": "默认无代理"}
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        call_args = mock_launch_server.call_args[1]
        assert call_args["os"] == ["windows", "linux", "macos"]

    def test_invalid_os_in_list_exits(self) -> None:
        """Verify invalid OS value in list causes exit(1)."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="headless",
            internal_auth_file=None,
            internal_camoufox_port=9222,
            internal_camoufox_proxy=None,
            internal_camoufox_os="windows,invalid_os",
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_proxy.return_value = {"camoufox_proxy": None, "source": "默认无代理"}
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        assert exc_info.value.code == 1

    def test_single_os_value(self) -> None:
        """Verify single OS value (not comma-separated) is handled correctly."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="headless",
            internal_auth_file=None,
            internal_camoufox_port=9222,
            internal_camoufox_proxy=None,
            internal_camoufox_os="Windows",  # Test case-insensitive
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit),
        ):
            mock_proxy.return_value = {"camoufox_proxy": None, "source": "默认无代理"}
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        call_args = mock_launch_server.call_args[1]
        assert call_args["os"] == "windows"

    def test_invalid_single_os_exits(self) -> None:
        """Verify invalid single OS value causes exit(1)."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="headless",
            internal_auth_file=None,
            internal_camoufox_port=9222,
            internal_camoufox_proxy=None,
            internal_camoufox_os="invalid_os",
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_proxy.return_value = {"camoufox_proxy": None, "source": "默认无代理"}
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        assert exc_info.value.code == 1

    def test_launch_server_exception_exits(self) -> None:
        """Verify exception during launch_server causes exit(1)."""
        from launcher.internal import run_internal_camoufox

        mock_launch_server = MagicMock()
        mock_launch_server.side_effect = RuntimeError("Browser failed to start")
        mock_default_addons = MagicMock()
        mock_default_addons.UBO = "ubo_addon"

        mock_args = SimpleNamespace(
            internal_launch_mode="headless",
            internal_auth_file=None,
            internal_camoufox_port=9222,
            internal_camoufox_proxy=None,
            internal_camoufox_os="random",
        )

        with (
            patch("launcher.internal.determine_proxy_configuration") as mock_proxy,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_proxy.return_value = {"camoufox_proxy": None, "source": "默认无代理"}
            run_internal_camoufox(mock_args, mock_launch_server, mock_default_addons)

        assert exc_info.value.code == 1
