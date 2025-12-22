# --- browser_utils/operations_modules/errors.py ---
import asyncio
import json
import logging
import traceback
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from playwright.async_api import Error as PlaywrightAsyncError
from playwright.async_api import Page as AsyncPage
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from config import ERROR_TOAST_SELECTOR
from logging_utils import set_request_id

logger = logging.getLogger("AIStudioProxyServer")


class ErrorCategory(Enum):
    """Error type classification for standardized error snapshot saving behavior."""

    TIMEOUT = (
        "timeout"  # Timeout errors (Playwright TimeoutError, asyncio.TimeoutError)
    )
    PLAYWRIGHT = "playwright"  # Playwright browser errors
    NETWORK = "network"  # Network/connection errors
    CLIENT = "client"  # Client disconnected
    VALIDATION = "validation"  # Validation errors (ValueError, TypeError)
    CANCELLED = "cancelled"  # Task cancelled
    UNKNOWN = "unknown"  # Unclassified errors


def categorize_error(exception: BaseException) -> ErrorCategory:
    """
    Automatically categorize error based on exception type.

    Args:
        exception: The exception object to classify

    Returns:
        ErrorCategory: The classified error category
    """
    exc_type = type(exception)
    exc_name = exc_type.__name__.lower()
    exc_module = exc_type.__module__ or ""

    # Cancellation error - special handling
    if isinstance(exception, asyncio.CancelledError):
        return ErrorCategory.CANCELLED

    # Timeout errors
    if isinstance(exception, (PlaywrightTimeoutError, asyncio.TimeoutError)):
        return ErrorCategory.TIMEOUT
    if "timeout" in exc_name:
        return ErrorCategory.TIMEOUT

    # Playwright errors
    if isinstance(exception, PlaywrightAsyncError):
        return ErrorCategory.PLAYWRIGHT
    if "playwright" in exc_module.lower():
        return ErrorCategory.PLAYWRIGHT

    # Network/connection errors
    network_keywords = ["connection", "network", "socket", "http", "ssl", "connect"]
    if any(kw in exc_name for kw in network_keywords):
        return ErrorCategory.NETWORK
    if any(kw in str(exception).lower() for kw in ["connection", "network", "socket"]):
        return ErrorCategory.NETWORK

    # Client disconnect
    if "clientdisconnected" in exc_name or "disconnect" in exc_name:
        return ErrorCategory.CLIENT

    # Validation errors
    if isinstance(exception, (ValueError, TypeError, AttributeError)):
        return ErrorCategory.VALIDATION

    return ErrorCategory.UNKNOWN


async def detect_and_extract_page_error(page: AsyncPage, req_id: str) -> Optional[str]:
    """Detect and extract page errors"""
    set_request_id(req_id)
    error_toast_locator = page.locator(ERROR_TOAST_SELECTOR).last
    try:
        await error_toast_locator.wait_for(state="visible", timeout=500)
        message_locator = error_toast_locator.locator("span.content-text")
        error_message = await message_locator.text_content(timeout=500)
        if error_message:
            logger.error(f"Detected and extracted error message: {error_message}")
            return error_message.strip()
        else:
            logger.warning("Detected error toast, but could not extract message.")
            return "Error toast detected, but specific message could not be extracted."
    except PlaywrightAsyncError:
        return None
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"Error checking for page errors: {e}")
        return None


async def save_minimal_snapshot(
    error_name: str,
    req_id: str = "unknown",
    error_category: Optional[ErrorCategory] = None,
    error_exception: Optional[BaseException] = None,
    additional_context: Optional[dict] = None,
) -> str:
    """
    Save minimal error snapshot (no browser/page required).

    Saves valuable debug info even when browser or page is unavailable.
    Includes environment variables, queue status, lock status, and a summary.

    Args:
        error_name: Error name
        req_id: Request ID
        error_category: Error category (optional)
        error_exception: Exception that triggered the snapshot (optional)
        additional_context: Extra context info (optional)

    Returns:
        str: Snapshot directory path, empty string on failure
    """
    try:
        import os
        import platform
        import sys

        # Generate timestamp (using local time)
        now = datetime.now().astimezone()
        iso_timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        date_str = iso_timestamp.split("T")[0]
        time_component = iso_timestamp.split("T")[1].replace(":", "-").replace(".", "-")

        # Create directory structure (using errors_py in project root)
        # Path: operations_modules -> browser_utils -> project_root
        base_error_dir = Path(__file__).parent.parent.parent / "errors_py"
        date_dir = base_error_dir / date_str
        snapshot_dir_name = f"{time_component}_{req_id}_{error_name}_minimal"
        snapshot_dir = date_dir / snapshot_dir_name
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Auto-categorize error (if not provided and exception is available)
        if error_category is None and error_exception is not None:
            error_category = categorize_error(error_exception)

        # === 1. Build detailed metadata ===
        metadata: dict = {
            "snapshot_info": {
                "type": "minimal",
                "reason": "Browser/page unavailable",
                "timestamp_iso": iso_timestamp,
                "timestamp_local": now.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
            },
            "error": {
                "name": error_name,
                "category": error_category.value if error_category else "unknown",
                "req_id": req_id,
            },
            "system": {
                "platform": platform.platform(),
                "python_version": sys.version.split()[0],
                "pid": os.getpid(),
                "cwd": os.getcwd(),
            },
        }

        # Add exception details
        if error_exception is not None:
            tb_lines = traceback.format_exception(
                type(error_exception), error_exception, error_exception.__traceback__
            )
            metadata["exception"] = {
                "type": type(error_exception).__name__,
                "module": type(error_exception).__module__,
                "message": str(error_exception),
                "args": [str(a) for a in getattr(error_exception, "args", [])[:5]],
                "traceback": "".join(tb_lines),
            }

        # Add additional context
        if additional_context:
            metadata["additional_context"] = additional_context

        # === 2. Capture application state ===
        try:
            from api_utils.server_state import state

            # Basic flags
            metadata["application_state"] = {
                "flags": {
                    "is_playwright_ready": getattr(state, "is_playwright_ready", None),
                    "is_browser_connected": getattr(
                        state, "is_browser_connected", None
                    ),
                    "is_page_ready": getattr(state, "is_page_ready", None),
                    "is_initializing": getattr(state, "is_initializing", None),
                },
                "current_model": getattr(state, "current_ai_studio_model_id", None),
                "excluded_models_count": len(getattr(state, "excluded_model_ids", [])),
            }

            # Queue status
            rq = getattr(state, "request_queue", None)
            if rq:
                try:
                    metadata["application_state"]["request_queue_size"] = rq.qsize()
                except Exception:
                    metadata["application_state"]["request_queue_size"] = "N/A"

            # Lock status
            pl = getattr(state, "processing_lock", None)
            ml = getattr(state, "model_switching_lock", None)
            metadata["application_state"]["locks"] = {
                "processing_lock": pl.locked()
                if pl and hasattr(pl, "locked")
                else None,
                "model_switching_lock": ml.locked()
                if ml and hasattr(ml, "locked")
                else None,
            }

            # Stream queue
            sq = getattr(state, "STREAM_QUEUE", None)
            metadata["application_state"]["stream_queue_active"] = sq is not None

        except Exception as server_err:
            metadata["application_state"] = {"error": str(server_err)}

        # === 3. Environment variables (security filtered) ===
        safe_env_keys = [
            "HEADLESS",
            "DEBUG_LOGS_ENABLED",
            "DEFAULT_MODEL",
            "LAUNCH_MODE",
            "RESPONSE_COMPLETION_TIMEOUT",
            "HOST_OS_FOR_SHORTCUT",
            "PORT",
            "STREAM_PROXY_PORT",
            "LOG_LEVEL",
        ]
        metadata["environment"] = {
            k: os.environ.get(k, "not set") for k in safe_env_keys
        }

        # === 4. Save metadata.json ===
        metadata_path = snapshot_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # === 5. Create human-readable SUMMARY.txt ===
        summary_path = snapshot_dir / "SUMMARY.txt"
        summary_lines = [
            "=" * 60,
            "ERROR SNAPSHOT SUMMARY",
            "=" * 60,
            "",
            f"Timestamp: {metadata['snapshot_info']['timestamp_local']}",
            f"Request ID: {req_id}",
            f"Error Name: {error_name}",
            f"Category: {error_category.value if error_category else 'unknown'}",
            "Snapshot Type: MINIMAL (browser unavailable)",
            "",
            "-" * 60,
            "EXCEPTION DETAILS",
            "-" * 60,
        ]

        if error_exception:
            summary_lines.extend(
                [
                    f"Type: {type(error_exception).__name__}",
                    f"Message: {error_exception}",
                    "",
                    "Traceback:",
                    metadata["exception"]["traceback"],
                ]
            )
        else:
            summary_lines.append("No exception provided")

        summary_lines.extend(
            [
                "",
                "-" * 60,
                "APPLICATION STATE",
                "-" * 60,
            ]
        )

        app_state = metadata.get("application_state", {})
        flags = app_state.get("flags", {})
        for key, val in flags.items():
            summary_lines.append(f"  {key}: {val}")

        summary_lines.extend(
            [
                f"  Current Model: {app_state.get('current_model', 'N/A')}",
                f"  Queue Size: {app_state.get('request_queue_size', 'N/A')}",
                "",
                "-" * 60,
                "FILES IN SNAPSHOT",
                "-" * 60,
                "  - SUMMARY.txt (this file)",
                "  - metadata.json (full details)",
                "",
                "=" * 60,
            ]
        )

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(summary_lines))

        logger.info(f"[Snapshot] Saved minimal snapshot: {snapshot_dir.name}")
        return str(snapshot_dir)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"[Snapshot] Failed to save minimal snapshot: {e}")
        return ""


async def save_error_snapshot(
    error_name: str = "error",
    error_exception: Optional[Exception] = None,
    error_stage: str = "",
    additional_context: Optional[dict] = None,
    locators: Optional[dict] = None,
):
    """
    Save error snapshot (Robust wrapper with guaranteed save).

    Ensures that SOMETHING is always saved when called.
    Falls back to minimal snapshot if browser/page is unavailable.

    Args:
        error_name: Error name with optional req_id suffix (e.g., "error_hbfu521")
        error_exception: The exception that triggered the snapshot (optional)
        error_stage: Description of the error stage (optional)
        additional_context: Extra context dict to include in metadata (optional)
        locators: Dict of named locators to capture states for (optional)
    """
    # Parse req_id
    name_parts = error_name.split("_")
    req_id = (
        name_parts[-1]
        if len(name_parts) > 1 and len(name_parts[-1]) == 7
        else "unknown"
    )

    # Auto-categorize error
    error_category = None
    if error_exception is not None:
        error_category = categorize_error(error_exception)
        # Skip snapshot for cancellation errors
        if error_category == ErrorCategory.CANCELLED:
            logger.debug(
                f"[Snapshot] Skipping snapshot for cancelled error: {error_name}"
            )
            return

    # Add category to context
    context = additional_context.copy() if additional_context else {}
    if error_category:
        context["error_category"] = error_category.value

    try:
        from browser_utils.debug_utils import save_error_snapshot_enhanced

        await save_error_snapshot_enhanced(
            error_name,
            error_exception=error_exception,
            error_stage=error_stage,
            additional_context=context,
            locators=locators,
        )
    except asyncio.CancelledError:
        raise
    except Exception as enhanced_err:
        # Fall back to minimal snapshot if enhanced snapshot fails
        logger.warning(
            f"[Snapshot] Enhanced snapshot failed ({enhanced_err}), falling back to minimal snapshot..."
        )
        await save_minimal_snapshot(
            error_name=error_name,
            req_id=req_id,
            error_category=error_category,
            error_exception=error_exception,
            additional_context=context,
        )
