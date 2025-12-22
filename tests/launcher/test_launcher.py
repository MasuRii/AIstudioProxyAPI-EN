import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from launcher.checks import check_dependencies, ensure_auth_dirs_exist
from launcher.config import determine_proxy_configuration, parse_args
from launcher.utils import (
    find_pids_on_port,
    get_proxy_from_gsettings,
    is_port_in_use,
    kill_process_interactive,
)

# --- Test launcher.config ---


def test_parse_args_defaults(clean_launcher_env):
    """Test argument parsing with default values."""
    with (
        patch.dict(os.environ, {"STREAM_PORT": "3120"}),
        patch.object(sys, "argv", ["launcher"]),
    ):
        # Patch constants to ensure we test against known defaults
        with (
            patch("launcher.config.DEFAULT_STREAM_PORT", 3120),
            patch("launcher.config.DEFAULT_CAMOUFOX_PORT", 9222),
        ):
            args = parse_args()
            assert args.server_port == 2048
            assert args.stream_port == 3120
            assert args.camoufox_debug_port == 9222
            assert args.debug is False
            assert args.headless is False


def test_parse_args_custom():
    """Test argument parsing with custom values."""
    test_args = [
        "launcher",
        "--server-port",
        "8080",
        "--stream-port",
        "9090",
        "--debug",
        "--active-auth-json",
        "test.json",
    ]
    with patch.object(sys, "argv", test_args):
        args = parse_args()
        assert args.server_port == 8080
        assert args.stream_port == 9090
        assert args.debug is True
        assert args.active_auth_json == "test.json"


def test_determine_proxy_configuration_arg():
    """Test proxy configuration from command-line argument."""
    result = determine_proxy_configuration(
        internal_camoufox_proxy_arg="http://proxy:8080"
    )
    assert result["camoufox_proxy"] == "http://proxy:8080"
    assert result["stream_proxy"] == "http://proxy:8080"
    assert result["source"] is not None
    assert "CLI argument" in result["source"]


def test_determine_proxy_configuration_env():
    """Test proxy configuration from environment variable."""
    with patch.dict(os.environ, {"UNIFIED_PROXY_CONFIG": "http://env:8080"}):
        result = determine_proxy_configuration()
        assert result["camoufox_proxy"] == "http://env:8080"
        assert result["source"] is not None
        assert "Environment variable UNIFIED_PROXY_CONFIG" in result["source"]


# --- Test launcher.utils ---


@pytest.mark.parametrize(
    "bind_side_effect,expected_result,test_id",
    [
        (OSError("Port in use"), True, "port_in_use"),
        (None, False, "port_free"),
    ],
)
@patch("socket.socket")
def test_is_port_in_use(mock_socket, bind_side_effect, expected_result, test_id):
    """Test port availability check when port is in use or free."""
    mock_socket_instance = MagicMock()
    mock_socket.return_value.__enter__.return_value = mock_socket_instance

    if bind_side_effect:
        mock_socket_instance.bind.side_effect = bind_side_effect

    assert is_port_in_use(8080) is expected_result


@patch("subprocess.Popen")
@patch("platform.system")
def test_find_pids_on_port_linux(mock_system, mock_popen):
    """Test finding processes on port using lsof (Linux)."""
    mock_system.return_value = "Linux"
    process_mock = MagicMock()
    process_mock.communicate.return_value = ("123\n456\n", "")
    process_mock.returncode = 0
    mock_popen.return_value = process_mock

    pids = find_pids_on_port(8080)
    assert 123 in pids
    assert 456 in pids


@patch("subprocess.Popen")
@patch("platform.system")
def test_find_pids_on_port_windows(mock_system, mock_popen):
    """Test finding processes on port using netstat (Windows)."""
    mock_system.return_value = "Windows"
    process_mock = MagicMock()
    # Simulate netstat output
    output = (
        "  TCP    0.0.0.0:8080           0.0.0.0:0              LISTENING       1234\n"
    )
    process_mock.communicate.return_value = (output, "")
    process_mock.returncode = 0
    mock_popen.return_value = process_mock

    pids = find_pids_on_port(8080)
    assert 1234 in pids


@patch("subprocess.run")
@patch("platform.system")
def test_kill_process_interactive_linux(mock_system, mock_run):
    """Test killing process on Linux using kill command."""
    mock_system.return_value = "Linux"
    mock_run.return_value.returncode = 0

    assert kill_process_interactive(1234) is True
    mock_run.assert_called_with(
        "kill 1234", shell=True, capture_output=True, text=True, timeout=3, check=False
    )


@patch("subprocess.run")
@patch("platform.system")
def test_kill_process_interactive_windows(mock_system, mock_run):
    """Test killing process on Windows using taskkill."""
    mock_system.return_value = "Windows"
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = (
        "SUCCESS: The process with PID 1234 has been terminated."
    )

    assert kill_process_interactive(1234) is True
    mock_run.assert_called()


@patch("subprocess.run")
def test_get_proxy_from_gsettings(mock_run):
    """Test retrieving proxy configuration from gsettings (Linux)."""
    # Mock sequence of calls: mode, http host, http port
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="'manual'"),
        MagicMock(returncode=0, stdout="'proxy.example.com'"),
        MagicMock(returncode=0, stdout="'8080'"),
    ]

    proxy = get_proxy_from_gsettings()
    assert proxy == "http://proxy.example.com:8080"


# --- Test launcher.checks ---


@patch("os.makedirs")
def test_ensure_auth_dirs_exist(mock_makedirs):
    """Test creation of authentication directories."""
    ensure_auth_dirs_exist()
    assert mock_makedirs.call_count == 2


@patch("sys.exit")
def test_check_dependencies_missing_camoufox(mock_exit):
    """Test dependency check exits when camoufox is missing."""
    # Simulate missing camoufox
    with patch.dict(sys.modules, {"camoufox": None}):
        # We need to mock __import__ to raise ImportError for camoufox
        original_import = __import__

        def side_effect(name, *args, **kwargs):
            if name == "camoufox":
                raise ImportError("No module named 'camoufox'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=side_effect):
            check_dependencies(launch_server=True, DefaultAddons=True)
            mock_exit.assert_called_with(1)


def test_check_dependencies_success():
    """Test dependency check succeeds when all dependencies are available."""
    with (
        patch("builtins.__import__"),
        patch("sys.modules", {"server": MagicMock(), "server.app": MagicMock()}),
    ):
        # Mock server.app import
        with patch.dict(sys.modules):
            sys.modules["server"] = MagicMock()
            sys.modules["server"].app = MagicMock()

            # Should not raise SystemExit
            check_dependencies(launch_server=None, DefaultAddons=None)
