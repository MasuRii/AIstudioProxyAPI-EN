# Debug Report: Queue Worker State Synchronization Bug

**Date**: 2025-06-22  
**Agent**: Debug Agent  
**Issue**: Requests queued but never processed by queue worker

---

## Issue Summary

Requests were being received and queued by the chat router, but the queue worker never processed them. Logs showed "Request processing worker started" but no "Request dequeued" messages.

---

## Root Cause

### Primary Bug: Broken Module-Level `__setattr__` Proxy

**Location**: `server.py` lines 58-62 and `api_utils/app.py` lines 93-96

The `server.py` module implements a `__setattr__` hook to proxy attribute writes to a centralized `state` object:

```python
def __setattr__(name: str, value: Any) -> None:
    if name in _STATE_ATTRS:
        setattr(state, name, value)
    else:
        globals()[name] = value
```

**However, Python's module-level `__setattr__` is NOT invoked for external assignments.**

When `app.py:_initialize_globals()` executed:
```python
server.request_queue = Queue()
```

This wrote directly to `server.__dict__["request_queue"]`, bypassing the `__setattr__` hook entirely. As a result, `state.request_queue` remained `None`.

### Evidence

```python
>>> import server
>>> from api_utils.server_state import state
>>> import asyncio
>>> server.request_queue = asyncio.Queue()
>>> server.__dict__["request_queue"]
<Queue maxsize=0>
>>> state.request_queue
None  # Should be the Queue!
```

### Secondary Issue: Dangerous Fallback Initialization

The `queue_worker()` function (lines 771-789) had fallback code that would create a **local** queue if the imported one was None:

```python
if request_queue is None:
    request_queue = Queue()  # Creates LOCAL variable, not shared!
```

This creates a new local queue that shadows the imported one, causing the worker to use a different queue than the router.

---

## Evidence

### Before Fix
```
server.__dict__["request_queue"]: <Queue maxsize=0>
state.request_queue: None
Same object? False
```

### After Fix
```
server.__dict__["request_queue"]: <Queue maxsize=0>
state.request_queue: <Queue maxsize=0>
Same object? True
```

---

## Fix Details

### File: `api_utils/app.py`

Changed `_initialize_globals()` to write directly to `state` first, then sync to `server.__dict__`:

```python
def _initialize_globals():
    import server
    from api_utils.server_state import state

    # CRITICAL FIX: Write directly to state AND server.__dict__
    # Module-level __setattr__ is NOT invoked for external assignments,
    # so we must update both locations to maintain compatibility.
    state.request_queue = Queue()
    state.processing_lock = Lock()
    state.model_switching_lock = Lock()
    state.params_cache_lock = Lock()

    # Also update server.__dict__ for backward compatibility
    server.__dict__["request_queue"] = state.request_queue
    server.__dict__["processing_lock"] = state.processing_lock
    server.__dict__["model_switching_lock"] = state.model_switching_lock
    server.__dict__["params_cache_lock"] = state.params_cache_lock

    # Initialize model_list_fetch_event
    state.model_list_fetch_event = asyncio.Event()
    server.__dict__["model_list_fetch_event"] = state.model_list_fetch_event
    
    # ... rest of function
```

### File: `api_utils/queue_worker.py`

Replaced dangerous fallback initialization with explicit validation:

```python
async def queue_worker() -> None:
    """Queue worker, processes tasks in the request queue"""
    from server import (
        logger, request_queue, processing_lock, model_switching_lock,
        params_cache_lock
    )
    from config.global_state import GlobalState
    
    logger.info("--- Queue Worker Started ---")
    
    # Validate that required globals are initialized
    # If any are None, it indicates a startup sequence error
    if request_queue is None:
        logger.critical("FATAL: request_queue is None! Initialization failed.")
        raise RuntimeError("request_queue not initialized - check _initialize_globals()")
    
    # ... similar checks for other locks
```

---

## Verification

Test output after fix:

```
state.request_queue: <Queue maxsize=0>
server.__dict__["request_queue"]: <Queue maxsize=0>
Same? True
Put item. Queue size: 1, state.request_queue.qsize(): 1
AIStudioProxyServer - --- Queue Worker Started ---
AIStudioProxyServer - [test123] (Worker) Request dequeued. Mode: Non-streaming
Queue size after worker run: 0
```

---

## Files Modified

1. `api_utils/app.py` - Fixed `_initialize_globals()` to properly sync state
2. `api_utils/queue_worker.py` - Replaced fallback init with validation checks

---

## Prevention Recommendations

1. **Remove module-level variables from `server.py`**: The pattern of having both module-level variables AND a `__getattr__`/`__setattr__` proxy is fragile. Consider removing the module-level declarations (lines 110-134) and relying purely on the proxy mechanism.

2. **Add startup validation**: Add an assertion in the lifespan that validates `state.request_queue is server.__dict__["request_queue"]` to catch sync issues early.

3. **Consider using a proper singleton pattern**: Instead of the current split architecture, use a single source of truth (the `state` object) and have `server.py` only re-export from it.

4. **Add type annotations**: The 120+ Pyright errors indicate missing/incorrect type annotations. Adding proper types would catch many issues at development time.

---

## Related Issues

- The `QueueManager` class (lines 21-757 of queue_worker.py) correctly uses `state.request_queue` but is NOT used in production (only in tests)
- The standalone `queue_worker()` function (lines 759-1422) is what's actually called in production

---

## Technical Details

### Python Module `__setattr__` Behavior

Unlike class `__setattr__`, module-level `__setattr__` is only called when:
1. Code **inside** the module does an assignment
2. NOT when external code does `module.attr = value`

For external assignments, Python directly updates `module.__dict__[attr]` without calling any hooks.

This is documented Python behavior but is a common source of bugs when trying to implement proxy patterns at the module level.
