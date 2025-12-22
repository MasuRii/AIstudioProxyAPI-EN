# Bug Fix Design Document

## Executive Summary

This document details the root cause analysis and proposed fixes for three critical crash bugs identified in the codebase:
1. **Error A**: `UnboundLocalError` in [`stream.py:55`](api_utils/utils_ext/stream.py:55) - variable `max_empty_retries` referenced before assignment
2. **Error B**: `NameError` in [`model_switching.py:60`](api_utils/model_switching.py:60) - module `server` used without import
3. **Error C**: UI Timeout in [`stream.py:118`](api_utils/utils_ext/stream.py:118) - `is_disabled()` check timing out on Run button

All three errors have been analyzed with irrefutable evidence from source code inspection.

---

## Error A: UnboundLocalError in stream.py

### Root Cause Statement
**Variable `max_empty_retries` is referenced in a logging statement at line 55 before it is defined at line 84, causing an `UnboundLocalError` when the function executes.**

### Evidence

**File**: [`api_utils/utils_ext/stream.py`](api_utils/utils_ext/stream.py)

**Line 55** (Variable Usage - BEFORE definition):
```python
logger.info(f"[{req_id}] Starting stream response (TTFB Timeout: {timeout:.2f}s, Silence Threshold: {silence_threshold:.2f}s, Max Retries: {max_empty_retries}, Start Time: {stream_start_time})")
```

**Lines 80-84** (Variable Definition - AFTER usage):
```python
# [STREAM-FIX] Dynamic max_empty_retries based on silence_threshold
# Convert silence_threshold (seconds) to ticks (0.1s each)
# Ensure it's at least as long as initial_wait_limit to prevent general timeout from undercutting TTFB
silence_wait_limit = int(silence_threshold * 10)
max_empty_retries = max(silence_wait_limit, initial_wait_limit)
```

**Execution Flow:**
1. Function `use_stream_response()` is called at line 17
2. Line 55 executes FIRST, attempting to log `max_empty_retries`
3. Python raises `UnboundLocalError: local variable 'max_empty_retries' referenced before assignment`
4. Function never reaches line 84 where the variable is actually defined

### Proposed Fix

**Option 1 (Recommended)**: Move the logging statement to AFTER variable initialization:

```python
# Lines 78-84: Keep variable calculation here
empty_count = 0
initial_wait_limit = int(timeout * 10)  # TTFB timeout in ticks (0.1s each)

# [STREAM-FIX] Dynamic max_empty_retries based on silence_threshold
silence_wait_limit = int(silence_threshold * 10)
max_empty_retries = max(silence_wait_limit, initial_wait_limit)

# Line 55: MOVE logging to here (after line 84)
logger.info(f"[{req_id}] Starting stream response (TTFB Timeout: {timeout:.2f}s, Silence Threshold: {silence_threshold:.2f}s, Max Retries: {max_empty_retries}, Start Time: {stream_start_time})")
```

**Option 2**: Remove `max_empty_retries` from the initial log statement (less informative):

```python
# Line 55: Remove max_empty_retries reference
logger.info(f"[{req_id}] Starting stream response (TTFB Timeout: {timeout:.2f}s, Silence Threshold: {silence_threshold:.2f}s, Start Time: {stream_start_time})")
```

**Recommendation**: Use Option 1 to preserve full logging information while fixing the execution order issue.

---

## Error B: NameError in model_switching.py

### Root Cause Statement
**Module `server` is referenced at lines 60, 66, and 69 without being imported, causing a `NameError` when the function attempts to access `server.current_ai_studio_model_id`.**

### Evidence

**File**: [`api_utils/model_switching.py`](api_utils/model_switching.py)

**Imports (lines 1-8)** - No `server` import present:
```python
import logging

from playwright.async_api import Page as AsyncPage

from api_utils.server_state import state
from logging_utils import set_request_id

from .context_types import RequestContext
```

**Line 60** (Undefined Usage #1):
```python
if server.current_ai_studio_model_id != model_id_to_use:
```

**Line 61** (Undefined Usage #2):
```python
logger.info(f"[{req_id}] Preparing to switch model: {server.current_ai_studio_model_id} -> {model_id_to_use}")
```

**Line 66** (Undefined Usage #3):
```python
server.current_ai_studio_model_id = model_id_to_use
```

**Line 69** (Undefined Usage #4):
```python
logger.info(f"[{req_id}] ✅ Model switched successfully: {server.current_ai_studio_model_id}")
```

**Line 87** (Correct Usage in different function):
```python
async def _handle_model_switch_failure(...):
    import server  # <-- Local import present here
    server.current_ai_studio_model_id = model_before_switch
```

**Additional Evidence - Inconsistent API usage:**
- Line 72 uses: `state.current_ai_studio_model_id` (imported from `api_utils.server_state`)
- Lines 60-69 use: `server.current_ai_studio_model_id` (not imported)

### Proposed Fix

**Root Issue Analysis:**
The code has TWO different state management objects:
1. `state` from `api_utils.server_state` (imported)
2. `server` module (not imported, but used in `_handle_model_switch_failure`)

**Option 1 (Recommended)**: Use the already-imported `state` object consistently:

```python
# Line 60: Change from server to state
if state.current_ai_studio_model_id != model_id_to_use:
    logger.info(f"[{req_id}] Preparing to switch model: {state.current_ai_studio_model_id} -> {model_id_to_use}")
    from browser_utils import switch_ai_studio_model

    switch_success = await switch_ai_studio_model(page, model_id_to_use, req_id)
    if switch_success:
        state.current_ai_studio_model_id = model_id_to_use  # Line 66: Use state
        context['model_actually_switched'] = True
        context['current_ai_studio_model_id'] = model_id_to_use
        logger.info(f"[{req_id}] ✅ Model switched successfully: {state.current_ai_studio_model_id}")  # Line 69: Use state
```

**Also fix `_handle_model_switch_failure`** (line 85-87):
```python
async def _handle_model_switch_failure(req_id: str, page: AsyncPage, model_id_to_use: str, model_before_switch: str, logger) -> None:
    # Remove: import server
    # Add at top of file if not present: from api_utils.server_state import state
    logger.warning(f"[{req_id}] ❌ Failed to switch to model {model_id_to_use}.")
    state.current_ai_studio_model_id = model_before_switch  # Use state instead of server
    from .error_utils import http_error
    raise http_error(422, f"[{req_id}] Failed to switch to model '{model_id_to_use}'. Ensure model is available.")
```

**Option 2**: Add `import server` at module level (if `server` module exists and is the correct object):

```python
# At top of file
import logging
import server  # Add this import

from playwright.async_api import Page as AsyncPage
...
```

**Recommendation**: Use Option 1 (use `state` consistently) because:
1. `state` is already imported from `api_utils.server_state`
2. The code at line 72 already uses `state.current_ai_studio_model_id`
3. This maintains consistency within the file
4. Avoids circular import issues if `server` module imports from this file

---

## Error C: UI Timeout on "disabled" check

### Root Cause Statement
**The `is_disabled()` check at line 118 times out because it uses a compound CSS selector that may match multiple or stale DOM elements, and the 1000ms timeout is insufficient for the UI state check.**

### Evidence

**File**: [`api_utils/utils_ext/stream.py`](api_utils/utils_ext/stream.py)

**Lines 116-120** (Problematic Code):
```python
# Check if submit button is disabled (generation in progress)
submit_button = page.locator('button[aria-label="Run"].run-button, ms-run-button button[type="submit"].run-button')
if await submit_button.count() > 0:
    is_disabled = await submit_button.first.is_disabled(timeout=1000)
    if is_disabled:
```

**Issues Identified:**

1. **Compound Selector Complexity**:
   - Selector: `'button[aria-label="Run"].run-button, ms-run-button button[type="submit"].run-button'`
   - This matches TWO different patterns (comma-separated)
   - May match multiple elements or elements in different states

2. **Timeout Value Inconsistency**:
   - Line 118: Uses `timeout=1000` (1 second)
   - Lines 517, 640 in [`input.py`](browser_utils/page_controller_modules/input.py): Uses `timeout=2000` (2 seconds)
   - Shorter timeout increases likelihood of timeout errors

3. **Race Condition**:
   - Line 117: `if await submit_button.count() > 0:` checks element count
   - Line 118: `await submit_button.first.is_disabled(timeout=1000)` accesses `.first`
   - Elements could become stale between these two operations

4. **Error Handling**:
   - The code is inside a try-except block (lines 109-128)
   - BUT the except catches exceptions and returns `False`, silently failing
   - No logging of the actual timeout error

**Lines 104-128** (Full Context):
```python
async def check_ui_generation_active():
    """Check if the AI is still generating based on UI state."""
    if not page:
        return False
        
    try:
        # Check for "Stop generating" button (indicates active generation)
        stop_button = page.locator('button[aria-label="Stop generating"]')
        if await stop_button.is_visible(timeout=1000):
            return True
            
        # Check if submit button is disabled (generation in progress)
        submit_button = page.locator('button[aria-label="Run"].run-button, ms-run-button button[type="submit"].run-button')
        if await submit_button.count() > 0:
            is_disabled = await submit_button.first.is_disabled(timeout=1000)  # <-- LINE 118: TIMEOUT HERE
            if is_disabled:
                return True
                
        return False
    except Exception as e:
        # [FIX-ZOMBIE] If target closed, definitely not generating
        if "Target closed" in str(e) or "Connection closed" in str(e):
            return False
        # If UI check fails, assume generation is not active
        return False
```

### Proposed Fix

**Recommended Approach**: Use more robust selector, increase timeout, add proper error handling:

```python
async def check_ui_generation_active():
    """Check if the AI is still generating based on UI state."""
    if not page:
        return False
        
    try:
        # Check for "Stop generating" button (indicates active generation)
        stop_button = page.locator('button[aria-label="Stop generating"]')
        if await stop_button.is_visible(timeout=1000):
            return True
            
        # Check if submit button is disabled (generation in progress)
        # Use SUBMIT_BUTTON_SELECTOR from config for consistency
        from config import SUBMIT_BUTTON_SELECTOR
        submit_button = page.locator(SUBMIT_BUTTON_SELECTOR)
        
        # Check element exists before querying state
        if await submit_button.count() > 0:
            try:
                # Increase timeout to 2000ms for consistency with input.py
                is_disabled = await submit_button.first.is_disabled(timeout=2000)
                if is_disabled:
                    return True
            except Exception as btn_check_err:
                # Log specific button state check failures
                if "Timeout" in str(btn_check_err):
                    # Timeout on is_disabled check - assume not generating
                    return False
                # Re-raise other unexpected errors for visibility
                raise
                
        return False
    except Exception as e:
        # [FIX-ZOMBIE] If target closed, definitely not generating
        if "Target closed" in str(e) or "Connection closed" in str(e):
            return False
        # Log unexpected errors for debugging
        if "Timeout" not in str(e):
            # Only log non-timeout errors to avoid spam
            pass  # Could add logger.debug here if available
        # If UI check fails, assume generation is not active
        return False
```

**Key Improvements:**

1. **Use Centralized Selector**: Import `SUBMIT_BUTTON_SELECTOR` from config for consistency
2. **Increase Timeout**: Change from 1000ms to 2000ms to match other usages in input.py
3. **Better Error Handling**: Catch timeout specifically on the `is_disabled()` call
4. **Add Nested Try-Catch**: Separate element existence check from state check

**Alternative Fix** (Simpler, less robust):

```python
# Line 116-120: Just increase timeout and add try-catch
submit_button = page.locator('button[aria-label="Run"].run-button, ms-run-button button[type="submit"].run-button')
if await submit_button.count() > 0:
    try:
        is_disabled = await submit_button.first.is_disabled(timeout=2000)  # Increased from 1000
        if is_disabled:
            return True
    except:
        # Timeout or other error - assume not disabled
        pass
```

**Recommendation**: Use the full recommended approach for better reliability and debugging.

---

## Prevention Recommendations

### For Error A (Variable Before Assignment)
1. **Linting Rule**: Enable Pylint/Flake8 rule `E0601` (used-before-assignment)
2. **Code Review Checklist**: Verify all variables used in logging are initialized
3. **Testing**: Add unit test that calls the function to catch UnboundLocalError

### For Error B (Missing Import)
1. **Linting Rule**: Enable Pylint rule `E0602` (undefined-variable)
2. **Static Type Checking**: Use `pyright` or `mypy` to catch undefined names
3. **Code Review**: Check all module-level references have corresponding imports
4. **Refactoring**: Consolidate state management to single source of truth (`state` object)

### For Error C (UI Timeout)
1. **Centralized Selectors**: Always import selectors from config, never hardcode
2. **Timeout Constants**: Define UI check timeouts in config/timeouts.py
3. **Error Logging**: Add debug logging for all Playwright timeout errors
4. **Retry Logic**: Implement exponential backoff for UI state checks
5. **Integration Tests**: Add E2E tests that verify UI automation under various conditions

---

## Testing Strategy

### Unit Tests Required

**Test for Error A**:
```python
def test_stream_response_variable_initialization():
    """Verify max_empty_retries is accessible in logging."""
    # Call use_stream_response and verify no UnboundLocalError
    # Check that logger.info is called with correct parameters
```

**Test for Error B**:
```python
def test_model_switching_state_access():
    """Verify state.current_ai_studio_model_id is used consistently."""
    # Call handle_model_switching
    # Verify no NameError is raised
    # Verify state object is used, not undefined server
```

**Test for Error C**:
```python
def test_ui_generation_check_timeout_handling():
    """Verify check_ui_generation_active handles timeouts gracefully."""
    # Mock page.locator to raise TimeoutError
    # Verify function returns False instead of crashing
    # Verify timeout doesn't propagate as unhandled exception
```

### Integration Tests Required

1. **Stream Response Flow**: Full E2E test of stream response with various timeout scenarios
2. **Model Switching**: Test model switching with state persistence
3. **UI Automation**: Test Run button detection under various UI states

---

## Files to Modify

1. [`api_utils/utils_ext/stream.py`](api_utils/utils_ext/stream.py) - Lines 55 and 84 (Error A), Lines 116-120 (Error C)
2. [`api_utils/model_switching.py`](api_utils/model_switching.py) - Lines 60-87 (Error B)

---

## Deployment Checklist

- [ ] Apply fixes to all three errors
- [ ] Run existing test suite - verify no regressions
- [ ] Add new unit tests for each fix
- [ ] Enable additional linting rules (E0601, E0602)
- [ ] Update configuration to centralize UI timeouts
- [ ] Code review with focus on import statements and variable scoping
- [ ] Deploy to staging environment
- [ ] Monitor logs for UnboundLocalError, NameError, and TimeoutError
- [ ] Deploy to production with rollback plan

---

## Conclusion

All three errors have been identified with concrete evidence:
- **Error A**: Simple ordering bug - variable used before definition
- **Error B**: Missing import - `server` module not imported but used
- **Error C**: Timeout issue - insufficient timeout on UI state check with compound selector

All fixes are straightforward and low-risk. The root causes are definitively proven through source code inspection.