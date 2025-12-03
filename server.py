import os
from typing import (
    Any,
)

# Add: Import load_dotenv
from dotenv import load_dotenv

# Add: Load .env file before other imports
load_dotenv()


# --- 导入集中状态模块 ---
from api_utils.server_state import state

# --- 向后兼容：通过 __getattr__ 将属性访问转发到 state 对象 ---
# 这允许现有代码继续使用 `import server; server.page_instance`
# 同时保持状态的集中管理

# 定义需要转发到 state 的属性名称
_STATE_ATTRS = {
    # Stream Queue
    "STREAM_QUEUE",
    "STREAM_PROCESS",
    # Playwright/Browser State
    "playwright_manager",
    "browser_instance",
    "page_instance",
    "is_playwright_ready",
    "is_browser_connected",
    "is_page_ready",
    "is_initializing",
    # Proxy Configuration
    "PLAYWRIGHT_PROXY_SETTINGS",
    # Model State
    "global_model_list_raw_json",
    "parsed_model_list",
    "model_list_fetch_event",
    "current_ai_studio_model_id",
    "model_switching_lock",
    "excluded_model_ids",
    # Request Processing State
    "request_queue",
    "processing_lock",
    "worker_task",
    # Parameter Cache
    "page_params_cache",
    "params_cache_lock",
    # Debug Logging State
    "console_logs",
    "network_log",
    # Logging
    "logger",
    "log_ws_manager",
    # Control Flags
    "should_exit",
}


def __getattr__(name: str) -> Any:
    """Forward attribute access to the state object for backward compatibility."""
    if name in _STATE_ATTRS:
        return getattr(state, name)
    raise AttributeError(f"module 'server' has no attribute '{name}'")


def __setattr__(name: str, value: Any) -> None:
    """Forward attribute assignment to the state object for backward compatibility."""
    if name in _STATE_ATTRS:
        setattr(state, name, value)
    else:
        # For non-state attributes, use the module's __dict__
        globals()[name] = value


def clear_debug_logs() -> None:
    """Clear console and network logs (called after each request)."""
    state.clear_debug_logs()


# --- Config Module Import ---
from config import (
    RESPONSE_COMPLETION_TIMEOUT,
)

# --- Models Module Import ---
from models import (
    FunctionCall,
    ToolCall,
    MessageContentItem, 
    Message,
    ChatCompletionRequest,
    ClientDisconnectedError,
    StreamToLogger,
    WebSocketConnectionManager,
    WebSocketLogHandler
)

# --- Logging Utils Module Import ---
from logging_utils import setup_server_logging, restore_original_streams

# --- Browser Utils Module Import ---
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
    _set_model_from_page_display
)

# --- API Utils Module Import ---
from api_utils import (
    create_app,
)

# --- stream queue ---
STREAM_QUEUE:Optional[multiprocessing.Queue] = None
STREAM_PROCESS = None

# --- Global State ---
playwright_manager: Optional[AsyncPlaywright] = None
browser_instance: Optional[AsyncBrowser] = None
page_instance: Optional[AsyncPage] = None
is_playwright_ready = False
is_browser_connected = False
is_page_ready = False
is_initializing = False

# --- Global Proxy Config ---
PLAYWRIGHT_PROXY_SETTINGS: Optional[Dict[str, str]] = None

global_model_list_raw_json: Optional[List[Any]] = None
parsed_model_list: List[Dict[str, Any]] = []
model_list_fetch_event = asyncio.Event()

current_ai_studio_model_id: Optional[str] = None
current_auth_profile_path: Optional[str] = None
model_switching_lock: Optional[Lock] = None

excluded_model_ids: Set[str] = set()

request_queue: Optional[Queue] = None
processing_lock: Optional[Lock] = None
worker_task: Optional[Task] = None

page_params_cache: Dict[str, Any] = {}
params_cache_lock: Optional[Lock] = None

logger = logging.getLogger("AIStudioProxyServer")
log_ws_manager = None


# --- FastAPI App Definition ---
app = create_app()

async def quota_watchdog():
    """
    Background watchdog to monitor quota exceeded events and trigger immediate rotation.
    Uses Event.wait() for instant reaction instead of polling.
    """
    from config.global_state import GlobalState
    from browser_utils.auth_rotation import perform_auth_rotation
    
    logger.info("👀 Quota Watchdog Started")
    while True:
        try:
            # Wait for the event signal (Instant Wakeup)
            await GlobalState.QUOTA_EXCEEDED_EVENT.wait()
            
            logger.critical("🚨 Watchdog detected Quota Exceeded! Initiating Rotation...")
            
            # Check if already rotating to avoid double trigger
            if not GlobalState.AUTH_ROTATION_LOCK.is_set():
                 logger.info("Watchdog: Rotation already in progress (Lock is clear). Waiting...")
                 await asyncio.sleep(1)
                 continue
            
            # Force rotation
            # [FIX-COORD] Wrap in recovery signal to notify listeners (stream/worker)
            GlobalState.start_recovery()
            try:
                # Get current model ID for smart rotation
                current_model_id = current_ai_studio_model_id
                success = await perform_auth_rotation(target_model_id=current_model_id)
                if success:
                    logger.info("Watchdog: Rotation triggered and completed successfully.")
                else:
                    logger.error("Watchdog: Rotation triggered but failed.")
            finally:
                GlobalState.finish_recovery()
            
            # Ensure event/flag is cleared
            if GlobalState.IS_QUOTA_EXCEEDED:
                 logger.warning("Watchdog: Quota flag still set after rotation. Forcing reset.")
                 GlobalState.reset_quota_status()
                     
        except asyncio.CancelledError:
            logger.info("Watchdog: Task cancelled.")
            break
        except Exception as e:
            logger.error(f"Watchdog Error: {e}", exc_info=True)
            await asyncio.sleep(5)


# --- Main Guard ---
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 2048))
    uvicorn.run(
        "server:app", host="0.0.0.0", port=port, log_level="info", access_log=False
    )
