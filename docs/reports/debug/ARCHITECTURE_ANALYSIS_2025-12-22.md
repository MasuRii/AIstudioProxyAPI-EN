# Architecture Analysis: Request Processing Flow
**Date:** 2025-12-22
**Focus:** Debugging Camoufox Browser Automation Failure

## 1. High-Level Architecture
The system operates as a proxy server that translates OpenAI-compatible API requests into browser actions on Google AI Studio. It uses a "Headless Browser" approach where a persistent browser session is controlled via Playwright.

**Core Components:**
1.  **Launcher (`launch_camoufox.py`)**: Orchestrates the startup of the Camoufox browser (subprocess) and the FastAPI server (Uvicorn).
2.  **API Layer (`server.py`, `api_utils/`)**: FastAPI application handling HTTP/WebSocket requests.
3.  **Queue System (`api_utils/queue_worker.py`)**: Serializes concurrent API requests into a single-threaded browser execution stream.
4.  **Browser Controller (`browser_utils/`)**: Playwright automation scripts interacting with the AI Studio DOM.

## 2. Request Processing Flow (Step-by-Step)

### Phase 1: Ingestion
1.  **Client Request**: POST request arrives at `/v1/chat/completions`.
2.  **Validation (`routers/chat.py`)**:
    *   Checks `server_state` flags: `is_initializing`, `is_playwright_ready`, `is_page_ready`, `worker_task`.
    *   **Failure Point A:** If any flag is False, returns 503 Service Unavailable immediately.
3.  **Queueing**:
    *   Creates a `Future` object (`result_future`) to track the async result.
    *   Wraps request + future into a `QueueItem`.
    *   Pushes item to `request_queue`.
    *   Awaits `result_future` (with timeout).

### Phase 2: Processing (The Bottleneck)
The `queue_worker` (background task started in `lifespan`) runs an infinite loop:
1.  **Dequeue**: Pulls the next item from `request_queue`.
2.  **Pre-Flight Checks**:
    *   Checks client disconnection.
    *   Checks `GlobalState.IS_QUOTA_EXCEEDED` or `NEEDS_ROTATION`. If true, pauses for Auth Rotation.
3.  **Locking**: Acquires `processing_lock`. **Crucial:** Only one request processes at a time.
4.  **Execution Delegate**: Calls `_process_request_refactored` (`request_processor.py`).

### Phase 3: Browser Automation
Inside `_process_request_refactored`:
1.  **Context**: Validates `page` object existence and state (`!page.is_closed()`).
2.  **Model Switching**: `_handle_model_switching` verifies/changes the selected model in UI.
3.  **Parameter Injection**: `PageController.adjust_parameters` sets temp, top_p, etc.
4.  **Prompt Submission**:
    *   `PageController.submit_prompt` fills the text area and clicks the submit button.
    *   **Failure Point B**: If selectors (`PROMPT_TEXTAREA_SELECTOR`, `SUBMIT_BUTTON_SELECTOR`) don't match the current Google UI, this fails.
5.  **Response Polling**:
    *   `_handle_response_processing` triggers a wait loop.
    *   `_wait_for_response_completion` polls for the "Edit" button to appear or the "Stop generating" button to disappear.
    *   **Failure Point C**: If the UI changes or the network lags, this times out.

### Phase 4: Extraction & Response
1.  **Extraction**: `_get_final_response_content` scrapes the DOM or uses the "Edit" button data-value to get the text.
2.  **Streaming**: If streaming, `resilient_stream_generator` yields chunks as they appear (hooked into `stream/` proxy or DOM polling).
3.  **Completion**: The `result_future` is set with the final JSON or Stream response.
4.  **Cleanup**: `queue_worker` releases `processing_lock` and triggers chat history clearing.

## 3. Key Integration & Failure Points

Based on the code analysis, here are the specific areas why automation might fail despite the server running:

| Component | Mechanism | Potential Failure Mode | Symptoms |
|-----------|-----------|------------------------|----------|
| **Launch** | `launch_camoufox.py` | Browser process crash or detach | Server runs, but `browser_instance.is_connected()` becomes False. |
| **Connection** | `server.py` | `CAMOUFOX_WS_ENDPOINT` handshake | If WS URL is stale/wrong, Playwright cannot connect. API returns 503. |
| **Worker** | `queue_worker.py` | `processing_lock` | **Deadlock**: If a previous request crashed *inside* the lock without cleaning up (unlikely due to `async with`, but possible with zombie tasks), new requests sit in queue forever. |
| **Selectors** | `config.py` | CSS/XPath Selectors | **UI Drift**: Google changes a class name. `submit_prompt` fails to find the button. Worker logs "Timeout" or "Element not found". |
| **State** | `server_state.py` | Global Variables | **Desync**: `is_page_ready` might be True, but the actual Page object is crashed/closed. |

## 4. Diagnostics Checklist

To debug "requests not processing", check these specific logs/states:

1.  **Lock State**: Is the `queue_worker` waiting for `processing_lock`? (Search logs for "Waiting for processing lock...").
2.  **Browser Visibility**: In `launch_camoufox.py`, is `CAMOUFOX_WS_ENDPOINT` captured correctly?
3.  **Selector Timeouts**: Look for `TimeoutError` in `PageController.submit_prompt` or `_wait_for_response_completion`.
4.  **Zombie Page**: Does `page.is_closed()` return True?

## 5. Summary
The architecture is robust against simple failures (retries, timeouts) but fragile regarding **DOM coupling** and **Single-Threaded Blocking**. A single stuck request holds up the entire queue. The system relies heavily on the "happy path" of the Google AI Studio UI remaining constant.
