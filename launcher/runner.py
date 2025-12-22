import atexit
import json
import logging
import os
import platform
import re
import shutil
import signal
import sys
import threading
import time
from typing import Optional

import uvicorn

from launcher.checks import check_dependencies, ensure_auth_dirs_exist
from launcher.config import (
    ACTIVE_AUTH_DIR,
    DIRECT_LAUNCH,
    SAVED_AUTH_DIR,
    determine_proxy_configuration,
    parse_args,
)
from launcher.internal import run_internal_camoufox
from launcher.logging_setup import setup_launcher_logging
from launcher.process import CamoufoxProcessManager
from launcher.utils import (
    find_pids_on_port,
    input_with_timeout,
    is_port_in_use,
    kill_process_interactive,
)

# Try to import launch_server (used for internal launch mode)
try:
    from camoufox import DefaultAddons
    from camoufox.server import launch_server
except ImportError:
    launch_server = None
    DefaultAddons = None

# Import server app
try:
    from server import app
except ImportError:
    app = None

logger = logging.getLogger("CamoufoxLauncher")


class Launcher:  # pragma: no cover
    def __init__(self):
        self.args = parse_args()
        self.camoufox_manager = CamoufoxProcessManager()
        atexit.register(self.camoufox_manager.cleanup)
        self.final_launch_mode: str = "headless"
        self.effective_active_auth_json_path: Optional[str] = None
        self.simulated_os_for_camoufox = "linux"

    def run(self):
        is_internal_call = self.args.internal_launch_mode is not None

        if is_internal_call:
            if self.args.internal_launch_mode:
                run_internal_camoufox(self.args, launch_server, DefaultAddons)
            return

        log_level_str = os.environ.get("SERVER_LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        setup_launcher_logging(log_level=log_level)
        logger.info("[System] Launcher started")
        ensure_auth_dirs_exist()
        check_dependencies(launch_server is not None, DefaultAddons is not None)

        # Automatically check and rebuild frontend if needed
        from launcher.frontend_build import ensure_frontend_built

        ensure_frontend_built(skip_build=self.args.skip_frontend_build)

        self._determine_launch_mode()

        if not DIRECT_LAUNCH:
            self._handle_auth_file_selection()
        self._check_xvfb()
        self._check_server_port()

        logger.debug("[Init] Step 3: Preparing and starting Camoufox...")
        self._resolve_auth_file_path()

        current_system_for_camoufox = platform.system()
        if current_system_for_camoufox == "Linux":
            self.simulated_os_for_camoufox = "linux"
        elif current_system_for_camoufox == "Windows":
            self.simulated_os_for_camoufox = "windows"
        elif current_system_for_camoufox == "Darwin":
            self.simulated_os_for_camoufox = "macos"
        else:
            logger.warning(
                f"Unrecognized system '{current_system_for_camoufox}'. Defaulting Camoufox OS simulation to: {self.simulated_os_for_camoufox}"
            )

        mode_str = self.final_launch_mode.replace("_", " ").capitalize()
        auth_name = (
            os.path.basename(self.effective_active_auth_json_path)
            if self.effective_active_auth_json_path
            else "None"
        )
        logger.info(
            f"[System] Configuration ready | Port: {self.args.server_port} | Mode: {mode_str} | Auth: {auth_name}"
        )

        captured_ws_endpoint = self.camoufox_manager.start(
            self.final_launch_mode,
            self.effective_active_auth_json_path,
            self.simulated_os_for_camoufox,
            self.args,
        )

        self._setup_helper_mode()
        self._setup_environment_variables(captured_ws_endpoint)
        self._start_server()

        logger.info("Launcher main logic completed")

    def _determine_launch_mode(self):
        if self.args.debug:
            self.final_launch_mode = "debug"
        elif self.args.headless:
            self.final_launch_mode = "headless"
        elif self.args.virtual_display:
            self.final_launch_mode = "virtual_headless"
            if platform.system() != "Linux":
                logger.warning(
                    "--virtual-display is designed for Linux. Behavior on other systems may be unpredictable."
                )
        else:
            env_launch_mode = os.environ.get("LAUNCH_MODE", "").lower()
            default_mode_from_env = None
            default_interactive_choice = "1"

            if env_launch_mode == "headless":
                default_mode_from_env = "headless"
                default_interactive_choice = "1"
            elif env_launch_mode == "debug" or env_launch_mode == "normal":
                default_mode_from_env = "debug"
                default_interactive_choice = "2"
            elif env_launch_mode in ("virtual_display", "virtual_headless"):
                default_mode_from_env = "virtual_headless"
                default_interactive_choice = (
                    "3" if platform.system() == "Linux" else "1"
                )

            if DIRECT_LAUNCH:
                self.final_launch_mode = default_mode_from_env or "headless"
                return

            logger.info("--- Select Launch Mode (Not specified via CLI) ---")
            if env_launch_mode and default_mode_from_env:
                logger.info(
                    f"  Default mode from .env: {env_launch_mode} -> {default_mode_from_env}"
                )

            prompt_options_text = "[1] Headless, [2] Debug"
            valid_choices = {"1": "headless", "2": "debug"}

            if platform.system() == "Linux":
                prompt_options_text += ", [3] Headless (Virtual Display Xvfb)"
                valid_choices["3"] = "virtual_headless"

            default_mode_name = valid_choices.get(
                default_interactive_choice, "headless"
            )
            user_mode_choice = (
                input_with_timeout(
                    f"  Enter launch mode ({prompt_options_text}; Default: {default_interactive_choice} {default_mode_name} mode, 15s timeout): ",
                    15,
                )
                or default_interactive_choice
            )

            if user_mode_choice in valid_choices:
                self.final_launch_mode = valid_choices[user_mode_choice]
            else:
                self.final_launch_mode = default_mode_from_env or "headless"
                logger.info(
                    f"Invalid input '{user_mode_choice}', using default: {self.final_launch_mode}"
                )
        logger.debug(f"Selected launch mode: {self.final_launch_mode}")

    def _handle_auth_file_selection(self):
        if self.final_launch_mode == "debug" and not self.args.active_auth_json:
            create_new_auth_choice = (
                input_with_timeout(
                    "  Create and save new auth file? (y/n; Default: n, 15s timeout): ",
                    15,
                )
                .strip()
                .lower()
            )
            if create_new_auth_choice == "y":
                new_auth_filename = ""
                while not new_auth_filename:
                    new_auth_filename_input = input_with_timeout(
                        "  Enter filename to save (without .json, alphanumeric/_-): ",
                        self.args.auth_save_timeout,
                    ).strip()
                    if re.match(r"^[a-zA-Z0-9_-]+$", new_auth_filename_input):
                        new_auth_filename = new_auth_filename_input
                    elif new_auth_filename_input == "":
                        logger.info("Empty input, cancelling new auth creation.")
                        break
                    else:
                        print("Invalid characters, try again.")

                if new_auth_filename:
                    self.args.auto_save_auth = True
                    self.args.auto_save_auth_from_cli = True
                    self.args.save_auth_as = new_auth_filename
                    logger.info(f"Auth will be saved as: {new_auth_filename}.json")
                    if self.effective_active_auth_json_path:
                        self.effective_active_auth_json_path = None
            else:
                logger.info("New auth file will not be created.")

    def _check_xvfb(self):
        if (
            self.final_launch_mode == "virtual_headless"
            and platform.system() == "Linux"
        ):
            if not shutil.which("Xvfb"):
                logger.error("Xvfb not found. Required for virtual display mode.")
                sys.exit(1)

    def _check_server_port(self):
        server_target_port = self.args.server_port
        logger.info(f"--- Step 2: Checking if port {server_target_port} is in use ---")
        port_is_available = False
        uvicorn_bind_host = "0.0.0.0"
        if is_port_in_use(server_target_port, host=uvicorn_bind_host):
            logger.warning(f"Port {server_target_port} is currently in use.")
            pids_on_port = find_pids_on_port(server_target_port)
            if pids_on_port:
                logger.warning(f"PIDs using port {server_target_port}: {pids_on_port}")
                if self.final_launch_mode == "debug":
                    choice = (
                        input_with_timeout(
                            "     Try to kill these processes? (y/n, 15s timeout): ",
                            15,
                        )
                        .strip()
                        .lower()
                    )
                    if choice == "y":
                        all(kill_process_interactive(pid) for pid in pids_on_port)
                        time.sleep(2)
                        if not is_port_in_use(
                            server_target_port, host=uvicorn_bind_host
                        ):
                            logger.info("Port is now available.")
                            port_is_available = True
                        else:
                            logger.error("Port still in use after kill attempt.")
                else:
                    logger.error("Headless mode: will not auto-kill processes.")
            if not port_is_available:
                logger.warning("Continuing anyway, Uvicorn will handle binding.")
        else:
            logger.debug(f"[System] Port {server_target_port} is available")

    def _resolve_auth_file_path(self):
        if self.args.active_auth_json:
            candidate_path = os.path.expanduser(self.args.active_auth_json)
            if os.path.isabs(candidate_path) and os.path.exists(candidate_path):
                self.effective_active_auth_json_path = candidate_path
            else:
                path_rel_to_cwd = os.path.abspath(candidate_path)
                if os.path.exists(path_rel_to_cwd):
                    self.effective_active_auth_json_path = path_rel_to_cwd
                else:
                    path_rel_to_script = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)), candidate_path
                    )
                    if os.path.exists(path_rel_to_script):
                        self.effective_active_auth_json_path = path_rel_to_script
                    elif os.path.sep not in candidate_path:
                        for d in [ACTIVE_AUTH_DIR, SAVED_AUTH_DIR]:
                            p = os.path.join(d, candidate_path)
                            if os.path.exists(p):
                                self.effective_active_auth_json_path = p
                                break

            if self.effective_active_auth_json_path:
                logger.info(f"Using auth file: {self.effective_active_auth_json_path}")
            else:
                logger.error(f"Auth file '{self.args.active_auth_json}' not found.")
                sys.exit(1)
        else:
            if self.final_launch_mode != "debug":
                try:
                    if os.path.exists(ACTIVE_AUTH_DIR):
                        active_json_files = sorted(
                            [
                                f
                                for f in os.listdir(ACTIVE_AUTH_DIR)
                                if f.lower().endswith(".json")
                            ]
                        )
                        if active_json_files:
                            self.effective_active_auth_json_path = os.path.join(
                                ACTIVE_AUTH_DIR, active_json_files[0]
                            )
                except Exception as e:
                    logger.warning(f"Error scanning active auth dir: {e}")

            if self.final_launch_mode == "debug" and not self.args.auto_save_auth:
                available_profiles = []
                for d, label in [
                    (ACTIVE_AUTH_DIR, "active"),
                    (SAVED_AUTH_DIR, "saved"),
                ]:
                    if os.path.exists(d):
                        try:
                            for f in sorted(os.listdir(d)):
                                if f.lower().endswith(".json"):
                                    available_profiles.append(
                                        {
                                            "name": f"{label}/{f}",
                                            "path": os.path.join(d, f),
                                        }
                                    )
                        except OSError:
                            pass

                if available_profiles:
                    available_profiles.sort(key=lambda x: x["name"])
                    if DIRECT_LAUNCH:
                        self.effective_active_auth_json_path = available_profiles[0][
                            "path"
                        ]
                    else:
                        print("-" * 60 + "\nAvailable auth files:")
                        for i, p in enumerate(available_profiles):
                            print(f"{i + 1}: {p['name']}")
                        print("N: None (use current browser state)\n" + "-" * 60)
                        choice = input_with_timeout(
                            "Select number (N/Enter for none, 30s): ", 30
                        )
                        if choice.strip().lower() not in ["n", ""]:
                            try:
                                idx = int(choice.strip()) - 1
                                if 0 <= idx < len(available_profiles):
                                    self.effective_active_auth_json_path = (
                                        available_profiles[idx]["path"]
                                    )
                                    logger.info(
                                        f"Selected: {available_profiles[idx]['name']}"
                                    )
                            except ValueError:
                                pass
                else:
                    logger.info("No auth files found.")
            elif (
                not self.effective_active_auth_json_path
                and not self.args.auto_save_auth
            ):
                logger.error(
                    f"Headless mode error: no auth file found in {ACTIVE_AUTH_DIR}."
                )
                sys.exit(1)

    def _setup_helper_mode(self):
        if self.args.helper:
            logger.info(f"Helper mode enabled, endpoint: {self.args.helper}")
            os.environ["HELPER_ENDPOINT"] = self.args.helper
            if self.effective_active_auth_json_path:
                try:
                    with open(
                        self.effective_active_auth_json_path, "r", encoding="utf-8"
                    ) as f:
                        data = json.load(f)
                        for cookie in data.get("cookies", []):
                            if (
                                cookie.get("name") == "SAPISID"
                                and cookie.get("domain") == ".google.com"
                            ):
                                os.environ["HELPER_SAPISID"] = cookie.get("value", "")
                                break
                except Exception as e:
                    logger.warning(f"Failed to extract SAPISID: {e}")

    def _setup_environment_variables(self, captured_ws_endpoint):
        if not captured_ws_endpoint:
            logger.error("Critical error: WebSocket endpoint not captured.")
            sys.exit(1)

        os.environ["CAMOUFOX_WS_ENDPOINT"] = captured_ws_endpoint
        os.environ["LAUNCH_MODE"] = self.final_launch_mode
        os.environ["SERVER_LOG_LEVEL"] = self.args.server_log_level.upper()

        # Only set these env vars if CLI flags were explicitly provided
        # Otherwise, preserve existing env var values (from .env files)
        if (
            hasattr(self.args, "server_redirect_print_from_cli")
            and self.args.server_redirect_print_from_cli
        ):
            os.environ["SERVER_REDIRECT_PRINT"] = str(
                self.args.server_redirect_print
            ).lower()
        if hasattr(self.args, "debug_logs_from_cli") and self.args.debug_logs_from_cli:
            os.environ["DEBUG_LOGS_ENABLED"] = str(self.args.debug_logs).lower()
        if hasattr(self.args, "trace_logs_from_cli") and self.args.trace_logs_from_cli:
            os.environ["TRACE_LOGS_ENABLED"] = str(self.args.trace_logs).lower()
        if self.effective_active_auth_json_path:
            os.environ["ACTIVE_AUTH_JSON_PATH"] = self.effective_active_auth_json_path
        if (
            self.final_launch_mode == "debug"
            and hasattr(self.args, "auto_save_auth_from_cli")
            and self.args.auto_save_auth_from_cli
        ):
            os.environ["AUTO_SAVE_AUTH"] = str(self.args.auto_save_auth).lower()

        if self.args.save_auth_as:
            os.environ["SAVE_AUTH_FILENAME"] = self.args.save_auth_as
        os.environ["AUTH_SAVE_TIMEOUT"] = str(self.args.auth_save_timeout)
        os.environ["SERVER_PORT_INFO"] = str(self.args.server_port)
        os.environ["STREAM_PORT"] = str(self.args.stream_port)

        proxy_config = determine_proxy_configuration(self.args.internal_camoufox_proxy)
        if proxy_config["stream_proxy"]:
            os.environ["UNIFIED_PROXY_CONFIG"] = proxy_config["stream_proxy"]
            logger.info(f"Unified proxy set: {proxy_config['source']}")

        camoufox_os = self.simulated_os_for_camoufox.lower()
        host_os_map = {"macos": "Darwin", "windows": "Windows", "linux": "Linux"}
        if camoufox_os in host_os_map:
            os.environ["HOST_OS_FOR_SHORTCUT"] = host_os_map[camoufox_os]

    def _start_server(self):
        logger.info(
            f"--- Step 5: Starting integrated FastAPI server on port {self.args.server_port} ---"
        )
        if app is None:
            logger.error("FastAPI app not found.")
            sys.exit(1)

        if not self.args.exit_on_auth_save:
            try:
                uvicorn.run(
                    app, host="0.0.0.0", port=self.args.server_port, log_config=None
                )
            except Exception as e:
                logger.critical(f"Uvicorn error: {e}", exc_info=True)
                sys.exit(1)
        else:
            server_config = uvicorn.Config(
                app, host="0.0.0.0", port=self.args.server_port, log_config=None
            )
            server = uvicorn.Server(server_config)
            stop_watcher = threading.Event()

            def watch_for_saved_auth_and_shutdown():
                os.makedirs(SAVED_AUTH_DIR, exist_ok=True)
                initial_files = set(os.listdir(SAVED_AUTH_DIR))
                while not stop_watcher.is_set():
                    try:
                        new_files = set(os.listdir(SAVED_AUTH_DIR)) - initial_files
                        if new_files:
                            logger.info(
                                f"New auth file detected: {', '.join(new_files)}. Shutting down in 3s..."
                            )
                            time.sleep(3)
                            server.should_exit = True
                            break
                    except Exception:
                        pass
                    if stop_watcher.wait(1):
                        break

            watcher_thread = threading.Thread(target=watch_for_saved_auth_and_shutdown)
            try:
                watcher_thread.start()
                server.run()
            except Exception as e:
                logger.critical(f"Uvicorn error: {e}", exc_info=True)
                sys.exit(1)
            finally:
                stop_watcher.set()
                if watcher_thread.is_alive():
                    watcher_thread.join()


def signal_handler(sig, frame):
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def cleanup():
    pass
