"""
Comprehensive tests for launcher/utils.py

Targets:
- is_port_in_use(): port availability checking
- find_pids_on_port(): cross-platform PID discovery
- kill_process_interactive(): process termination
- input_with_timeout(): timed user input
- get_proxy_from_gsettings(): Linux proxy detection

Coverage target: 75% (add ~35-45 statements out of 68 missing)
"""

import socket
import subprocess
from unittest.mock import MagicMock, patch

from launcher.utils import (
    find_pids_on_port,
    get_proxy_from_gsettings,
    input_with_timeout,
    is_port_in_use,
    kill_process_interactive,
)

# ==================== is_port_in_use TESTS ====================


def test_is_port_in_use_free_port():
    """Test port availability check on a free port."""
    # Find a free port by binding to port 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    # Port should be free after socket closes
    assert is_port_in_use(free_port) is False


def test_is_port_in_use_occupied_port():
    """Test port availability check on an occupied port."""
    # The actual code uses SO_REUSEADDR, so just binding a listening socket
    # won't make it detect as "in use". We need to trigger an OSError.
    # Let's mock socket to raise OSError on bind.

    with patch("launcher.utils.socket.socket") as mock_socket:
        mock_socket_instance = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_socket_instance

        # Simulate port already in use (OSError on bind)
        mock_socket_instance.bind.side_effect = OSError("Address already in use")

        result = is_port_in_use(8080)

        assert result is True


def test_is_port_in_use_exception():
    """Test exception handling in port check."""
    # Mock socket to raise generic exception
    with patch("launcher.utils.socket.socket") as mock_socket:
        mock_socket_instance = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_socket_instance
        mock_socket_instance.bind.side_effect = ValueError("Unexpected error")

        # Should return True and log warning
        result = is_port_in_use(12345)
        assert result is True


# ==================== find_pids_on_port TESTS ====================


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.Popen")
def test_find_pids_on_port_linux_success(mock_popen, mock_platform):
    """Test finding PIDs on Linux with successful lsof."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("1234\n5678\n", "")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    pids = find_pids_on_port(8080)

    assert pids == [1234, 5678]
    mock_popen.assert_called_once()
    assert "lsof" in mock_popen.call_args[0][0]


@patch("launcher.utils.platform.system", return_value="Darwin")
@patch("launcher.utils.subprocess.Popen")
def test_find_pids_on_port_darwin_success(mock_popen, mock_platform):
    """Test finding PIDs on macOS."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("9999\n", "")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    pids = find_pids_on_port(3000)

    assert pids == [9999]


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.Popen")
def test_find_pids_on_port_lsof_not_found(mock_popen, mock_platform):
    """Test handling lsof command not found."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("", "command not found")
    mock_process.returncode = 127
    mock_popen.return_value = mock_process

    pids = find_pids_on_port(8080)

    # Should return empty list and log error
    assert pids == []


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.Popen")
def test_find_pids_on_port_lsof_error(mock_popen, mock_platform):
    """Test handling lsof command error."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("", "Permission denied")
    mock_process.returncode = 2  # Not 0 or 1
    mock_popen.return_value = mock_process

    pids = find_pids_on_port(8080)

    # Should return empty list and log warning
    assert pids == []


@patch("launcher.utils.platform.system", return_value="Windows")
@patch("launcher.utils.subprocess.Popen")
def test_find_pids_on_port_windows_success(mock_popen, mock_platform):
    """Test finding PIDs on Windows with netstat."""
    netstat_output = (
        "TCP    0.0.0.0:8080           0.0.0.0:0              LISTENING       1234\n"
        "TCP    [::]:8080              [::]:0                 LISTENING       1234\n"
    )
    mock_process = MagicMock()
    mock_process.communicate.return_value = (netstat_output, "")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    pids = find_pids_on_port(8080)

    # Should find PID 1234 (deduplicated)
    assert pids == [1234]


@patch("launcher.utils.platform.system", return_value="Windows")
@patch("launcher.utils.subprocess.Popen")
def test_find_pids_on_port_windows_error(mock_popen, mock_platform):
    """Test handling Windows netstat error."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("", "Access denied")
    mock_process.returncode = 2  # Not 0 or 1
    mock_popen.return_value = mock_process

    pids = find_pids_on_port(8080)

    assert pids == []


@patch("launcher.utils.platform.system", return_value="FreeBSD")
def test_find_pids_on_port_unsupported_platform(mock_platform):
    """Test unsupported operating system."""
    pids = find_pids_on_port(8080)

    # Should return empty list and log warning
    assert pids == []


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.Popen")
def test_find_pids_on_port_timeout(mock_popen, mock_platform):
    """Test subprocess timeout handling."""
    mock_process = MagicMock()
    mock_process.communicate.side_effect = subprocess.TimeoutExpired("lsof", 5)
    mock_popen.return_value = mock_process

    pids = find_pids_on_port(8080)

    assert pids == []


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.Popen")
def test_find_pids_on_port_filenotfounderror(mock_popen, mock_platform):
    """Test FileNotFoundError handling."""
    mock_popen.side_effect = FileNotFoundError()

    pids = find_pids_on_port(8080)

    assert pids == []


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.Popen")
def test_find_pids_on_port_generic_exception(mock_popen, mock_platform):
    """Test generic exception handling."""
    mock_popen.side_effect = RuntimeError("Unexpected error")

    pids = find_pids_on_port(8080)

    assert pids == []


# ==================== kill_process_interactive TESTS ====================


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.run")
def test_kill_process_linux_sigterm_success(mock_run, mock_platform):
    """Test successful SIGTERM on Linux."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    success = kill_process_interactive(1234)

    assert success is True
    # Should call kill (SIGTERM)
    assert mock_run.call_count == 1
    assert "kill 1234" in mock_run.call_args[0][0]


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.run")
def test_kill_process_linux_sigterm_fail_sigkill_success(mock_run, mock_platform):
    """Test SIGTERM failure, then SIGKILL success on Linux."""
    # First call (SIGTERM) fails, second call (SIGKILL) succeeds
    mock_result_term = MagicMock()
    mock_result_term.returncode = 1
    mock_result_term.stdout = ""
    mock_result_term.stderr = "No such process"

    mock_result_kill = MagicMock()
    mock_result_kill.returncode = 0
    mock_result_kill.stdout = ""
    mock_result_kill.stderr = ""

    mock_run.side_effect = [mock_result_term, mock_result_kill]

    success = kill_process_interactive(1234)

    assert success is True
    assert mock_run.call_count == 2
    # First: kill, Second: kill -9
    assert "kill 1234" in mock_run.call_args_list[0][0][0]
    assert "kill -9 1234" in mock_run.call_args_list[1][0][0]


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.run")
def test_kill_process_linux_both_fail(mock_run, mock_platform):
    """Test both SIGTERM and SIGKILL failure on Linux."""
    mock_result_fail = MagicMock()
    mock_result_fail.returncode = 1
    mock_result_fail.stdout = ""
    mock_result_fail.stderr = "Permission denied"

    mock_run.return_value = mock_result_fail

    success = kill_process_interactive(1234)

    assert success is False
    assert mock_run.call_count == 2


@patch("launcher.utils.platform.system", return_value="Darwin")
@patch("launcher.utils.subprocess.run")
def test_kill_process_darwin_success(mock_run, mock_platform):
    """Test successful kill on macOS."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    success = kill_process_interactive(5678)

    assert success is True


@patch("launcher.utils.platform.system", return_value="Windows")
@patch("launcher.utils.subprocess.run")
def test_kill_process_windows_success(mock_run, mock_platform):
    """Test successful taskkill on Windows."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "SUCCESS: The process with PID 1234 has been terminated."
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    success = kill_process_interactive(1234)

    assert success is True
    assert "taskkill" in mock_run.call_args[0][0]


@patch("launcher.utils.platform.system", return_value="Windows")
@patch("launcher.utils.subprocess.run")
def test_kill_process_windows_process_not_found(mock_run, mock_platform):
    """Test Windows taskkill when process not found (treated as success)."""
    mock_result = MagicMock()
    mock_result.returncode = 128
    mock_result.stdout = ""
    mock_result.stderr = "ERROR: The process could not find process 1234"
    mock_run.return_value = mock_result

    success = kill_process_interactive(1234)

    # Should treat as success (port is now available)
    assert success is True


@patch("launcher.utils.platform.system", return_value="Windows")
@patch("launcher.utils.subprocess.run")
def test_kill_process_windows_failure(mock_run, mock_platform):
    """Test Windows taskkill failure."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Access denied"
    mock_run.return_value = mock_result

    success = kill_process_interactive(1234)

    assert success is False


@patch("launcher.utils.platform.system", return_value="SunOS")
def test_kill_process_unsupported_platform(mock_platform):
    """Test unsupported platform warning."""
    success = kill_process_interactive(1234)

    assert success is False


@patch("launcher.utils.platform.system", return_value="Linux")
@patch("launcher.utils.subprocess.run")
def test_kill_process_exception(mock_run, mock_platform):
    """Test exception during kill."""
    mock_run.side_effect = RuntimeError("Unexpected error")

    success = kill_process_interactive(1234)

    assert success is False


# ==================== input_with_timeout TESTS ====================


@patch("launcher.utils.sys.platform", "win32")
@patch("launcher.utils.sys.stdin")
def test_input_with_timeout_windows_success(mock_stdin):
    """Test timed input on Windows with user input."""
    from typing import List, Optional

    # Create a container that will be modified by the thread
    user_input_container: List[Optional[str]] = [None]

    def fake_get_input():
        user_input_container[0] = "user input"

    mock_stdin.readline.return_value = "user input\n"

    # Patch the thread to execute immediately instead of running async
    with (
        patch("builtins.print"),
        patch("launcher.utils.threading.Thread") as mock_thread_class,
    ):
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False

        # Simulate thread execution by calling target immediately
        def start_side_effect():
            target = mock_thread_class.call_args[1]["target"]
            target()

        mock_thread.start.side_effect = start_side_effect
        mock_thread_class.return_value = mock_thread

        result = input_with_timeout("Enter value: ", timeout_seconds=5)

    assert result == "user input"


@patch("launcher.utils.sys.platform", "win32")
@patch("launcher.utils.threading.Thread")
def test_input_with_timeout_windows_timeout(mock_thread_class):
    """Test timed input on Windows with timeout."""
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True  # Timeout occurred
    mock_thread_class.return_value = mock_thread

    with patch("builtins.print"):
        result = input_with_timeout("Enter value: ", timeout_seconds=2)

    assert result == ""


@patch("launcher.utils.sys.platform", "win32")
@patch("launcher.utils.sys.stdin")
@patch("launcher.utils.threading.Thread")
def test_input_with_timeout_windows_exception(mock_thread_class, mock_stdin):
    """Test timed input on Windows with exception during readline (covers lines 168-169)."""
    mock_stdin.readline.side_effect = IOError("Read error")

    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = False

    # Simulate thread execution by calling target immediately (like success test)
    def start_side_effect():
        target = mock_thread_class.call_args[1]["target"]
        target()  # This will trigger the IOError, hitting except block (lines 168-169)

    mock_thread.start.side_effect = start_side_effect
    mock_thread_class.return_value = mock_thread

    with patch("builtins.print"):
        result = input_with_timeout("Enter value: ", timeout_seconds=5)

    # Should return empty string from exception handler (line 169)
    assert result == ""


@patch("launcher.utils.sys.platform", "linux")
@patch("launcher.utils.select.select")
@patch("launcher.utils.sys.stdin")
def test_input_with_timeout_linux_success(mock_stdin, mock_select):
    """Test timed input on Linux with user input."""
    mock_select.return_value = ([mock_stdin], [], [])
    mock_stdin.readline.return_value = "linux input\n"

    with patch("builtins.print"):
        result = input_with_timeout("Enter value: ", timeout_seconds=5)

    assert result == "linux input"
    mock_select.assert_called_once_with([mock_stdin], [], [], 5)


@patch("launcher.utils.sys.platform", "linux")
@patch("launcher.utils.select.select")
def test_input_with_timeout_linux_timeout(mock_select):
    """Test timed input on Linux with timeout."""
    mock_select.return_value = ([], [], [])  # No readable FDs = timeout

    with patch("builtins.print"):
        result = input_with_timeout("Enter value: ", timeout_seconds=2)

    assert result == ""


# ==================== get_proxy_from_gsettings TESTS ====================


@patch("launcher.utils.subprocess.run")
def test_get_proxy_from_gsettings_manual_http(mock_run):
    """Test retrieving HTTP proxy from gsettings."""

    # Mock gsettings responses
    def run_side_effect(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0

        # cmd is a list like ['gsettings', 'get', 'org.gnome.system.proxy', 'mode']
        cmd_str = " ".join(cmd)

        if "mode" in cmd_str:
            result.stdout = "'manual'"
        elif "http" in cmd_str and "host" in cmd_str:
            result.stdout = "'proxy.example.com'"
        elif "http" in cmd_str and "port" in cmd_str:
            result.stdout = "8080"
        else:
            result.stdout = "''"

        return result

    mock_run.side_effect = run_side_effect

    proxy = get_proxy_from_gsettings()

    assert proxy == "http://proxy.example.com:8080"


@patch("launcher.utils.subprocess.run")
def test_get_proxy_from_gsettings_manual_https(mock_run):
    """Test retrieving HTTPS proxy from gsettings (HTTP not set)."""

    # Mock gsettings responses
    def run_side_effect(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0

        # cmd is a list like ['gsettings', 'get', ...]
        cmd_str = " ".join(cmd)

        if "mode" in cmd_str:
            result.stdout = "'manual'"
        elif "https" in cmd_str and "host" in cmd_str:
            result.stdout = "'secure.proxy.com'"
        elif "https" in cmd_str and "port" in cmd_str:
            result.stdout = "8443"
        else:
            result.stdout = "''"  # HTTP is empty

        return result

    mock_run.side_effect = run_side_effect

    proxy = get_proxy_from_gsettings()

    assert proxy == "http://secure.proxy.com:8443"


@patch("launcher.utils.subprocess.run")
def test_get_proxy_from_gsettings_no_proxy(mock_run):
    """Test gsettings with no proxy configured."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = "'none'"
    mock_run.return_value = result

    proxy = get_proxy_from_gsettings()

    assert proxy is None


@patch("launcher.utils.subprocess.run")
def test_get_proxy_from_gsettings_empty_values(mock_run):
    """Test gsettings with empty/null proxy values."""

    def run_side_effect(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0

        cmd_str = " ".join(cmd)

        if "mode" in cmd_str:
            result.stdout = "'manual'"
        else:
            result.stdout = "@as []"  # Empty array representation

        return result

    mock_run.side_effect = run_side_effect

    proxy = get_proxy_from_gsettings()

    assert proxy is None


@patch("launcher.utils.subprocess.run")
def test_get_proxy_from_gsettings_invalid_port(mock_run):
    """Test gsettings with invalid port value."""

    def run_side_effect(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0

        cmd_str = " ".join(cmd)

        if "mode" in cmd_str:
            result.stdout = "'manual'"
        elif "host" in cmd_str:
            result.stdout = "'proxy.com'"
        elif "port" in cmd_str:
            result.stdout = "not_a_number"
        else:
            result.stdout = "''"

        return result

    mock_run.side_effect = run_side_effect

    proxy = get_proxy_from_gsettings()

    # Should return None (ValueError caught)
    assert proxy is None


@patch("launcher.utils.subprocess.run")
def test_get_proxy_from_gsettings_zero_port(mock_run):
    """Test gsettings with zero port (invalid)."""

    def run_side_effect(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0

        cmd_str = " ".join(cmd)

        if "mode" in cmd_str:
            result.stdout = "'manual'"
        elif "host" in cmd_str:
            result.stdout = "'proxy.com'"
        elif "port" in cmd_str:
            result.stdout = "0"  # Invalid port
        else:
            result.stdout = "''"

        return result

    mock_run.side_effect = run_side_effect

    proxy = get_proxy_from_gsettings()

    assert proxy is None


@patch("launcher.utils.subprocess.run")
def test_get_proxy_from_gsettings_command_failure(mock_run):
    """Test gsettings command failure."""
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    mock_run.return_value = result

    proxy = get_proxy_from_gsettings()

    assert proxy is None


@patch("launcher.utils.subprocess.run")
def test_get_proxy_from_gsettings_timeout(mock_run):
    """Test gsettings command timeout."""
    mock_run.side_effect = subprocess.TimeoutExpired("gsettings", 1)

    proxy = get_proxy_from_gsettings()

    assert proxy is None


@patch("launcher.utils.subprocess.run")
def test_get_proxy_from_gsettings_exception(mock_run):
    """Test gsettings generic exception."""
    mock_run.side_effect = RuntimeError("Unexpected error")

    proxy = get_proxy_from_gsettings()

    assert proxy is None
