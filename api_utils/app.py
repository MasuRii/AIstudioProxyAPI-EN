"""
FastAPI application initialization and lifecycle management
"""

import asyncio
import multiprocessing
import queue
import sys
import time
from asyncio import Lock, Queue
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

import stream
from api_utils.server_state import state

# --- browser_utils module imports ---
from browser_utils import (
    _close_page_logic,
    _handle_initial_model_state_and_storage,
    _initialize_page_logic,
    enable_temporary_chat_mode,
    load_excluded_models,
)

# --- Configuration imports ---
from config import EXCLUDED_MODELS_FILENAME, NO_PROXY_ENV, get_environment_variable

# --- logging_utils module imports ---
from logging_utils import restore_original_streams, setup_server_logging

# --- models module imports ---
from models import WebSocketConnectionManager

from . import auth_utils


# --- Lifespan Context Manager ---
def _setup_logging():
    log_level_env = get_environment_variable("SERVER_LOG_LEVEL", "INFO")
    redirect_print_env = get_environment_variable("SERVER_REDIRECT_PRINT", "false")
    state.log_ws_manager = WebSocketConnectionManager()
    return setup_server_logging(
        logger_instance=state.logger,
        log_ws_manager=state.log_ws_manager,
        log_level_name=log_level_env,
        redirect_print_str=redirect_print_env,
    )


def _initialize_globals():
    from api_utils.server_state import state

    state.request_queue = Queue()
    state.processing_lock = Lock()
    state.model_switching_lock = Lock()
    state.params_cache_lock = Lock()

    # Initialize model_list_fetch_event
    state.model_list_fetch_event = asyncio.Event()

    auth_utils.initialize_keys()

    # Initialize Auth Rotation Lock
    from config.global_state import GlobalState

    GlobalState.init_rotation_lock()

    state.logger.info("API keys and global locks initialized.")


def _initialize_proxy_settings():
    stream_port_env = get_environment_variable("STREAM_PORT")
    if stream_port_env == "0":
        proxy_server_url = get_environment_variable(
            "HTTPS_PROXY"
        ) or get_environment_variable("HTTP_PROXY")
    else:
        proxy_server_url = f"http://127.0.0.1:{stream_port_env or 3120}/"

    if proxy_server_url:
        state.PLAYWRIGHT_PROXY_SETTINGS = {"server": proxy_server_url}
        if NO_PROXY_ENV:
            state.PLAYWRIGHT_PROXY_SETTINGS["bypass"] = NO_PROXY_ENV.replace(",", ";")
        state.logger.info(
            f"Playwright proxy settings configured: {state.PLAYWRIGHT_PROXY_SETTINGS}"
        )
    else:
        state.logger.info("No proxy configured for Playwright.")


async def _start_stream_proxy():
    stream_port_env = get_environment_variable("STREAM_PORT")
    if stream_port_env != "0":
        port = int(stream_port_env or 3120)
        stream_proxy_server_env = (
            get_environment_variable("UNIFIED_PROXY_CONFIG")
            or get_environment_variable("HTTPS_PROXY")
            or get_environment_variable("HTTP_PROXY")
        )
        state.logger.info(
            f"Starting STREAM proxy on port {port} with upstream proxy: {stream_proxy_server_env}"
        )
        state.STREAM_QUEUE = multiprocessing.Queue()
        state.STREAM_PROCESS = multiprocessing.Process(
            target=stream.start,
            args=(state.STREAM_QUEUE, port, stream_proxy_server_env),
        )
        state.STREAM_PROCESS.start()
        state.logger.info("STREAM proxy process started. Waiting for 'READY' signal...")

        try:
            ready_signal = await asyncio.to_thread(state.STREAM_QUEUE.get, timeout=15)
            if ready_signal == "READY":
                state.logger.info(
                    "[SUCCESS] Received 'READY' signal from STREAM proxy."
                )
            else:
                state.logger.warning(
                    f"Received unexpected signal from proxy: {ready_signal}"
                )
        except queue.Empty:
            state.logger.error(
                "[ERROR] Timed out waiting for STREAM proxy to become ready. Startup will likely fail."
            )
            raise RuntimeError("STREAM proxy failed to start in time.")


async def _initialize_browser_and_page():
    from playwright.async_api import async_playwright

    state.logger.info("Starting Playwright...")
    state.playwright_manager = await async_playwright().start()
    state.is_playwright_ready = True
    state.logger.info("Playwright started.")

    ws_endpoint = get_environment_variable("CAMOUFOX_WS_ENDPOINT")
    launch_mode = get_environment_variable("LAUNCH_MODE", "unknown")

    if not ws_endpoint and launch_mode != "direct_debug_no_browser":
        raise ValueError("CAMOUFOX_WS_ENDPOINT environment variable is missing.")

    if ws_endpoint:
        state.logger.info(f"Connecting to browser at: {ws_endpoint}")
        state.browser_instance = await state.playwright_manager.firefox.connect(
            ws_endpoint, timeout=30000
        )
        state.is_browser_connected = True
        state.logger.info(f"Connected to browser: {state.browser_instance.version}")

        state.page_instance, state.is_page_ready = await _initialize_page_logic(
            state.browser_instance
        )
        if state.is_page_ready:
            await _handle_initial_model_state_and_storage(state.page_instance)
            await enable_temporary_chat_mode(state.page_instance)
            state.logger.info("Page initialized successfully.")
        else:
            state.logger.error("Page initialization failed.")
            state.page_instance = None
            state.is_page_ready = False
            state.current_ai_studio_model_id = None

    if not state.model_list_fetch_event.is_set():
        state.model_list_fetch_event.set()


async def _shutdown_resources():
    logger = state.logger
    logger.info("Shutting down resources...")

    # Signal global shutdown if event exists
    try:
        from config import GlobalState

        if hasattr(GlobalState, "IS_SHUTTING_DOWN") and hasattr(
            GlobalState.IS_SHUTTING_DOWN, "set"
        ):
            GlobalState.IS_SHUTTING_DOWN.set()
    except Exception as e:
        logger.debug(f"Failed to set IS_SHUTTING_DOWN: {e}")

    state.should_exit = True

    if state.STREAM_PROCESS:
        try:
            state.STREAM_PROCESS.terminate()
            state.STREAM_PROCESS.join(timeout=3)
            if state.STREAM_PROCESS.is_alive():
                logger.warning("STREAM proxy did not terminate, killing...")
                state.STREAM_PROCESS.kill()
                state.STREAM_PROCESS.join(timeout=1)
        except Exception as e:
            logger.error(f"Error terminating STREAM proxy: {e}")
        finally:
            if state.STREAM_QUEUE:
                try:
                    state.STREAM_QUEUE.close()
                    state.STREAM_QUEUE.join_thread()
                except Exception:
                    pass
            state.STREAM_PROCESS = None
            state.STREAM_QUEUE = None
            logger.info("STREAM proxy terminated.")

    if state.worker_task and not state.worker_task.done():
        logger.info("Cancelling worker task...")
        state.worker_task.cancel()
        try:
            await asyncio.wait_for(state.worker_task, timeout=2.0)
            logger.info("Worker task cancelled.")
        except asyncio.TimeoutError:
            logger.warning("Worker task did not respond to cancellation within 2s.")
        except asyncio.CancelledError:
            logger.debug("Worker task cancellation acknowledged (CancelledError).")
        except Exception as e:
            logger.error(f"Error cancelling worker task: {e}")
        finally:
            state.worker_task = None

    if state.page_instance:
        try:
            await _close_page_logic()
        except asyncio.CancelledError:
            logger.debug("Page closure cancelled (CancelledError).")
        except Exception as e:
            logger.error(f"Error during page closure: {e}")
        finally:
            state.page_instance = None
            state.is_page_ready = False

    if state.browser_instance:
        try:
            if state.browser_instance.is_connected():
                await state.browser_instance.close()
                logger.info("Browser connection closed.")
        except asyncio.CancelledError:
            logger.debug("Browser closure cancelled (CancelledError).")
        except Exception as e:
            logger.error(f"Error during browser closure: {e}")
        finally:
            state.browser_instance = None
            state.is_browser_connected = False

    if state.playwright_manager:
        try:
            await state.playwright_manager.stop()
            logger.info("Playwright stopped.")
        except asyncio.CancelledError:
            logger.debug("Playwright stop cancelled (CancelledError).")
        except Exception as e:
            logger.error(f"Error stopping playwright: {e}")
        finally:
            state.playwright_manager = None
            state.is_playwright_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifecycle management"""
    from .queue_worker import queue_worker

    original_streams = sys.stdout, sys.stderr
    initial_stdout, initial_stderr = _setup_logging()
    logger = state.logger

    _initialize_globals()
    _initialize_proxy_settings()
    load_excluded_models(EXCLUDED_MODELS_FILENAME)

    state.is_initializing = True
    startup_start_time = time.time()
    logger.info("Starting AI Studio Proxy Server...")

    try:
        await _start_stream_proxy()
        await _initialize_browser_and_page()

        launch_mode = get_environment_variable("LAUNCH_MODE", "unknown")
        if state.is_page_ready or launch_mode == "direct_debug_no_browser":
            state.worker_task = asyncio.create_task(queue_worker())
            logger.info("Request processing worker started.")
        else:
            raise RuntimeError("Failed to initialize browser/page, worker not started.")

        logger.info("[WATCHDOG] Starting Quota Watchdog Task...")
        watchdog_func = state.quota_watchdog
        if watchdog_func:
            app.state.watchdog_task = asyncio.create_task(watchdog_func())
        else:
            logger.warning(
                "[WATCHDOG] Quota Watchdog function not found, task not started."
            )

        startup_duration = time.time() - startup_start_time
        logger.info(f"Server startup complete. (Took: {startup_duration:.2f}s)")
        state.is_initializing = False
        yield
    except Exception as e:
        logger.critical(f"Application startup failed: {e}", exc_info=True)
        await _shutdown_resources()
        raise RuntimeError(f"Application startup failed: {e}") from e
    finally:
        logger.info("Shutting down server...")
        if hasattr(app.state, "watchdog_task"):
            logger.info("[STOP] Stopping Quota Watchdog...")
            task = app.state.watchdog_task
            if hasattr(task, "cancel"):
                task.cancel()
                # Only await if it's actually an asyncio task or future
                if isinstance(task, (asyncio.Task, asyncio.Future)):
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        try:
            await _shutdown_resources()
        finally:
            restore_original_streams(initial_stdout, initial_stderr)
            restore_original_streams(*original_streams)
            logger.info("Server shut down.")


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.excluded_paths = [
            "/v1/models",
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico",
        ]

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable]
    ):
        if not auth_utils.API_KEYS:
            return await call_next(request)
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)
        for excluded_path in self.excluded_paths:
            if request.url.path == excluded_path or request.url.path.startswith(
                excluded_path + "/"
            ):
                return await call_next(request)
        api_key = request.headers.get("Authorization")
        if api_key and api_key.startswith("Bearer "):
            api_key = api_key[7:]
        if not api_key:
            api_key = request.headers.get("X-API-Key")
        if not api_key or not auth_utils.verify_api_key(api_key):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "message": "Invalid or missing API key. Please provide a valid API key using 'Authorization: Bearer <your_key>' or 'X-API-Key: <your_key>' header.",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_api_key",
                    }
                },
            )
        return await call_next(request)


def create_app() -> FastAPI:
    """Create FastAPI application instance"""
    app = FastAPI(
        title="AI Studio Proxy Server (Integrated Mode)",
        description="Proxy server interacting with AI Studio via Playwright.",
        version="0.6.0-integrated",
        lifespan=lifespan,
    )
    app.add_middleware(APIKeyAuthMiddleware)
    from fastapi.responses import FileResponse

    from .routers import (
        add_api_key,
        auth_files_router,
        cancel_request,
        chat_completions,
        delete_api_key,
        get_api_info,
        get_api_keys,
        get_queue_status,
        health_check,
        list_models,
        model_capabilities_router,
        ports_router,
        proxy_router,
        read_index,
        serve_react_assets,
        test_api_key,
        websocket_log_endpoint,
    )

    app.get("/", response_class=FileResponse)(read_index)
    app.get("/assets/{filename:path}")(serve_react_assets)
    app.get("/api/info")(get_api_info)
    app.get("/health")(health_check)
    app.get("/v1/models")(list_models)
    app.post("/v1/chat/completions")(chat_completions)
    app.post("/v1/cancel/{req_id}")(cancel_request)
    app.get("/v1/queue")(get_queue_status)
    app.websocket("/ws/logs")(websocket_log_endpoint)
    app.include_router(model_capabilities_router)
    app.include_router(proxy_router)
    app.include_router(auth_files_router)
    app.include_router(ports_router)
    from api_utils.routers import helper_router, server_router

    app.include_router(server_router)
    app.include_router(helper_router)
    app.get("/api/keys")(get_api_keys)
    app.post("/api/keys")(add_api_key)
    app.post("/api/keys/test")(test_api_key)
    app.delete("/api/keys")(delete_api_key)
    return app
