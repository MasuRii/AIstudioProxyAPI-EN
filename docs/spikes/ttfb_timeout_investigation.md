# TTFB Timeout Investigation When Streaming is Disabled

This document outlines the investigation into the Time To First Byte (TTFB) timeout issue observed when the streaming feature is disabled.

## 1. Root Cause Analysis

The investigation identified two primary contributing factors to the timeout issue, with one being a critical code bug:

### Primary Cause: Inconsistent Timeout Application (Bug)
A discrepancy exists in how the **Time To First Byte (TTFB)** timeout is applied between streaming and non-streaming paths.
*   **Streaming Path:** Calculates a `dynamic_timeout` based on prompt length (Base 5s + 1s per 1000 chars) and correctly passes this to the stream handler.
*   **Non-Streaming Path:** Calculates the same `dynamic_timeout` but **fails to pass it** to the `use_stream_response` function. Consequently, the non-streaming path falls back to the default **5.0 seconds** timeout.

**Impact:** If a model takes longer than 5 seconds to generate the first token (common with long prompts or "Thinking" models), the non-streaming request will fail with a server-side TTFB timeout (resulting in a 502 error), while the same request would succeed in streaming mode (which might have a 10s+ timeout).

### Secondary Cause: Architecture Inherent Latency
By definition, a non-streaming request (`stream=false`) requires the server to buffer the **entire** response before sending the first byte of the HTTP body to the client.
*   **Streaming:** Client receives the first token within seconds (TTFB ~ Generation Start Time).
*   **Non-Streaming:** Client receives nothing until generation is complete (TTFB = Total Generation Time).
*   **Impact:** Even if the server-side 5s bug is fixed, clients with short read timeouts (e.g., 30s) will still timeout on long generations because they receive no "Keep-Alive" data during the generation process.

## 2. Execution Path Analysis

### Streaming Request Flow (`stream=True`)
1.  **Entry:** `_process_request_refactored` calculates `dynamic_timeout`.
2.  **Handler:** Calls `_handle_auxiliary_stream_response`.
3.  **Generator:** Calls `gen_sse_from_aux_stream` passing `timeout=dynamic_timeout`.
4.  **Stream Consumer:** Calls `use_stream_response(..., timeout=timeout)`.
5.  **Result:** The stream listener waits for up to `dynamic_timeout` (e.g., 15s) for the first token.

### Non-Streaming Request Flow (`stream=False`)
1.  **Entry:** `_process_request_refactored` calculates `dynamic_timeout`.
2.  **Handler:** Calls `_handle_auxiliary_stream_response`.
3.  **Loop:** Iterates directly over `use_stream_response`.
    ```python
    # api_utils/request_processor.py
    async for raw_data in use_stream_response(req_id, page=page, check_client_disconnected=check_client_disconnected):
        # MISSING: timeout=timeout
    ```
4.  **Defaulting:** `use_stream_response` uses its default `timeout=5.0`.
5.  **Result:** The stream listener aborts if the first token doesn't arrive within **5.0 seconds**, ignoring the dynamic calculation meant to handle complex prompts.

## 3. Reproduction Steps

1.  **Configure Server:** Ensure `STREAM_PORT` is active (default).
2.  **Prepare Request:** Create a request with a significantly long prompt (e.g., 5000+ characters) or instructions that require a long "Thinking" pause before outputting text.
    *   *Example:* "Read this long context [insert 5k text] and wait 7 seconds before answering."
3.  **Test Streaming:** Send with `stream=True`. Observe it succeeds (first token arrives in ~6-7s).
4.  **Test Non-Streaming:** Send with `stream=False`.
5.  **Observation:** The non-streaming request will fail after exactly 5 seconds with a 502 Bad Gateway (caused by internal TTFB timeout), whereas the streaming request continues.

## 4. Recommendations

### Solution A: Fix Timeout Parameter Passing (Critical)
Update `api_utils/request_processor.py` to pass the calculated `timeout` to `use_stream_response` in the non-streaming branch.

*   **Location:** `api_utils/request_processor.py`, inside `_handle_auxiliary_stream_response`.
*   **Change:**
    ```python
    # Before
    async for raw_data in use_stream_response(req_id, page=page, check_client_disconnected=check_client_disconnected):

    # After
    async for raw_data in use_stream_response(req_id, timeout=timeout, page=page, check_client_disconnected=check_client_disconnected):
    ```
*   **Pros:** Immediately resolves the inconsistency; enables non-streaming requests to handle long prompts/thinking time just like streaming ones.
*   **Cons:** None.
*   **Complexity:** Very Low (1 line change).

### Solution B: Client Configuration Advisory
Update documentation to advise users that `stream=False` requires significantly higher client-side read timeouts.

*   **Action:** Add a "Timeout Configuration" section to `README.md` or `docs/troubleshooting.md`.
*   **Pros:** manages user expectations regarding the inherent latency of non-streaming LLM responses.
*   **Cons:** Does not fix the server-side bug identified in Solution A.
*   **Complexity:** Low (Documentation only).

### Solution C: Pseudo-Streaming (Advanced)
Implement a "Keep-Alive" mechanism for non-streaming requests, where the server sends periodic whitespace characters to keep the HTTP connection active while buffering the JSON response.

*   **Implementation:** requires changing `response_class` or manual socket management in FastAPI, as standard `JSONResponse` assumes a single atomic body.
*   **Pros:** Prevents load balancer/proxy timeouts (e.g., Cloudflare 100s limit).
*   **Cons:** High complexity; strictly speaking violates JSON content-type if whitespaces are sent before the body (though often tolerated).
*   **Complexity:** High.

**Recommendation:** Implement **Solution A** immediately as it is a clear bug fix. Adopt **Solution B** as standard practice.