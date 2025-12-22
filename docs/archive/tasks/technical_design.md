# Technical Design: Stream Instability & FAIL-FAST Fixes

## 1. Executive Summary
This document outlines the technical design to resolve stream instability, premature disconnects ("FAIL-FAST"), and race conditions in the AI Studio Proxy. The core issues stem from conflicting timeout logic in `stream.py` where a hardcoded 90-second limit overrides the configured dynamic timeout (often 5+ minutes), and from aggressive silence detection that fails to account for "thinking" models. The solution involves unifying the timeout logic, making silence detection dynamic, and restoring the authority of the UI state ("Stop generating" button) to prevent killing active streams.

## 2. Root Cause Analysis Recap
1.  **Timeout Logic Conflict**: In `api_utils/utils_ext/stream.py`, `max_empty_retries` is hardcoded to 900 ticks (90s). `initial_wait_limit` (TTFB timeout) is derived from the passed `timeout` (e.g., 300s -> 3000 ticks). However, the general timeout check `if empty_count >= max_empty_retries` executes unconditionally, effectively capping TTFB at 90s regardless of the configuration.
2.  **Aggressive Silence Detection**: The silence threshold is static (default 60s). Large "thinking" models or heavy payloads often pause for longer than this, triggering a premature "silence_detected" signal.
3.  **UI State Ignored**: The current logic explicitly ignores the UI state (`check_ui_generation_active`) when the timeout is reached (`CRITICAL FIX: Remove UI-based timeout extension`), killing valid streams even if the browser is clearly busy generating.
4.  **Done Signal Synchronization**: Premature termination in `stream.py` sends a `done: True` signal to `response_generators.py`, causing it to finalize the response. Late-arriving data is then discarded as "extraneous".

## 3. Proposed Solution

### 3.1. `api_utils/utils_ext/stream.py` Modifications

**Objective**: Unify timeout logic and respect UI state.

1.  **Dynamic `max_empty_retries`**:
    *   Change `max_empty_retries` from a hardcoded constant (900) to a value derived from the `timeout` parameter or a new `silence_threshold` parameter.
    *   Ensure `max_empty_retries` is always $\ge$ `initial_wait_limit` to prevent the general timeout from undercutting the TTFB timeout.

2.  **Smart Timeout Logic**:
    *   Refactor the timeout check to distinguish between **TTFB Phase** (0 items received) and **Streaming Phase** (>0 items received).
    *   **TTFB Phase**: Use `initial_wait_limit`.
    *   **Streaming Phase**: Use `max_empty_retries` (derived from `silence_threshold`).

3.  **Restore UI Trust (The "Thinking" Fix)**:
    *   In the timeout block, re-enable the UI activity check.
    *   If `check_ui_generation_active()` returns `True`:
        *   Log a warning ("Timeout reached but UI active...").
        *   **Action**: Reset `empty_count` to 0 (or reduce it) to "snooze" the timeout, effectively extending the wait as long as the UI reports activity.
        *   Add a `hard_timeout_limit` (e.g., 2x or 3x the original timeout) to prevent infinite zombie loops if the UI gets stuck.

4.  **Dynamic Silence Threshold**:
    *   Update `use_stream_response` signature to accept `silence_threshold: float`.
    *   Use this passed value instead of the global constant `SILENCE_TIMEOUT_MS`.

### 3.2. `api_utils/request_processor.py` Modifications

**Objective**: Calculate and propagate dynamic timeouts.

1.  **Calculate Silence Threshold**:
    *   In `_process_request_refactored`, calculate a `dynamic_silence_threshold`.
    *   Base logic: `max(DEFAULT_SILENCE (60s), dynamic_timeout / 2)`.
    *   This ensures that if we allow a 5-minute request, we also allow for significant pauses (e.g., 2.5 mins) without assuming death.

2.  **Propagate Parameters**:
    *   Pass `dynamic_silence_threshold` down the chain:
        *   `_handle_response_processing`
        *   `_handle_auxiliary_stream_response`
        *   `gen_sse_from_aux_stream`
        *   `use_stream_response`

### 3.3. `api_utils/response_generators.py` Modifications

**Objective**: Pass-through new parameters.

1.  Update `gen_sse_from_aux_stream` to accept `silence_threshold` and pass it to `use_stream_response`.

## 4. Implementation Plan

### Step 1: Update `stream.py`
*   Modify `use_stream_response` signature.
*   Remove hardcoded `max_empty_retries = 900`.
*   Implement `effective_timeout_limit` logic:
    ```python
    # Pseudo-code
    effective_limit = initial_wait_limit if received_items_count == 0 else silence_wait_limit
    ```
*   Implement UI-based "Snooze" logic in the timeout block.

### Step 2: Update `response_generators.py`
*   Update `gen_sse_from_aux_stream` signature to accept `silence_threshold`.
*   Pass it to `use_stream_response`.

### Step 3: Update `request_processor.py`
*   Calculate `dynamic_silence_threshold`.
*   Pass it through the function call chain.

### Step 4: Verification
*   **Log Verification**: Check logs for "Extended timeout due to active UI" messages.
*   **TTFB Test**: Verify that `timeout=300` results in a 300s wait for the first byte, not 90s.
*   **Thinking Test**: Simulate a model pause > 60s and ensure the stream stays alive.

## 5. Risk Assessment
*   **Zombie Processes**: Trusting the UI state ("Stop generating" button) carries the risk of keeping a connection open indefinitely if the browser hangs.
    *   *Mitigation*: Implement a `hard_limit_multiplier` (e.g., max 10 minutes total) even if UI is active.
*   **Memory Usage**: Extending timeouts increases the duration `accumulated_body` is held in memory.
    *   *Mitigation*: Python handles string appending efficiently enough for typical context sizes.

## 6. Artifacts to be Created/Modified
*   `api_utils/utils_ext/stream.py` (Modified)
*   `api_utils/request_processor.py` (Modified)
*   `api_utils/response_generators.py` (Modified)