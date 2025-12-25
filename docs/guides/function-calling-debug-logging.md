# Function Calling Debug Logging Guide

This guide explains how to use the modular debug logging system for Function Calling (FC) in the AI Studio Proxy. This system provides granular control over logging for different components of the function calling pipeline, making it easier to diagnose issues without being overwhelmed by massive log files.

**Related Documentation:**
- [FC Debug Logging Architecture](../architecture/FC_DEBUG_LOGGING_DESIGN.md)
- [Native Function Calling Architecture](../architecture/ADR-001-native-function-calling.md)

---

## 1. Overview

The Function Calling subsystem involves multiple complex steps: schema conversion, cache management, UI automation, DOM parsing, and response formatting. Previously, all these logs were mixed into the main application log, making debugging difficult.

The new **Modular FC Debug Logging** system allows you to:
- **Isolate** logs for specific components (e.g., only see Cache logs).
- **Separate** logs into dedicated files (e.g., `logs/fc_debug/fc_cache.log`).
- **Truncate** large payloads (like tool definitions) to keep logs readable.
- **Trace** requests across modules using a unique Request ID.

---

## 2. Quick Start

To enable full debug logging for all function calling components, add the following to your `.env` file:

```bash
# Master switch
FC_DEBUG_ENABLED=true

# Enable all modules
FC_DEBUG_ORCHESTRATOR=true
FC_DEBUG_UI=true
FC_DEBUG_CACHE=true
FC_DEBUG_WIRE=true
FC_DEBUG_DOM=true
FC_DEBUG_SCHEMA=true
FC_DEBUG_RESPONSE=true

# Optional: View all FC logs in one file
FC_DEBUG_COMBINED_LOG=true
```

Restart the server. Logs will appear in `logs/fc_debug/`.

---

## 3. Configuration Reference

All configuration is handled via environment variables in your `.env` file.

### Master Switch
| Variable | Default | Description |
|----------|---------|-------------|
| `FC_DEBUG_ENABLED` | `false` | Master kill switch. If `false`, all FC logging is disabled regardless of other settings. |

### Module Toggles
Enable specific modules to generate logs for them.

| Variable | Default | Description |
|----------|---------|-------------|
| `FC_DEBUG_ORCHESTRATOR` | `false` | High-level flow, mode selection, fallback logic. |
| `FC_DEBUG_UI` | `false` | Browser UI interactions (toggles, dialogs, button clicks). |
| `FC_DEBUG_CACHE` | `false` | Cache hits, misses, digest validation. |
| `FC_DEBUG_WIRE` | `false` | Network response parsing (wire format). |
| `FC_DEBUG_DOM` | `false` | HTML DOM extraction of function calls. |
| `FC_DEBUG_SCHEMA` | `false` | Conversion between OpenAI tools and Gemini tools. |
| `FC_DEBUG_RESPONSE` | `false` | Formatting the final response for the client. |

### Log Levels
Set the verbosity for each module (`DEBUG`, `INFO`, `WARNING`, `ERROR`).

| Variable | Default | Description |
|----------|---------|-------------|
| `FC_DEBUG_LEVEL_ORCHESTRATOR` | `DEBUG` | |
| `FC_DEBUG_LEVEL_UI` | `DEBUG` | |
| `FC_DEBUG_LEVEL_CACHE` | `DEBUG` | |
| `FC_DEBUG_LEVEL_WIRE` | `DEBUG` | |
| `FC_DEBUG_LEVEL_DOM` | `DEBUG` | |
| `FC_DEBUG_LEVEL_SCHEMA` | `DEBUG` | |
| `FC_DEBUG_LEVEL_RESPONSE` | `DEBUG` | |

### Output Options
| Variable | Default | Description |
|----------|---------|-------------|
| `FC_DEBUG_COMBINED_LOG` | `false` | If `true`, writes all enabled FC logs to `logs/fc_debug/fc_combined.log` in addition to individual files. |

---

## 4. Module Guide

| Module | Use When... | Log File |
|--------|-------------|----------|
| **ORCHESTRATOR** | You want to trace the overall request flow, understand why "native" or "emulated" mode was chosen, or debug fallback logic. | `fc_orchestrator.log` |
| **UI** | The browser automation seems to be failing (e.g., buttons not clicked, dialogs not opening). | `fc_ui.log` |
| **CACHE** | You suspect tools are not being updated, or you want to verify if cache hits are working properly. | `fc_cache.log` |
| **WIRE** | The server is receiving data from Google but failing to parse the raw network protocol. | `fc_wire.log` |
| **DOM** | The UI shows a function call but the proxy isn't detecting it from the page HTML. | `fc_dom.log` |
| **SCHEMA** | You have errors related to tool definitions or parameter validation. | `fc_schema.log` |
| **RESPONSE** | The client (e.g., SillyTavern) is receiving malformed JSON or invalid tool call formats. | `fc_response.log` |

---

## 5. Common Debugging Scenarios

### Scenario: "Tool not recognized" or "Invalid tool format"
**Enable:** `SCHEMA`, `DOM`
**Why:** Check `fc_schema.log` to see how your tools were converted. Check `fc_dom.log` to see what the model actually outputted.

### Scenario: "Function call not detected" (Model outputs text instead of call)
**Enable:** `WIRE`, `DOM`
**Why:** The model might have generated the call, but the proxy missed it. `fc_wire.log` shows the raw network events. `fc_dom.log` shows if the parser found the function call block in the HTML.

### Scenario: "Cache issues" (Old tools persisting)
**Enable:** `CACHE`
**Why:** `fc_cache.log` will show Digest Mismatches (`MISS`) if the tools have changed, or `HIT` if they are being reused.

### Scenario: "UI automation failing" (Timeouts, stuck on "Processing")
**Enable:** `UI`
**Why:** `fc_ui.log` details every click, check, and wait operation. Look for "Element not found" or long durations.

### Scenario: "Schema conversion errors"
**Enable:** `SCHEMA`
**Why:** `fc_schema.log` will show the input tools from the client and the converted schema sent to Google.

---

## 6. Log File Locations and Rotation

Logs are stored in: `logs/fc_debug/`

- **Rotation:** Files are rotated automatically when they reach **5MB**.
- **History:** Up to **3** backup files are kept (e.g., `fc_cache.log`, `fc_cache.log.1`, `fc_cache.log.2`).
- **Configuration:**
  - `FC_DEBUG_LOG_MAX_BYTES` (default: 5242880)
  - `FC_DEBUG_LOG_BACKUP_COUNT` (default: 3)

---

## 7. Payload Truncation

Function calling payloads can be huge (10KB+ for complex tool definitions). To keep logs readable, the system truncates large fields by default.

**Configuration:**
- `FC_DEBUG_TRUNCATE_ENABLED=true` (Default)

**Limits:**
- **Tool Definitions:** Summarized as `tool_name(N params)`
- **Arguments:** First 1000 chars + summary
- **Responses:** First 2000 chars + summary

**Disable Truncation:**
Set `FC_DEBUG_TRUNCATE_ENABLED=false` to see full payloads (useful for inspecting exact JSON structure).

---

## 8. Reading the Logs

**Format:**
`YYYY-MM-DD HH:MM:SS.mmm | LEVEL | [RequestID] [FC:MODULE] Message`

**Example:**
```text
2025-12-25 14:32:15.123 | DEBUG   | [abc123] [FC:CACHE] HIT - digest=a1b2c3d4..., age=5.2s
```

- **Timestamp:** Local time (America/Chicago by default)
- **Level:** DEBUG, INFO, WARNING, ERROR
- **RequestID:** `[abc123]` - Use this to correlate logs across different files for the same request.
- **Module:** `[FC:CACHE]` - Indicates the source module.

---

## 9. Troubleshooting Tips

1. **No logs appearing?**
   - Check `FC_DEBUG_ENABLED=true`.
   - Check if the specific module is enabled (e.g., `FC_DEBUG_CACHE=true`).
   - Ensure the server was restarted after changing `.env`.

2. **Logs are too verbose?**
   - Increase the log level: `FC_DEBUG_LEVEL_WIRE=INFO` (hides DEBUG messages).
   - Enable truncation: `FC_DEBUG_TRUNCATE_ENABLED=true`.

3. **Cannot trace a request?**
   - Enable `FC_DEBUG_COMBINED_LOG=true` to see the sequence of events in one file.
   - Grep for the Request ID: `grep "abc123" logs/fc_debug/*.log`

---

## 10. Example Log Output

### Orchestrator (`fc_orchestrator.log`)
```text
2025-12-25 10:00:01.123 | INFO    | [req-001] [FC:ORCH] Mode=native, reason=tools present
2025-12-25 10:00:01.125 | DEBUG   | [req-001] [FC:ORCH] Native execution started
```

### Cache (`fc_cache.log`)
```text
2025-12-25 10:00:01.130 | DEBUG   | [req-001] [FC:CACHE] Checking cache validity
2025-12-25 10:00:01.135 | DEBUG   | [req-001] [FC:CACHE] MISS - reason=digest mismatch
```

### Schema (`fc_schema.log`)
```text
2025-12-25 10:00:01.140 | INFO    | [req-001] [FC:SCHEMA] Converted 3 tools in 2.50ms
2025-12-25 10:00:01.142 | DEBUG   | [req-001] [FC:SCHEMA] Tool summary: [get_weather(2 params), search_web(1 params)]
```

### UI (`fc_ui.log`)
```text
2025-12-25 10:00:02.100 | DEBUG   | [req-001] [FC:UI] check_toggle enabled=True (120ms)
2025-12-25 10:00:02.500 | DEBUG   | [req-001] [FC:UI] click run_button (50ms)
```

### DOM (`fc_dom.log`)
```text
2025-12-25 10:00:05.100 | DEBUG   | [req-001] [FC:DOM] Extracted 1 call(s) via native_chunk
2025-12-25 10:00:05.105 | DEBUG   | [req-001] [FC:DOM] Call 1: get_weather
```

### Response (`fc_response.log`)
```text
2025-12-25 10:00:05.200 | DEBUG   | [req-001] [FC:RESP] Formatted 1 tool calls, finish_reason=tool_calls
```
