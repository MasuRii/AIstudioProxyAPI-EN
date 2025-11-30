import asyncio
import threading
import time
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ShutdownTest")

# Mock GlobalState
class GlobalState:
    IS_SHUTTING_DOWN = threading.Event()

async def _wait_for_shutdown():
    """Helper to wait for GlobalState.IS_SHUTTING_DOWN event."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, GlobalState.IS_SHUTTING_DOWN.wait)

async def mock_expect_async_visible(timeout):
    """Mocks Playwright's expect(locator).to_be_visible(timeout) with a long sleep."""
    logger.info(f"Mock expect_async started, sleeping for {timeout/1000} seconds...")
    try:
        await asyncio.sleep(timeout / 1000)
        logger.info("Mock expect_async finished normally.")
        return True
    except asyncio.CancelledError:
        logger.info("Mock expect_async was cancelled!")
        raise

async def test_shutdown_interruption():
    logger.info("Starting test_shutdown_interruption...")
    
    # Reset event just in case
    GlobalState.IS_SHUTTING_DOWN.clear()
    
    # 1. Start the long running task (simulating waiting for element)
    # Simulating 35000ms timeout like in the real code
    expect_task = asyncio.create_task(mock_expect_async_visible(timeout=35000))
    
    # 2. Start the shutdown waiter
    shutdown_task = asyncio.create_task(_wait_for_shutdown())
    
    # 3. Schedule the shutdown event trigger in 2 seconds (simulating user Ctrl+C)
    def trigger_shutdown():
        logger.info("Simulating Ctrl+C (waiting 2s then setting IS_SHUTTING_DOWN)...")
        time.sleep(2)
        GlobalState.IS_SHUTTING_DOWN.set()
        logger.info("IS_SHUTTING_DOWN set.")

    # Run trigger in a separate thread to simulate external signal/event
    trigger_thread = threading.Thread(target=trigger_shutdown)
    trigger_thread.start()
    
    start_time = time.time()
    
    # 4. Wait for FIRST_COMPLETED
    logger.info("Waiting for tasks...")
    done, pending = await asyncio.wait([expect_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED)
    
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"Await finished in {duration:.2f} seconds.")

    if shutdown_task in done:
        logger.info("🛑 Shutdown signal received during initialization. Aborting.")
        expect_task.cancel()
        try:
            await expect_task
        except asyncio.CancelledError:
            pass
        logger.info("Verified: expect_task cancelled successfully.")
        
        if duration < 5.0:
             logger.info("✅ SUCCESS: Test completed quickly (well under 35s). Fix verified.")
        else:
             logger.error("❌ FAILURE: Test took too long.")
             raise RuntimeError("Test failed: took too long")
    else:
        logger.error("❌ FAILURE: expect_task finished first (unexpected).")
        raise RuntimeError("Test failed: expect_task finished first")

    # Wait for trigger thread to ensure clean exit
    trigger_thread.join()

if __name__ == "__main__":
    asyncio.run(test_shutdown_interruption())