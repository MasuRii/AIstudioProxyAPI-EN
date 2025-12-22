import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from typing import Optional

from launcher.config import ENDPOINT_CAPTURE_TIMEOUT, PYTHON_EXECUTABLE, ws_regex

logger = logging.getLogger("CamoufoxLauncher")


def _enqueue_output(
    stream, stream_name, output_queue, process_pid_for_log="<unknown PID>"
):
    log_prefix = f"[ReadThread-{stream_name}-PID:{process_pid_for_log}]"
    try:
        for line_bytes in iter(stream.readline, b""):
            if not line_bytes:
                break
            try:
                line_str = line_bytes.decode("utf-8", errors="replace")
                output_queue.put((stream_name, line_str))
            except Exception as decode_err:
                logger.warning(
                    f"{log_prefix} Decode error: {decode_err}. Raw data (first 100 bytes): {line_bytes[:100]}"
                )
                output_queue.put(
                    (
                        stream_name,
                        f"[Decode error: {decode_err}] {line_bytes[:100]}...\n",
                    )
                )
    except ValueError:
        logger.debug(f"{log_prefix} ValueError (stream may be closed).")
    except Exception as e:
        logger.error(
            f"{log_prefix} Unexpected error reading stream: {e}", exc_info=True
        )
    finally:
        output_queue.put((stream_name, None))
        if hasattr(stream, "close") and not stream.closed:
            try:
                stream.close()
            except Exception:
                pass
        logger.debug(f"{log_prefix} Thread exiting.")


def build_launch_command(
    final_launch_mode: str,
    effective_active_auth_json_path: Optional[str],
    simulated_os_for_camoufox: str,
    camoufox_debug_port: int,
    internal_camoufox_proxy: Optional[str],
) -> list[str]:
    """
    Build the command-line arguments for launching the internal Camoufox process.

    This is a pure function (no I/O) that can be easily unit tested.

    Args:
        final_launch_mode: The launch mode (headless, virtual_headless, debug)
        effective_active_auth_json_path: Path to auth file, or None
        simulated_os_for_camoufox: OS to simulate (linux, windows, macos)
        camoufox_debug_port: Debug port for Camoufox
        internal_camoufox_proxy: Proxy configuration, or None

    Returns:
        List of command-line arguments for subprocess.Popen
    """
    cmd = [
        PYTHON_EXECUTABLE,
        "-u",
        sys.argv[0],
        "--internal-launch-mode",
        final_launch_mode,
    ]

    if effective_active_auth_json_path:
        cmd.extend(["--internal-auth-file", effective_active_auth_json_path])

    cmd.extend(["--internal-camoufox-os", simulated_os_for_camoufox])
    cmd.extend(["--internal-camoufox-port", str(camoufox_debug_port)])

    if internal_camoufox_proxy is not None:
        cmd.extend(["--internal-camoufox-proxy", internal_camoufox_proxy])

    return cmd


class CamoufoxProcessManager:
    def __init__(self):
        self.camoufox_proc = None
        self.captured_ws_endpoint = None

    def start(
        self,
        final_launch_mode,
        effective_active_auth_json_path,
        simulated_os_for_camoufox,
        args,
    ):
        # Build Camoufox internal launch command (from dev)
        camoufox_internal_cmd_args = build_launch_command(
            final_launch_mode,
            effective_active_auth_json_path,
            simulated_os_for_camoufox,
            args.camoufox_debug_port,
            args.internal_camoufox_proxy,
        )

        camoufox_popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": os.environ.copy(),
        }
        camoufox_popen_kwargs["env"]["PYTHONIOENCODING"] = "utf-8"
        if sys.platform != "win32" and final_launch_mode != "debug":
            camoufox_popen_kwargs["start_new_session"] = True
        elif sys.platform == "win32" and (
            final_launch_mode == "headless" or final_launch_mode == "virtual_headless"
        ):
            camoufox_popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            logger.debug(
                f"Executing Camoufox internal launch command: {' '.join(camoufox_internal_cmd_args)}"
            )
            self.camoufox_proc = subprocess.Popen(
                camoufox_internal_cmd_args, **camoufox_popen_kwargs
            )
            logger.info(
                f"Camoufox internal process started (PID: {self.camoufox_proc.pid}). Waiting for WebSocket endpoint output (max {ENDPOINT_CAPTURE_TIMEOUT} seconds)..."
            )

            camoufox_output_q = queue.Queue()
            camoufox_stdout_reader = threading.Thread(
                target=_enqueue_output,
                args=(
                    self.camoufox_proc.stdout,
                    "stdout",
                    camoufox_output_q,
                    self.camoufox_proc.pid,
                ),
                daemon=True,
            )
            camoufox_stderr_reader = threading.Thread(
                target=_enqueue_output,
                args=(
                    self.camoufox_proc.stderr,
                    "stderr",
                    camoufox_output_q,
                    self.camoufox_proc.pid,
                ),
                daemon=True,
            )
            camoufox_stdout_reader.start()
            camoufox_stderr_reader.start()

            ws_capture_start_time = time.time()
            camoufox_ended_streams_count = 0
            while time.time() - ws_capture_start_time < ENDPOINT_CAPTURE_TIMEOUT:
                if self.camoufox_proc.poll() is not None:
                    logger.error(
                        f"  Camoufox internal process (PID: {self.camoufox_proc.pid}) unexpectedly exited while waiting for WebSocket endpoint, exit code: {self.camoufox_proc.poll()}."
                    )
                    break
                try:
                    stream_name, line_from_camoufox = camoufox_output_q.get(timeout=0.2)
                    if line_from_camoufox is None:
                        camoufox_ended_streams_count += 1
                        logger.debug(
                            f"  [InternalCamoufox-{stream_name}-PID:{self.camoufox_proc.pid}] Output stream closed (EOF)."
                        )
                        if camoufox_ended_streams_count >= 2:
                            logger.info(
                                f"  Camoufox internal process (PID: {self.camoufox_proc.pid}) all output streams closed."
                            )
                            break
                        continue

                    # Skip the ugly prefix, just log the content
                    log_content = line_from_camoufox.rstrip()
                    # Skip verbose startup messages (move to debug)
                    if (
                        "[InternalCamoufoxStartup]" in log_content
                        or "passed to launch_server" in log_content
                    ):
                        logger.debug(f"(Camoufox) {log_content}")
                    elif (
                        stream_name == "stderr" or "ERROR" in line_from_camoufox.upper()
                    ):
                        logger.info(f"(Camoufox) {log_content}")
                    else:
                        logger.debug(f"(Camoufox) {log_content}")

                    ws_match = ws_regex.search(line_from_camoufox)
                    if ws_match:
                        self.captured_ws_endpoint = ws_match.group(1)
                        logger.debug(
                            f"Successfully captured WebSocket endpoint from Camoufox internal process: {self.captured_ws_endpoint[:40]}..."
                        )
                        logger.info("[Core] WebSocket endpoint obtained successfully")
                        break
                except queue.Empty:
                    continue

            if camoufox_stdout_reader.is_alive():
                camoufox_stdout_reader.join(timeout=1.0)
            if camoufox_stderr_reader.is_alive():
                camoufox_stderr_reader.join(timeout=1.0)

            if not self.captured_ws_endpoint and (
                self.camoufox_proc and self.camoufox_proc.poll() is None
            ):
                logger.error(
                    f"  Failed to capture WebSocket endpoint from Camoufox internal process (PID: {self.camoufox_proc.pid}) within {ENDPOINT_CAPTURE_TIMEOUT} seconds."
                )
                logger.error(
                    "  Camoufox internal process is still running but did not output expected WebSocket endpoint. Please check its logs or behavior."
                )
                self.cleanup()
                sys.exit(1)
            elif not self.captured_ws_endpoint and (
                self.camoufox_proc and self.camoufox_proc.poll() is not None
            ):
                logger.error(
                    "Camoufox internal process exited and failed to capture WebSocket endpoint."
                )
                sys.exit(1)
            elif not self.captured_ws_endpoint:
                logger.error("Failed to capture WebSocket endpoint.")
                sys.exit(1)

        except Exception as e_launch_camoufox_internal:
            logger.critical(
                f"  Fatal error launching Camoufox internally or capturing its WebSocket endpoint: {e_launch_camoufox_internal}",
                exc_info=True,
            )
            self.cleanup()
            sys.exit(1)

        return self.captured_ws_endpoint

    def cleanup(self):
        logger.info("--- Starting cleanup procedure (CamoufoxProcessManager) ---")
        if self.camoufox_proc and self.camoufox_proc.poll() is None:
            pid = self.camoufox_proc.pid
            logger.info(f"Terminating Camoufox process tree (PID: {pid})...")
            try:
                if sys.platform == "win32":
                    # Windows: Force terminate directly, don't try graceful shutdown (headless browsers often hang)
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=5,
                        )
                        logger.info("Process tree successfully terminated.")
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "taskkill timed out, process may have terminated."
                        )
                    except Exception as e:
                        logger.warning(f"taskkill execution exception: {e}")
                elif hasattr(os, "getpgid") and hasattr(os, "killpg"):
                    # Unix: Try SIGTERM, then SIGKILL on timeout
                    try:
                        pgid = os.getpgid(pid)
                        os.killpg(pgid, signal.SIGTERM)
                        self.camoufox_proc.wait(timeout=5)
                        logger.info(
                            f"Process group (PGID: {pgid}) successfully terminated via SIGTERM."
                        )
                    except subprocess.TimeoutExpired:
                        logger.warning("SIGTERM timed out, sending SIGKILL...")
                        try:
                            os.killpg(os.getpgid(pid), signal.SIGKILL)
                            self.camoufox_proc.wait(timeout=2)
                            logger.info(
                                "Process group successfully terminated via SIGKILL."
                            )
                        except Exception:
                            pass
                    except ProcessLookupError:
                        logger.info("Process group not found, may have already exited.")
                else:
                    # Fallback: Terminate process directly
                    self.camoufox_proc.terminate()
                    try:
                        self.camoufox_proc.wait(timeout=5)
                        logger.info("Process successfully terminated.")
                    except subprocess.TimeoutExpired:
                        self.camoufox_proc.kill()
                        logger.info("Process forcefully terminated.")
            except Exception as e_term:
                logger.warning(f"Error terminating process: {e_term}")
            finally:
                # Clean up streams
                for stream in [self.camoufox_proc.stdout, self.camoufox_proc.stderr]:
                    if stream and not stream.closed:
                        try:
                            stream.close()
                        except Exception:
                            pass
            self.camoufox_proc = None
        elif self.camoufox_proc:
            logger.info(
                f"Camoufox internal subprocess previously exited on its own, exit code: {self.camoufox_proc.poll()}."
            )
            self.camoufox_proc = None
        else:
            logger.info(
                "Camoufox internal subprocess not running or already cleaned up."
            )
        logger.info("--- Cleanup procedure completed (CamoufoxProcessManager) ---")
