# Debug Report - is_disconnected() Hang in Queue Worker

## Issue Summary
The request queue worker was intermittently hanging during its cleanup loop. This loop iterates through queued requests to identify and remove clients that have disconnected while waiting for processing.

## Root Cause
The hang was caused by the use of `await item_http_request.is_disconnected()` in `api_utils/queue_worker.py`. 

In Starlette/FastAPI, `Request.is_disconnected()` is an asynchronous method that calls `await self.receive()`. If the connection is still alive but no data is being sent by the client, `receive()` blocks indefinitely until a message (either data or a disconnect signal) is received from the ASGI server. 

When called within the main loop of the queue worker, this blocking call caused the entire worker task to hang, preventing it from processing new requests or cleaning up other items in the queue.

## Evidence
- Code in `api_utils/queue_worker.py` (lines 100 and 868) directly awaited `item_http_request.is_disconnected()` without any timeout.
- The `check_client_connection` helper in `api_utils/client_connection.py` also had a fallback that awaited `is_disconnected()` without a timeout.
- Log analysis (provided in task context) indicated that the worker stopped precisely at these check points.

## Fix Details

### 1. `api_utils/client_connection.py`
Modified `check_client_connection` to be truly non-blocking:
- If the `_receive()` poll times out (0.01s), it now returns `True` (assuming connected) instead of falling back to a blocking `is_disconnected()` call.
- The fallback to `is_disconnected()` (for non-standard request objects) is now wrapped in `asyncio.wait_for` with a 0.01s timeout.
- Removed a redundant and potentially blocking `is_disconnected()` check in `setup_disconnect_monitoring`.

### 2. `api_utils/queue_worker.py`
- Updated both the `QueueManager.check_queue_disconnects` method and the `queue_worker()` standalone function to use `check_client_connection()` instead of calling `is_disconnected()` directly.
- This ensures that all connection checks performed during queue cleanup are governed by the new non-blocking logic.

## Verification
- Connection checks now use a 0.01s timeout.
- If a client is still connected but idle, the check returns `True` almost immediately (after 10ms), allowing the worker to continue.
- If a client is disconnected, the `_receive()` poll or the timed-out `is_disconnected()` call will correctly identify the state (either by receiving the disconnect message or by eventually catching it in a subsequent loop iteration).

## Files Modified
- `api_utils/client_connection.py`
- `api_utils/queue_worker.py`

## Prevention Recommendations
- Never await `is_disconnected()` or `receive()` on a request object in a background loop without a timeout.
- Use the centralized `check_client_connection` utility for all connection state checks.
- Add lint rules or type checks to discourage direct use of potentially blocking Starlette Request methods in critical paths.
