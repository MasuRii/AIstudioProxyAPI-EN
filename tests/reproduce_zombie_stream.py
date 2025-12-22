import asyncio
import logging
import os
import sys
import time
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock server module
sys.modules["server"] = MagicMock()
sys.modules["server"].STREAM_QUEUE = asyncio.Queue()
sys.modules["server"].logger = logging.getLogger("repro")

# Mock models module
sys.modules["models"] = MagicMock()

# Mock browser_utils to prevent transitive import errors
sys.modules["browser_utils"] = MagicMock()
sys.modules["browser_utils.page_controller"] = MagicMock()

# Mock config and config.global_state
# IMPORTANT: We must mock config as a package that contains submodules
sys.modules["config"] = MagicMock()
sys.modules["config.global_state"] = MagicMock()
sys.modules["config.settings"] = MagicMock() # Added this line

# Setup GlobalState class mock
class MockGlobalState:
    IS_QUOTA_EXCEEDED = False
    IS_RECOVERING = False
    LAST_ROTATION_TIMESTAMP = time.time() - 10.0  # Simulate rotation 10 seconds ago (within 30s window)
    IS_SHUTTING_DOWN = MagicMock()
    IS_SHUTTING_DOWN.is_set.return_value = False

sys.modules["config.global_state"].GlobalState = MockGlobalState

# Mock attributes on the config module itself
sys.modules["config"].SCROLL_CONTAINER_SELECTOR = ""
sys.modules["config"].CHAT_SESSION_CONTENT_SELECTOR = ""
sys.modules["config"].LAST_CHAT_TURN_SELECTOR = ""
sys.modules["config"].UI_GENERATION_WAIT_TIMEOUT_MS = 100
sys.modules["config"].GlobalState = MockGlobalState

# Now we can import
import server
from api_utils.utils_ext.stream import use_stream_response

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repro")

async def reproduce():
    print("--- Starting Reproduction Test ---")

    # 1. Setup State: Quota was exceeded, but just recovered (Rotation finished)
    # The bug is that IS_QUOTA_EXCEEDED is False (because we recovered),
    # but the stream logic thinks an empty DONE is "stale" because it's the first item.
    MockGlobalState.IS_QUOTA_EXCEEDED = False
    MockGlobalState.IS_RECOVERING = False

    import json
    # 2. Add an empty DONE signal to the queue (simulating the end of the rotated request)
    # NOTE: We must send it as a string to bypass the early 'isinstance(data, dict)' check at line 186
    # and force it into the parsing logic where the 'stale data' check exists.
    await server.STREAM_QUEUE.put(json.dumps({"done": True, "body": "", "reason": ""}))

    # 3. Run stream handler with a short timeout to catch the hang
    print("Running stream handler...")

    # We expect it to exit immediately. If it hangs, we'll catch the timeout.
    try:
        # Use a short timeout for the generator itself, but inside the function
        # the loop might wait up to 'timeout' arg (which we set to 2.0s for test)
        async for chunk in use_stream_response(req_id="test_req", timeout=1.0, enable_silence_detection=True):
            print(f"Received chunk: {chunk}")
            if chunk.get("done"):
                print("Received DONE signal. Checking if generator exits...")
                # If the generator exits correctly, the loop should end (StopAsyncIteration).
                # If the generator stays alive (zombie), it will just hang here waiting for next yield.
                continue

        print("SUCCESS: Generator finished (raised StopAsyncIteration).")
        return

    except asyncio.TimeoutError:
        # This won't be raised by the generator loop itself usually,
        # unless we wrap it. The generator yields items.
        # If it enters the "wait loop", it won't yield.
        pass

    print("FAILURE: Stream handler did not yield completion (likely stuck in wait loop).")

async def main():
    # Wrap in timeout to detect the hang
    try:
        await asyncio.wait_for(reproduce(), timeout=5.0)
    except asyncio.TimeoutError:
        print("CRITICAL FAILURE: Test timed out! The stream handler entered the zombie loop.")

if __name__ == "__main__":
    asyncio.run(main())
