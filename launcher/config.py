import argparse
import os
import re
import sys
from typing import Dict, Optional

from launcher.utils import get_proxy_from_gsettings

# --- Configuration Constants ---
PYTHON_EXECUTABLE = sys.executable
ENDPOINT_CAPTURE_TIMEOUT = int(os.environ.get("ENDPOINT_CAPTURE_TIMEOUT", "45"))
DEFAULT_SERVER_PORT = int(os.environ.get("DEFAULT_FASTAPI_PORT", "2048"))
DEFAULT_CAMOUFOX_PORT = int(os.environ.get("DEFAULT_CAMOUFOX_PORT", "9222"))
DEFAULT_STREAM_PORT = int(os.environ.get("STREAM_PORT", "3120"))
DEFAULT_HELPER_ENDPOINT = os.environ.get("GUI_DEFAULT_HELPER_ENDPOINT", "")
DEFAULT_AUTH_SAVE_TIMEOUT = int(os.environ.get("AUTH_SAVE_TIMEOUT", "30"))
DEFAULT_SERVER_LOG_LEVEL = os.environ.get("SERVER_LOG_LEVEL", "INFO")
AUTH_PROFILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "auth_profiles"
)
ACTIVE_AUTH_DIR = os.path.join(AUTH_PROFILES_DIR, "active")
SAVED_AUTH_DIR = os.path.join(AUTH_PROFILES_DIR, "saved")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LAUNCHER_LOG_FILE_PATH = os.path.join(LOG_DIR, "launch_app.log")
DIRECT_LAUNCH = os.environ.get("DIRECT_LAUNCH", "").lower() in ("true", "1", "yes")

ws_regex = re.compile(r"(ws://\S+)")


def determine_proxy_configuration(
    internal_camoufox_proxy_arg: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Unified proxy configuration determination function.
    Priority: Command-line arguments > Environment variables > System settings.
    """
    result = {"camoufox_proxy": None, "stream_proxy": None, "source": "No Proxy"}

    if internal_camoufox_proxy_arg is not None:
        if internal_camoufox_proxy_arg.strip():
            result["camoufox_proxy"] = internal_camoufox_proxy_arg.strip()
            result["stream_proxy"] = internal_camoufox_proxy_arg.strip()
            result["source"] = (
                f"CLI argument --internal-camoufox-proxy: {internal_camoufox_proxy_arg.strip()}"
            )
        else:
            result["source"] = (
                "CLI argument --internal-camoufox-proxy='' (Explicitly disabled)"
            )
        return result

    unified_proxy = os.environ.get("UNIFIED_PROXY_CONFIG")
    if unified_proxy:
        result["camoufox_proxy"] = unified_proxy
        result["stream_proxy"] = unified_proxy
        result["source"] = f"Environment variable UNIFIED_PROXY_CONFIG: {unified_proxy}"
        return result

    http_proxy = os.environ.get("HTTP_PROXY")
    if http_proxy:
        result["camoufox_proxy"] = http_proxy
        result["stream_proxy"] = http_proxy
        result["source"] = f"Environment variable HTTP_PROXY: {http_proxy}"
        return result

    https_proxy = os.environ.get("HTTPS_PROXY")
    if https_proxy:
        result["camoufox_proxy"] = https_proxy
        result["stream_proxy"] = https_proxy
        result["source"] = f"Environment variable HTTPS_PROXY: {https_proxy}"
        return result

    if sys.platform.startswith("linux"):
        gsettings_proxy = get_proxy_from_gsettings()
        if gsettings_proxy:
            result["camoufox_proxy"] = gsettings_proxy
            result["stream_proxy"] = gsettings_proxy
            result["source"] = f"gsettings System Proxy: {gsettings_proxy}"
            return result

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launcher for Camoufox browser simulation and FastAPI proxy server.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Internal parameters
    parser.add_argument(
        "--internal-launch-mode",
        type=str,
        choices=["debug", "headless", "virtual_headless"],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--internal-auth-file", type=str, default=None, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--internal-camoufox-port",
        type=int,
        default=DEFAULT_CAMOUFOX_PORT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--internal-camoufox-proxy", type=str, default=None, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--internal-camoufox-os", type=str, default="random", help=argparse.SUPPRESS
    )

    # User-visible parameters
    parser.add_argument(
        "--server-port",
        type=int,
        default=DEFAULT_SERVER_PORT,
        help=f"FastAPI server listening port (Default: {DEFAULT_SERVER_PORT})",
    )
    parser.add_argument(
        "--stream-port",
        type=int,
        default=DEFAULT_STREAM_PORT,
        help=f"Streaming proxy server port. Provide 0 to disable. Default: {DEFAULT_STREAM_PORT}",
    )
    parser.add_argument(
        "--helper",
        type=str,
        default=DEFAULT_HELPER_ENDPOINT,
        help=f"Helper server getStreamResponse endpoint. Provide empty string to disable. Default: {DEFAULT_HELPER_ENDPOINT}",
    )
    parser.add_argument(
        "--camoufox-debug-port",
        type=int,
        default=DEFAULT_CAMOUFOX_PORT,
        help=f"Internal Camoufox instance debugging port (Default: {DEFAULT_CAMOUFOX_PORT})",
    )

    mode_selection_group = parser.add_mutually_exclusive_group()
    mode_selection_group.add_argument(
        "--debug",
        action="store_true",
        help="Start in debug mode (browser visible, interactive auth allowed)",
    )
    mode_selection_group.add_argument(
        "--headless",
        action="store_true",
        help="Start in headless mode (no browser UI, requires pre-saved auth)",
    )
    mode_selection_group.add_argument(
        "--virtual-display",
        action="store_true",
        help="Start in headless mode with virtual display (Xvfb, Linux only)",
    )

    parser.add_argument(
        "--active-auth-json",
        type=str,
        default=None,
        help="[Optional] Path to active authentication JSON file.",
    )

    debug_logs_default = os.environ.get("DEBUG_LOGS_ENABLED", "false").lower() == "true"
    trace_logs_default = os.environ.get("TRACE_LOGS_ENABLED", "false").lower() == "true"
    auto_save_auth_default = os.environ.get("AUTO_SAVE_AUTH", "false").lower() == "true"

    parser.add_argument(
        "--auto-save-auth",
        action="store_true",
        help="[Debug Mode] Automatically prompt and save new auth state after successful login.",
    )
    parser.add_argument(
        "--save-auth-as",
        type=str,
        default=None,
        help="[Debug Mode] Filename for the new auth file (without .json extension).",
    )
    parser.add_argument(
        "--auth-save-timeout",
        type=int,
        default=DEFAULT_AUTH_SAVE_TIMEOUT,
        help=f"[Debug Mode] Timeout in seconds to wait for auth save. Default: {DEFAULT_AUTH_SAVE_TIMEOUT}",
    )
    parser.add_argument(
        "--exit-on-auth-save",
        action="store_true",
        help="[Debug Mode] Automatically close the launcher and processes after saving new auth file.",
    )

    parser.add_argument(
        "--server-log-level",
        type=str,
        default=DEFAULT_SERVER_LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=f"Log level for server.py. Default: {DEFAULT_SERVER_LOG_LEVEL}",
    )
    parser.add_argument(
        "--server-redirect-print",
        action="store_true",
        help="Redirect server.py print output to its logging system.",
    )
    parser.add_argument(
        "--debug-logs",
        action="store_true",
        default=debug_logs_default,
        help="Enable internal DEBUG logs for server.py (DEBUG_LOGS_ENABLED env).",
    )
    parser.add_argument(
        "--trace-logs",
        action="store_true",
        default=trace_logs_default,
        help="Enable internal TRACE logs for server.py (TRACE_LOGS_ENABLED env).",
    )
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="Skip frontend build check (for environments without Node.js/npm).",
    )

    args = parser.parse_args()

    # Mark which arguments were explicitly set via CLI
    args.debug_logs_from_cli = "--debug-logs" in sys.argv
    args.trace_logs_from_cli = "--trace-logs" in sys.argv
    args.auto_save_auth_from_cli = "--auto-save-auth" in sys.argv
    args.server_redirect_print_from_cli = "--server-redirect-print" in sys.argv

    # Use environment variables if not set via CLI
    if not args.debug_logs_from_cli:
        args.debug_logs = debug_logs_default
    if not args.trace_logs_from_cli:
        args.trace_logs = trace_logs_default
    if not args.auto_save_auth_from_cli:
        args.auto_save_auth = auto_save_auth_default

    return args
