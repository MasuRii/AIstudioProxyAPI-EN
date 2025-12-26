# Environment Variables Reference

This document provides a complete reference for all environment variables in the project, including usage, type, default values, and examples.

## 📋 Table of Contents

- [Port Configuration](#port-configuration)
- [Proxy Configuration](#proxy-configuration)
- [Log Configuration](#log-configuration)
- [Authentication Configuration](#authentication-configuration)
- [Browser Configuration](#browser-configuration)
- [API Default Parameters](#api-default-parameters)
- [Timeout Configuration](#timeout-configuration)
- [GUI Launcher Configuration](#gui-launcher-configuration)
- [Script Injection Configuration](#script-injection-configuration)
- [Other Configuration](#other-configuration)
- [Stream State Configuration](#stream-state-configuration)

---

## Port Configuration

### PORT

- **Usage**: FastAPI service listening port
- **Type**: Integer
- **Default**: `2048`
- **Example**: `PORT=8000`
- **Description**: HTTP port for the main API service, all `/v1/*` endpoints are accessed via this port

### DEFAULT_FASTAPI_PORT

- **Usage**: Default FastAPI port for GUI launcher
- **Type**: Integer
- **Default**: `2048`
- **Example**: `DEFAULT_FASTAPI_PORT=3048`
- **Description**: Default port when starting via GUI or command line, used in conjunction with `PORT`

### DEFAULT_CAMOUFOX_PORT

- **Usage**: Camoufox browser debugging port
- **Type**: Integer
- **Default**: `9222`
- **Example**: `DEFAULT_CAMOUFOX_PORT=9223`
- **Description**: CDP (Chrome DevTools Protocol) port used when Camoufox starts internally

### STREAM_PORT

- **Usage**: Integrated streaming proxy service port
- **Type**: Integer
- **Default**: `3120`
- **Special Value**: `0` - Disable streaming proxy service
- **Example**: `STREAM_PORT=3121`
- **Description**: Listening port for the built-in streaming proxy service, used for the first layer of the three-layer response acquisition mechanism

---

## Startup Configuration

### DIRECT_LAUNCH

- **Usage**: Quick launch
- **Type**: Boolean
- **Default**: `false`
- **Example**: `DIRECT_LAUNCH=false`
- **Description**: Skip waiting for option timeout and launch directly with default options

### SKIP_FRONTEND_BUILD

- **Usage**: Skip frontend build check
- **Type**: Boolean
- **Default**: `false`
- **Allowed Values**: `true`, `false`, `1`, `0`, `yes`, `no`
- **Example**: `SKIP_FRONTEND_BUILD=true`
- **Description**: Skip the frontend resource build check at startup. Suitable for environments without Node.js/npm, or deployment scenarios using pre-built resources. Can also be set via command line argument `--skip-frontend-build`.

---

## Proxy Configuration

### HTTP_PROXY

- **Usage**: HTTP proxy server address
- **Type**: String (URL)
- **Default**: Empty
- **Example**: `HTTP_PROXY=http://127.0.0.1:7890`
- **Description**: Upstream proxy for HTTP requests

### HTTPS_PROXY

- **Usage**: HTTPS proxy server address
- **Type**: String (URL)
- **Default**: Empty
- **Example**: `HTTPS_PROXY=http://127.0.0.1:7890`
- **Description**: Upstream proxy for HTTPS requests

### UNIFIED_PROXY_CONFIG

- **Usage**: Unified proxy configuration (Higher priority than HTTP_PROXY/HTTPS_PROXY)
- **Type**: String (URL)
- **Default**: `Empty`
- **Example**: `UNIFIED_PROXY_CONFIG=socks5://127.0.0.1:1080`
- **Description**: Recommended configuration, applies to both HTTP and HTTPS requests

### NO_PROXY

- **Usage**: Proxy bypass list
- **Type**: String (semicolon or comma separated)
- **Default**: Empty
- **Example**: `NO_PROXY=localhost;127.0.0.1;*.local`
- **Description**: Specify hostnames or IP addresses that should not use the proxy

---

## Log Configuration

### SERVER_LOG_LEVEL

- **Usage**: Server log level
- **Type**: String
- **Default**: `INFO`
- **Allowed Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Example**: `SERVER_LOG_LEVEL=DEBUG`
- **Description**: Controls the log verbosity of the FastAPI server

### SERVER_REDIRECT_PRINT

- **Usage**: Whether to redirect print output to logs
- **Type**: Boolean
- **Default**: `false`
- **Example**: `SERVER_REDIRECT_PRINT=true`
- **Description**: When enabled, all `print()` statements will be redirected to the logging system

### DEBUG_LOGS_ENABLED

- **Usage**: Enable debug logs
- **Type**: Boolean
- **Default**: `false`
- **Example**: `DEBUG_LOGS_ENABLED=true`
- **Description**: Enables more detailed debug information output when set to true

### TRACE_LOGS_ENABLED

- **Usage**: Enable trace logs
- **Type**: Boolean
- **Default**: `false`
- **Example**: `TRACE_LOGS_ENABLED=true`
- **Description**: Enables the most detailed trace level logs, used for deep debugging

### JSON_LOGS

- **Usage**: Enable JSON structured logs
- **Type**: Boolean
- **Default**: `false`
- **Example**: `JSON_LOGS=true`
- **Description**: When enabled, outputs logs in JSON format, suitable for log aggregation tools like ELK/Datadog

### LOG_FILE_MAX_BYTES

- **Usage**: Maximum bytes for a single log file
- **Type**: Integer
- **Default**: `10485760` (10MB)
- **Example**: `LOG_FILE_MAX_BYTES=20971520`
- **Description**: Log file will rotate automatically after reaching this size

### LOG_FILE_BACKUP_COUNT

- **Usage**: Number of log backup files to keep
- **Type**: Integer
- **Default**: `5`
- **Example**: `LOG_FILE_BACKUP_COUNT=10`
- **Description**: Number of backup log files to retain during rotation

---

## Authentication Configuration

### AUTO_SAVE_AUTH

- **Usage**: Automatically save authentication info to file
- **Type**: Boolean
- **Default**: `false`
- **Example**: `AUTO_SAVE_AUTH=true`
- **Description**: When enabled, automatically saves Google auth Cookies to `auth_profiles/saved/` directory
- **Warning**:
  > [!WARNING]
  > Must be set to `true` in **debug mode** to save new auth profiles! Headless mode uses saved profiles, so this setting has no effect on it.

### AUTH_SAVE_TIMEOUT

- **Usage**: Authentication save timeout (seconds)
- **Type**: Integer
- **Default**: `30`
- **Example**: `AUTH_SAVE_TIMEOUT=60`
- **Description**: Maximum time to wait for the auth file save to complete

### ONLY_COLLECT_CURRENT_USER_ATTACHMENTS

- **Usage**: Only collect current user attachments
- **Type**: Boolean
- **Default**: `false`
- **Example**: `ONLY_COLLECT_CURRENT_USER_ATTACHMENTS=true`
- **Description**: When enabled, only processes attachments in the current user's message, ignoring attachments in history messages

---

## Browser Configuration

### CAMOUFOX_WS_ENDPOINT

- **Usage**: Camoufox WebSocket endpoint URL
- **Type**: String (WebSocket URL)
- **Default**: Empty (Automatically set by startup script)
- **Example**: `CAMOUFOX_WS_ENDPOINT=ws://127.0.0.1:9222`
- **Description**: WebSocket address for Playwright to connect to Camoufox browser

### LAUNCH_MODE

- **Usage**: Launch mode
- **Type**: String
- **Default**: `normal`
- **Allowed Values**:
  - `normal` - Normal mode (with UI)
  - `headless` - Headless mode (no UI)
  - `virtual_display` - Virtual display mode
  - `direct_debug_no_browser` - Direct debug mode (no browser started)
- **Example**: `LAUNCH_MODE=headless`
- **Description**: Controls how the browser is launched

### ENDPOINT_CAPTURE_TIMEOUT

- **Usage**: WebSocket endpoint capture timeout (seconds)
- **Type**: Integer
- **Default**: `45`
- **Example**: `ENDPOINT_CAPTURE_TIMEOUT=60`
- **Description**: Maximum time to wait for Camoufox browser to start and return WebSocket endpoint

---

## API Default Parameters

### DEFAULT_TEMPERATURE

- **Usage**: Default temperature parameter
- **Type**: Float
- **Default**: `1.0`
- **Range**: `0.0` - `2.0`
- **Example**: `DEFAULT_TEMPERATURE=0.7`
- **Description**: Controls the randomness of model output, higher values mean more randomness

### DEFAULT_MAX_OUTPUT_TOKENS

- **Usage**: Default maximum output tokens
- **Type**: Integer
- **Default**: `65536`
- **Example**: `DEFAULT_MAX_OUTPUT_TOKENS=8192`
- **Description**: Limits the maximum length of text generated by the model

### DEFAULT_TOP_P

- **Usage**: Default Top-P parameter (Nucleus Sampling)
- **Type**: Float
- **Default**: `0.95`
- **Range**: `0.0` - `1.0`
- **Example**: `DEFAULT_TOP_P=0.9`
- **Description**: Controls the diversity of sampling, lower values mean more focused results

### DEFAULT_STOP_SEQUENCES

- **Usage**: Default stop sequences
- **Type**: JSON Array
- **Default**: `["User:"]`
- **Example**: `DEFAULT_STOP_SEQUENCES=["\\n\\nUser:", "\\n\\nAssistant:"]`
- **Description**: Stops generation when these sequences are encountered, note that special characters need to be properly escaped

### ENABLE_URL_CONTEXT

- **Usage**: Whether to enable URL Context feature
- **Type**: Boolean
- **Default**: `false`
- **Example**: `ENABLE_URL_CONTEXT=true`
- **Description**: When enabled, allows including URL context in requests (Reference: https://ai.google.dev/gemini-api/docs/url-context)

### ENABLE_THINKING_BUDGET

- **Usage**: Whether to default enable thinking budget limit
- **Type**: Boolean
- **Default**: `false`
- **Example**: `ENABLE_THINKING_BUDGET=true`
- **Description**: When enabled, uses specified thinking budget; when disabled, the model decides itself

### DEFAULT_THINKING_BUDGET

- **Usage**: Default thinking budget (tokens)
- **Type**: Integer
- **Default**: `8192`
- **Example**: `DEFAULT_THINKING_BUDGET=16384`
- **Description**: Used when `reasoning_effort` parameter is not provided in API request

### DEFAULT_THINKING_LEVEL_PRO

- **Usage**: Default thinking level for Gemini Pro models
- **Type**: String
- **Default**: `high`
- **Allowed Values**: `high`, `low`
- **Example**: `DEFAULT_THINKING_LEVEL_PRO=low`
- **Description**: Applicable to Pro models like gemini-3-pro-preview. Used when `reasoning_effort` parameter is not provided in API request

### DEFAULT_THINKING_LEVEL_FLASH

- **Usage**: Default thinking level for Gemini Flash models
- **Type**: String
- **Default**: `high`
- **Allowed Values**: `high`, `medium`, `low`, `minimal`
- **Example**: `DEFAULT_THINKING_LEVEL_FLASH=medium`
- **Description**: Applicable to Flash models like gemini-3-flash-preview. Used when `reasoning_effort` parameter is not provided in API request

### ENABLE_GOOGLE_SEARCH

- **Usage**: Whether to default enable Google Search feature
- **Type**: Boolean
- **Default**: `false`
- **Example**: `ENABLE_GOOGLE_SEARCH=true`
- **Description**: Decides whether to enable Google Search tool when `tools` parameter is not provided in API request

### MCP_HTTP_ENDPOINT

- **Usage**: MCP (Model Context Protocol) service endpoint
- **Type**: String (URL)
- **Default**: Empty
- **Example**: `MCP_HTTP_ENDPOINT=http://localhost:7000`
- **Description**: Specifies the HTTP endpoint of the MCP service for handling non-built-in tool calls. When a request contains an unknown tool call, the system attempts to forward the request to this endpoint.

### MCP_HTTP_TIMEOUT

- **Usage**: MCP service request timeout (seconds)
- **Type**: Float
- **Default**: `15`
- **Example**: `MCP_HTTP_TIMEOUT=30`
- **Description**: Maximum wait time when calling MCP service endpoint

---

## Timeout Configuration

All timeout configurations are in milliseconds (ms) unless otherwise specified.

### RESPONSE_COMPLETION_TIMEOUT

- **Usage**: Total response completion timeout
- **Type**: Integer (ms)
- **Default**: `300000` (5 minutes)
- **Example**: `RESPONSE_COMPLETION_TIMEOUT=600000`
- **Description**: Maximum time to wait for AI Studio to complete response

### INITIAL_WAIT_MS_BEFORE_POLLING

- **Usage**: Initial wait time before polling
- **Type**: Integer (ms)
- **Default**: `500`
- **Example**: `INITIAL_WAIT_MS_BEFORE_POLLING=1000`
- **Description**: Wait time before starting to poll response status

### POLLING_INTERVAL

- **Usage**: Non-streaming mode polling interval
- **Type**: Integer (ms)
- **Default**: `300`
- **Example**: `POLLING_INTERVAL=500`
- **Description**: Interval for checking response status in non-streaming requests

### POLLING_INTERVAL_STREAM

- **Usage**: Streaming mode polling interval
- **Type**: Integer (ms)
- **Default**: `180`
- **Example**: `POLLING_INTERVAL_STREAM=200`
- **Description**: Interval for checking response status in streaming requests

### SILENCE_TIMEOUT_MS

- **Usage**: Silence timeout
- **Type**: Integer (ms)
- **Default**: `60000` (1 minute)
- **Example**: `SILENCE_TIMEOUT_MS=120000`
- **Description**: Request times out if no new content output within this time

### POST_SPINNER_CHECK_DELAY_MS

- **Usage**: Spinner check delay
- **Type**: Integer (ms)
- **Default**: `500`
- **Description**: Delay before checking page loading spinner status

### FINAL_STATE_CHECK_TIMEOUT_MS

- **Usage**: Final state check timeout
- **Type**: Integer (ms)
- **Default**: `1500`
- **Description**: Timeout for waiting page to reach final state

### POST_COMPLETION_BUFFER

- **Usage**: Post completion buffer time
- **Type**: Integer (ms)
- **Default**: `700`
- **Description**: Extra wait time after response completion to ensure all content is loaded

### CLEAR_CHAT_VERIFY_TIMEOUT_MS

- **Usage**: Clear chat verification timeout
- **Type**: Integer (ms)
- **Default**: `5000`
- **Example**: `CLEAR_CHAT_VERIFY_TIMEOUT_MS=6000`
- **Description**: Timeout for verifying if chat has been cleared

### CLEAR_CHAT_VERIFY_INTERVAL_MS

- **Usage**: Clear chat verification interval
- **Type**: Integer (ms)
- **Default**: `2000`
- **Example**: `CLEAR_CHAT_VERIFY_INTERVAL_MS=1000`
- **Description**: Interval for checking if chat has been cleared

### CLICK_TIMEOUT_MS

- **Usage**: Click operation timeout
- **Type**: Integer (ms)
- **Default**: `3000`
- **Description**: Timeout for waiting for page element to be clickable

### CLIPBOARD_READ_TIMEOUT_MS

- **Usage**: Clipboard read timeout
- **Type**: Integer (ms)
- **Default**: `3000`
- **Description**: Timeout for reading browser clipboard content

### WAIT_FOR_ELEMENT_TIMEOUT_MS

- **Usage**: Element wait timeout
- **Type**: Integer (ms)
- **Default**: `10000`
- **Description**: General timeout for waiting for page elements to appear

### PSEUDO_STREAM_DELAY

- **Usage**: Pseudo-stream delay
- **Type**: Float (seconds)
- **Default**: `0.01`
- **Example**: `PSEUDO_STREAM_DELAY=0.02`
- **Description**: Delay between each data chunk in pseudo-streaming output

---

## GUI Launcher Configuration

> [!WARNING]
> The GUI launcher (`gui_launcher.py`) has been moved to the `deprecated/` directory. The following configurations are for reference only.

### GUI_DEFAULT_PROXY_ADDRESS

- **Usage**: Default proxy address for GUI launcher
- **Type**: String (URL)
- **Default**: `http://127.0.0.1:7890`
- **Example**: `GUI_DEFAULT_PROXY_ADDRESS=http://127.0.0.1:1080`
- **Description**: Pre-filled proxy address in GUI launcher

### GUI_DEFAULT_STREAM_PORT

- **Usage**: Default streaming port for GUI launcher
- **Type**: Integer
- **Default**: `3120`
- **Example**: `GUI_DEFAULT_STREAM_PORT=3121`
- **Description**: Pre-filled streaming proxy port in GUI launcher

### GUI_DEFAULT_HELPER_ENDPOINT

- **Usage**: Default Helper endpoint for GUI launcher
- **Type**: String (URL)
- **Default**: Empty
- **Example**: `GUI_DEFAULT_HELPER_ENDPOINT=http://helper.example.com`
- **Description**: URL of external Helper service (optional)

---

## Script Injection Configuration

### ENABLE_SCRIPT_INJECTION

- **Usage**: Whether to enable Tampermonkey script injection feature (v3.0)
- **Type**: Boolean
- **Default**: `false`
- **Example**: `ENABLE_SCRIPT_INJECTION=true`
- **Description**: When enabled, the system automatically parses the model list from the Tampermonkey script and injects it into API responses. Version 3.0 uses Playwright native network interception for higher reliability.

### USERSCRIPT_PATH

- **Usage**: Tampermonkey script file path
- **Type**: String (Relative path)
- **Default**: `browser_utils/more_models.js`
- **Example**: `USERSCRIPT_PATH=custom_scripts/my_script.js`
- **Description**: Path to the script file relative to the project root

---

## Other Configuration

### MODEL_NAME

- **Usage**: Model name identifier for proxy service
- **Type**: String
- **Default**: `AI-Studio_Proxy_API`
- **Example**: `MODEL_NAME=Custom_Proxy`
- **Description**: Proxy's own model name returned in `/v1/models` endpoint

### CHAT_COMPLETION_ID_PREFIX

- **Usage**: Chat completion ID prefix
- **Type**: String
- **Default**: `chatcmpl-`
- **Example**: `CHAT_COMPLETION_ID_PREFIX=custom-`
- **Description**: Prefix used when generating chat completion response IDs

### DEFAULT_FALLBACK_MODEL_ID

- **Usage**: Default fallback model ID
- **Type**: String
- **Default**: `no model list`
- **Example**: `DEFAULT_FALLBACK_MODEL_ID=gemini-pro`
- **Description**: Fallback model name used when model list cannot be obtained

### EXCLUDED_MODELS_FILENAME

- **Usage**: Excluded models filename
- **Type**: String
- **Default**: `excluded_models.txt`
- **Example**: `EXCLUDED_MODELS_FILENAME=my_excluded.txt`
- **Description**: File name containing model IDs to be excluded from the model list

### AI_STUDIO_URL_PATTERN

- **Usage**: AI Studio URL match pattern
- **Type**: String
- **Default**: `aistudio.google.com/`
- **Description**: URL pattern used to identify AI Studio pages

### MODELS_ENDPOINT_URL_CONTAINS

- **Usage**: Model list endpoint URL contains string
- **Type**: String
- **Default**: `MakerSuiteService/ListModels`
- **Description**: URL feature string used to intercept model list requests

### USER_INPUT_START_MARKER_SERVER

- **Usage**: User input start marker
- **Type**: String
- **Default**: `__USER_INPUT_START__`
- **Description**: Internal marker used to mark the start position of user input

### USER_INPUT_END_MARKER_SERVER

- **Usage**: User input end marker
- **Type**: String
- **Default**: `__USER_INPUT_END__`
- **Description**: Internal marker used to mark the end position of user input

---

## Function Calling Configuration

### FUNCTION_CALLING_MODE

- **Usage**: Function calling operation mode
- **Type**: String
- **Default**: `emulated`
- **Allowed Values**: `emulated`, `native`, `auto`
- **Description**:
  - `emulated`: Legacy text-based function calling (tools injected in prompt)
  - `native`: Uses AI Studio's native UI for function declarations
  - `auto`: Tries native, falls back to emulated on failure

### FUNCTION_CALLING_CACHE_ENABLED

- **Usage**: Enable function calling state caching
- **Type**: Boolean
- **Default**: `true`
- **Description**: When enabled, skips UI configuration if tool definitions haven't changed since the last request. Significantly improves performance.

### FUNCTION_CALLING_CACHE_TTL

- **Usage**: Cache Time-To-Live
- **Type**: Integer (seconds)
- **Default**: `0`
- **Description**: How long to keep the cache valid. `0` means no expiration (valid until session changes).

### FUNCTION_CALLING_NATIVE_FALLBACK

- **Usage**: Fallback behavior for AUTO mode
- **Type**: Boolean
- **Default**: `true`
- **Description**: If true, automatically switches to emulated mode if native UI automation fails.

### FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS

- **Usage**: Force clear function declarations
- **Type**: Boolean
- **Default**: `true`
- **Description**: If true, clears function declarations after every request. **Recommended to set to `false` when using caching.**

### FUNCTION_CALLING_DEBUG

- **Usage**: Master switch for function calling debug logging
- **Type**: Boolean
- **Default**: `false`
- **Description**: When enabled, activates the modular FC debug logging system. All FC-related console logs and file logging are controlled by this flag.

### FUNCTION_CALLING_UI_TIMEOUT

- **Usage**: UI operation timeout
- **Type**: Integer (milliseconds)
- **Default**: `5000`
- **Description**: Maximum time to wait for UI operations (toggle, dialog, paste) during native function calling setup.

### FUNCTION_CALLING_NATIVE_RETRY_COUNT

- **Usage**: Native mode retry attempts
- **Type**: Integer
- **Default**: `2`
- **Description**: Number of retry attempts for native mode UI automation before falling back to emulated mode.

---

## Function Calling Debug Logging

These variables control the modular debug logging system for function calling. All require `FUNCTION_CALLING_DEBUG=true` to be effective. Logs are written to `logs/fc_debug/`.

### Module Enable Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `FC_DEBUG_ORCHESTRATOR` | `false` | High-level flow, mode selection, fallback logic |
| `FC_DEBUG_UI` | `false` | Browser UI automation (toggles, dialogs, clicks) |
| `FC_DEBUG_CACHE` | `false` | Cache hits, misses, digest validation |
| `FC_DEBUG_WIRE` | `false` | Network response parsing (wire format) |
| `FC_DEBUG_DOM` | `false` | HTML DOM extraction of function calls |
| `FC_DEBUG_SCHEMA` | `false` | Tool schema conversion and validation |
| `FC_DEBUG_RESPONSE` | `false` | Response formatting for OpenAI compatibility |

### Per-Module Log Levels

| Variable | Default | Allowed Values |
|----------|---------|----------------|
| `FC_DEBUG_LEVEL_ORCHESTRATOR` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `FC_DEBUG_LEVEL_UI` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `FC_DEBUG_LEVEL_CACHE` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `FC_DEBUG_LEVEL_WIRE` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `FC_DEBUG_LEVEL_DOM` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `FC_DEBUG_LEVEL_SCHEMA` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `FC_DEBUG_LEVEL_RESPONSE` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

### Log File Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FC_DEBUG_LOG_MAX_BYTES` | `5242880` (5MB) | Maximum size per log file before rotation |
| `FC_DEBUG_LOG_BACKUP_COUNT` | `3` | Number of backup files to keep |
| `FC_DEBUG_COMBINED_LOG` | `false` | Write all FC logs to a single combined file |

### Payload Truncation

| Variable | Default | Description |
|----------|---------|-------------|
| `FC_DEBUG_TRUNCATE_ENABLED` | `true` | Enable truncation of large payloads |
| `FC_DEBUG_TRUNCATE_MAX_TOOL_DEF` | `500` | Max chars for tool definitions |
| `FC_DEBUG_TRUNCATE_MAX_ARGS` | `1000` | Max chars for function arguments |
| `FC_DEBUG_TRUNCATE_MAX_RESPONSE` | `2000` | Max chars for response bodies |

### Quick Start Examples

**Debug cache issues only:**
```env
FUNCTION_CALLING_DEBUG=true
FC_DEBUG_CACHE=true
```

**Full FC debugging with combined log:**
```env
FUNCTION_CALLING_DEBUG=true
FC_DEBUG_ORCHESTRATOR=true
FC_DEBUG_UI=true
FC_DEBUG_CACHE=true
FC_DEBUG_WIRE=true
FC_DEBUG_DOM=true
FC_DEBUG_SCHEMA=true
FC_DEBUG_RESPONSE=true
FC_DEBUG_COMBINED_LOG=true
```

**Production monitoring (errors only):**
```env
FUNCTION_CALLING_DEBUG=true
FC_DEBUG_ORCHESTRATOR=true
FC_DEBUG_LEVEL_ORCHESTRATOR=ERROR
```

For detailed documentation, see the [Native Function Calling Guide](./native-function-calling.md).

---

## Stream State Configuration

### STREAM_MAX_INITIAL_ERRORS

- **Usage**: Maximum initial errors for stream timeout logs
- **Type**: Integer
- **Default**: `3`
- **Example**: `STREAM_MAX_INITIAL_ERRORS=5`
- **Description**: Maximum number of errors allowed before suppressing duplicate error logs

### STREAM_WARNING_INTERVAL_AFTER_SUPPRESS

- **Usage**: Warning interval after suppression (seconds)
- **Type**: Float
- **Default**: `60.0`
- **Example**: `STREAM_WARNING_INTERVAL_AFTER_SUPPRESS=120.0`
- **Description**: Interval for showing warning again after errors are suppressed

### STREAM_SUPPRESS_DURATION_AFTER_INITIAL_BURST

- **Usage**: Suppression duration after initial burst (seconds)
- **Type**: Float
- **Default**: `400.0`
- **Example**: `STREAM_SUPPRESS_DURATION_AFTER_INITIAL_BURST=600.0`
- **Description**: Duration to suppress duplicate logs after an initial burst of errors

---

## Configuration Best Practices

### 1. Use .env File

Centralize all configurations in the `.env` file at the project root:

```bash
# Copy template
cp .env.example .env

# Edit configuration
nano .env
```

### 2. Configuration Priority

Configuration items take effect in the following priority order (high to low):

1. **Command Line Arguments** - Temporarily override configuration
2. **Environment Variables** - `.env` file or system environment variables
3. **Default Values** - Default values defined in code

### 3. Security Considerations

- ✅ `.env` file is in `.gitignore`, won't be committed
- ✅ Do not include real sensitive information in `.env.example`
- ✅ Update and review configuration periodically
- ✅ Use sufficiently complex keys and credentials

### 4. Debug Configuration

Enable detailed logs for debugging:

```env
DEBUG_LOGS_ENABLED=true
TRACE_LOGS_ENABLED=true
SERVER_LOG_LEVEL=DEBUG
SERVER_REDIRECT_PRINT=true
```

### 5. Production Environment Configuration

Recommended configuration for production:

```env
SERVER_LOG_LEVEL=WARNING
DEBUG_LOGS_ENABLED=false
TRACE_LOGS_ENABLED=false
RESPONSE_COMPLETION_TIMEOUT=600000
SILENCE_TIMEOUT_MS=120000
```

---

## Related Documentation

- [Environment Configuration Guide](environment-configuration.md) - Configuration management and usage methods
- [Installation Guide](installation-guide.md) - Installation and initial setup
- [Troubleshooting Guide](troubleshooting.md) - Common configuration issue solutions
- [Advanced Configuration Guide](advanced-configuration.md) - Advanced configuration options
- [Native Function Calling Guide](native-function-calling.md) - Complete function calling setup guide

---

## Verify Configuration

After starting the service, check logs to confirm if configuration is loaded correctly:

```bash
# View startup logs
tail -f logs/app.log

# Check configuration endpoint
curl http://127.0.0.1:2048/api/info

# Health check
curl http://127.0.0.1:2048/health
```
