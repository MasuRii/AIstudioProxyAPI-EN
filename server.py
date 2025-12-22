import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

# --- Centralized state module ---
from api_utils.server_state import state


def clear_debug_logs() -> None:
    state.clear_debug_logs()


# --- Imports ---

from browser_utils.auth_rotation import perform_auth_rotation
from config import (
    GlobalState,
)


async def quota_watchdog():
    """Background watchdog to monitor quota exceeded events."""
    # Use state's logger if available
    logger = getattr(state, "logger", logging.getLogger("AIStudioProxyServer"))
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


# Register quota_watchdog in state for easier access and to avoid circular import issues
state.quota_watchdog = quota_watchdog


from api_utils import (
    create_app,
)

# --- FastAPI App ---
app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 2048))
    uvicorn.run(
        "server:app", host="0.0.0.0", port=port, log_level="info", access_log=False
    )
