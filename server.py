import os
import asyncio
import multiprocessing
import logging
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
)
from threading import Lock
from dotenv import load_dotenv

load_dotenv()

# --- Centralized state module ---
from api_utils.server_state import state

# --- Backward compatibility ---
_STATE_ATTRS = {
    "STREAM_QUEUE",
    "STREAM_PROCESS",
    "playwright_manager",
    "browser_instance",
    "page_instance",
    "is_playwright_ready",
    "is_browser_connected",
    "is_page_ready",
    "is_initializing",
    "PLAYWRIGHT_PROXY_SETTINGS",
    "global_model_list_raw_json",
    "parsed_model_list",
    "model_list_fetch_event",
    "current_ai_studio_model_id",
    "current_auth_profile_path",
    "model_switching_lock",
    "excluded_model_ids",
    "request_queue",
    "processing_lock",
    "worker_task",
    "page_params_cache",
    "params_cache_lock",
    "console_logs",
    "network_log",
    "logger",
    "log_ws_manager",
    "should_exit",
}


def __getattr__(name: str) -> Any:
    if name in _STATE_ATTRS:
        return getattr(state, name)
    raise AttributeError(f"module 'server' has no attribute '{name}'")


def __setattr__(name: str, value: Any) -> None:
    if name in _STATE_ATTRS:
        setattr(state, name, value)
    else:
        globals()[name] = value


def clear_debug_logs() -> None:
    state.clear_debug_logs()


# --- Imports ---
from config import (
    RESPONSE_COMPLETION_TIMEOUT,
    GlobalState,
)
from playwright.async_api import Page as AsyncPage
from models import (
    FunctionCall,
    ToolCall,
    MessageContentItem,
    Message,
    ChatCompletionRequest,
    ClientDisconnectedError,
    StreamToLogger,
    WebSocketConnectionManager,
    WebSocketLogHandler,
)
from logging_utils import setup_server_logging, restore_original_streams
from browser_utils import (
    _initialize_page_logic,
    _close_page_logic,
    signal_camoufox_shutdown,
    _handle_model_list_response,
    detect_and_extract_page_error,
    save_error_snapshot,
    get_response_via_edit_button,
    get_response_via_copy_button,
    _wait_for_response_completion,
    _get_final_response_content,
    get_raw_text_content,
    switch_ai_studio_model,
    load_excluded_models,
    _handle_initial_model_state_and_storage,
    _set_model_from_page_display,
)
from browser_utils.auth_rotation import perform_auth_rotation
from api_utils import (
    create_app,
)

# Global variables (proxied to state)
STREAM_QUEUE: Optional[multiprocessing.Queue] = None
STREAM_PROCESS: Optional[multiprocessing.Process] = None
playwright_manager: Optional[Any] = None
browser_instance: Optional[Any] = None
page_instance: Optional[Any] = None
is_playwright_ready = False
is_browser_connected = False
is_page_ready = False
is_initializing = False
PLAYWRIGHT_PROXY_SETTINGS: Optional[Dict[str, str]] = None
global_model_list_raw_json: Optional[List[Any]] = None
parsed_model_list: List[Dict[str, Any]] = []
model_list_fetch_event = asyncio.Event()
current_ai_studio_model_id: Optional[str] = None
current_auth_profile_path: Optional[str] = None
model_switching_lock: Optional[Lock] = None
excluded_model_ids: Set[str] = set()
request_queue: Optional[Any] = None
processing_lock: Optional[Lock] = None
worker_task: Optional[Any] = None
page_params_cache: Dict[str, Any] = {}
params_cache_lock: Optional[Lock] = None
logger = logging.getLogger("AIStudioProxyServer")
log_ws_manager: Optional[WebSocketConnectionManager] = None
should_exit = False

# --- FastAPI App ---
app = create_app()


async def quota_watchdog():
    """Background watchdog to monitor quota exceeded events."""
    logger.info("👀 Quota Watchdog Started")
    while True:
        try:
            await GlobalState.QUOTA_EXCEEDED_EVENT.wait()
            logger.critical(
                "🚨 Watchdog detected Quota Exceeded! Initiating Rotation..."
            )

            if not GlobalState.AUTH_ROTATION_LOCK.is_set():
                logger.info("Watchdog: Rotation already in progress. Waiting...")
                await asyncio.sleep(1)
                continue

            GlobalState.start_recovery()
            try:
                current_model_id = state.current_ai_studio_model_id
                success = await perform_auth_rotation(
                    target_model_id=current_model_id or ""
                )
                if success:
                    logger.info("Watchdog: Rotation successful.")
                else:
                    logger.error("Watchdog: Rotation failed.")
            finally:
                GlobalState.finish_recovery()

            if GlobalState.IS_QUOTA_EXCEEDED:
                logger.warning("Watchdog: Quota flag still set. Forcing reset.")
                GlobalState.reset_quota_status()

        except asyncio.CancelledError:
            logger.info("Watchdog: Task cancelled.")
            break
        except Exception as e:
            logger.error(f"Watchdog Error: {e}", exc_info=True)
            await asyncio.sleep(5)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 2048))
    uvicorn.run(
        "server:app", host="0.0.0.0", port=port, log_level="info", access_log=False
    )
