import logging
import platform
import select
import socket
import subprocess
import sys
import threading
from typing import List, Optional

logger = logging.getLogger("CamoufoxLauncher")


def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return False
        except OSError:
            return True
        except Exception as e:
            logger.warning(f"Unknown error checking port {port} (host {host}): {e}")
            return True


def find_pids_on_port(port: int) -> List[int]:
    pids: List[int] = []
    system_platform = platform.system()
    command = ""
    try:
        if system_platform == "Linux" or system_platform == "Darwin":
            command = f"lsof -ti :{port} -sTCP:LISTEN"
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                close_fds=True,
            )
            stdout, stderr = process.communicate(timeout=5)
            if process.returncode == 0 and stdout:
                pids = [int(pid) for pid in stdout.strip().split("\n") if pid.isdigit()]
            elif process.returncode != 0 and (
                "command not found" in stderr.lower() or "未找到命令" in stderr
            ):
                logger.error("Command 'lsof' not found. Please ensure it is installed.")
            elif process.returncode not in [0, 1]:  # lsof returns 1 when not found
                logger.warning(
                    f"Failed to execute lsof command (return code {process.returncode}): {stderr.strip()}"
                )
        elif system_platform == "Windows":
            command = f'netstat -ano -p TCP | findstr "LISTENING" | findstr ":{port} "'
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(timeout=10)
            if process.returncode == 0 and stdout:
                for line in stdout.strip().split("\n"):
                    parts = line.split()
                    if (
                        len(parts) >= 4
                        and parts[0].upper() == "TCP"
                        and f":{port}" in parts[1]
                    ):
                        if parts[-1].isdigit():
                            pids.append(int(parts[-1]))
                pids = list(set(pids))  # Deduplicate
            elif process.returncode not in [0, 1]:  # findstr returns 1 when not found
                logger.warning(
                    f"Failed to execute netstat/findstr command (return code {process.returncode}): {stderr.strip()}"
                )
        else:
            logger.warning(
                f"Unsupported operating system '{system_platform}' for finding processes on port."
            )
    except FileNotFoundError:
        cmd_name = command.split()[0] if command else "required tool"
        logger.error(f"Command '{cmd_name}' not found.")
    except subprocess.TimeoutExpired:
        logger.error(f"Command '{command}' timed out.")
    except Exception as e:
        logger.error(f"Error finding processes on port {port}: {e}", exc_info=True)
    return pids


def kill_process_interactive(pid: int) -> bool:
    system_platform = platform.system()
    success = False
    logger.info(f"Attempting to terminate process PID: {pid}...")
    try:
        if system_platform == "Linux" or system_platform == "Darwin":
            result_term = subprocess.run(
                f"kill {pid}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result_term.returncode == 0:
                logger.info(f"SIGTERM signal sent to PID {pid}.")
                success = True
            else:
                logger.warning(
                    f"    PID {pid} SIGTERM failed: {result_term.stderr.strip() or result_term.stdout.strip()}. Trying SIGKILL..."
                )
                result_kill = subprocess.run(
                    f"kill -9 {pid}",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if result_kill.returncode == 0:
                    logger.info(f"SIGKILL signal sent to PID {pid}.")
                    success = True
                else:
                    logger.error(
                        f"    ✗ PID {pid} SIGKILL failed: {result_kill.stderr.strip() or result_kill.stdout.strip()}."
                    )
        elif system_platform == "Windows":
            command_desc = f"taskkill /PID {pid} /T /F"
            result = subprocess.run(
                command_desc,
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            output = result.stdout.strip()
            error_output = result.stderr.strip()
            if result.returncode == 0 and (
                "SUCCESS" in output.upper() or "成功" in output
            ):
                logger.info(f"PID {pid} terminated via taskkill /F.")
                success = True
            elif (
                "could not find process" in error_output.lower()
                or "找不到" in error_output
            ):  # Process may have already exited
                logger.info(
                    f"PID {pid} not found when executing taskkill (may have exited)."
                )
                success = True  # Treat as success since goal is port availability
            else:
                # Count errors rather than outputting each one
                combined = (error_output + " " + output).strip()
                error_count = combined.count("ERROR:")
                if error_count > 0:
                    logger.warning(
                        f"    PID {pid} taskkill /F: (suppressed {error_count} error messages)"
                    )
                else:
                    logger.warning(f"PID {pid} taskkill /F returned non-zero status")
        else:
            logger.warning(
                f"Unsupported operating system '{system_platform}' for terminating processes."
            )
    except Exception as e:
        logger.error(f"Unexpected error terminating PID {pid}: {e}", exc_info=True)
    return success


def input_with_timeout(prompt_message: str, timeout_seconds: int = 30) -> str:
    print(prompt_message, end="", flush=True)
    if sys.platform == "win32":
        user_input_container: List[Optional[str]] = [None]

        def get_input_in_thread():
            try:
                user_input_container[0] = sys.stdin.readline().strip()
            except Exception:
                user_input_container[0] = ""  # Return empty string on error

        input_thread = threading.Thread(target=get_input_in_thread, daemon=True)
        input_thread.start()
        input_thread.join(timeout=timeout_seconds)
        if input_thread.is_alive():
            print("\nInput timed out. Using default value.", flush=True)
            return ""
        return user_input_container[0] if user_input_container[0] is not None else ""
    else:  # Linux/macOS
        readable_fds, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
        if readable_fds:
            return sys.stdin.readline().strip()
        else:
            print("\nInput timed out. Using default value.", flush=True)
            return ""


def get_proxy_from_gsettings() -> Optional[str]:
    """
    Retrieves the proxy settings from GSettings on Linux systems.
    Returns a proxy string like "http://host:port" or None.
    """

    def _run_gsettings_command(command_parts: List[str]) -> Optional[str]:
        """Helper function to run gsettings command and return cleaned string output."""
        try:
            process_result = subprocess.run(
                command_parts,
                capture_output=True,
                text=True,
                check=False,  # Do not raise CalledProcessError for non-zero exit codes
                timeout=1,  # Timeout for the subprocess call
            )
            if process_result.returncode == 0:
                value = process_result.stdout.strip()
                if value.startswith("'") and value.endswith(
                    "'"
                ):  # Remove surrounding single quotes
                    value = value[1:-1]

                # If after stripping quotes, value is empty, or it's a gsettings "empty" representation
                if not value or value == "''" or value == "@as []" or value == "[]":
                    return None
                return value
            else:
                return None
        except subprocess.TimeoutExpired:
            return None
        except Exception:  # Broad exception as per pseudocode
            return None

    proxy_mode = _run_gsettings_command(
        ["gsettings", "get", "org.gnome.system.proxy", "mode"]
    )

    if proxy_mode == "manual":
        # Try HTTP proxy first
        http_host = _run_gsettings_command(
            ["gsettings", "get", "org.gnome.system.proxy.http", "host"]
        )
        http_port_str = _run_gsettings_command(
            ["gsettings", "get", "org.gnome.system.proxy.http", "port"]
        )

        if http_host and http_port_str:
            try:
                http_port = int(http_port_str)
                if http_port > 0:
                    return f"http://{http_host}:{http_port}"
            except ValueError:
                pass  # Continue to HTTPS

        # Try HTTPS proxy if HTTP not found or invalid
        https_host = _run_gsettings_command(
            ["gsettings", "get", "org.gnome.system.proxy.https", "host"]
        )
        https_port_str = _run_gsettings_command(
            ["gsettings", "get", "org.gnome.system.proxy.https", "port"]
        )

        if https_host and https_port_str:
            try:
                https_port = int(https_port_str)
                if https_port > 0:
                    # Note: Even for HTTPS proxy settings, the scheme for Playwright/requests is usually http://
                    return f"http://{https_host}:{https_port}"
            except ValueError:
                pass

    return None
