# Environment Configuration Guide

This document details how to use the `.env` file to configure the AI Studio Proxy API project, achieving unified configuration management.

## Overview

The project adopts a modern configuration management system based on `.env` files, providing the following advantages:

### Key Advantages

- ✅ **Worry-free Updates**: A single `git pull` completes the update without needing reconfiguration.
- ✅ **Centralized Management**: All configuration items are unified in the `.env` file, clear and concise.
- ✅ **Simplified Startup**: No complex command-line arguments needed, one-click start.
- ✅ **Security**: The `.env` file is ignored by `.gitignore`, preventing sensitive configuration leaks.
- ✅ **Flexibility**: Supports configuration management for different environments (Development, Testing, Production).
- ✅ **Docker Compatibility**: Docker and local environments use the same configuration method.
- ✅ **Modular Design**: Configuration items are grouped by function for easy understanding and maintenance.

## Quick Start

### 1. Copy Configuration Template

```bash
cp .env.example .env
```

### 2. Edit Configuration File

Modify the configuration items in the `.env` file according to your needs:

```bash
# Edit configuration file
nano .env
# Or use another editor
code .env
```

### 3. Start Service

After configuration, starting is very simple:

```bash
# Command line start (Recommended for daily use)
python launch_camoufox.py --headless

# Debug mode (For first-time setup or troubleshooting)
python launch_camoufox.py --debug
```

**That's it!** No complex command-line arguments needed, all configurations are preset in the `.env` file.

## Main Configuration Items

### Service Port Configuration

```env
# FastAPI Service Port
PORT=8000
DEFAULT_FASTAPI_PORT=2048
DEFAULT_CAMOUFOX_PORT=9222

# Camoufox WebSocket Endpoint Capture Timeout (seconds)
ENDPOINT_CAPTURE_TIMEOUT=45

# Streaming Proxy Service Configuration
STREAM_PORT=3120
```

### Startup Configuration

```env
# Direct Launch
DIRECT_LAUNCH=false

# Skip Frontend Build Check (Suitable for environments without Node.js or using pre-built assets)
SKIP_FRONTEND_BUILD=false
```

### Proxy Configuration

```env
# HTTP/HTTPS Proxy Settings
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890

# Unified Proxy Configuration (Higher Priority)
UNIFIED_PROXY_CONFIG=http://127.0.0.1:7890

# Proxy Bypass List
NO_PROXY=localhost;127.0.0.1;*.local
```

### Log Configuration

```env
# Server Log Level
SERVER_LOG_LEVEL=INFO

# Enable Debug Logs
DEBUG_LOGS_ENABLED=false
TRACE_LOGS_ENABLED=false

# Redirect print output to logs
SERVER_REDIRECT_PRINT=false
```

### Authentication Configuration

```env
# Auto Save Auth Info
# [IMPORTANT] Must be set to true in debug mode to save new auth profiles!
AUTO_SAVE_AUTH=false

# Auth Save Timeout (seconds)
AUTH_SAVE_TIMEOUT=30

# Only collect attachments from current user messages (true/false)
ONLY_COLLECT_CURRENT_USER_ATTACHMENTS=false
```

> [!WARNING]
> `AUTO_SAVE_AUTH=true` is a necessary condition for saving auth profiles in debug mode. Please ensure this option is enabled during initial setup. Headless mode uses saved profiles, so this setting has no effect on it.

### Browser Configuration

```env
# Camoufox WebSocket Endpoint
# CAMOUFOX_WS_ENDPOINT=ws://127.0.0.1:9222

# Launch Mode (normal, headless, virtual_display, direct_debug_no_browser)
LAUNCH_MODE=normal
```

### API Default Parameters

```env
# Default Temperature (0.0-2.0)
DEFAULT_TEMPERATURE=1.0

# Default Max Output Tokens
DEFAULT_MAX_OUTPUT_TOKENS=65536

# Default Top-P (0.0-1.0)
DEFAULT_TOP_P=0.95

# Default Stop Sequences (JSON Array Format)
DEFAULT_STOP_SEQUENCES=["User:"]

# Whether to automatically open and use "URL Context" feature when processing requests
# Reference: https://ai.google.dev/gemini-api/docs/url-context
ENABLE_URL_CONTEXT=false

# Whether to default enable "Specific Thinking Budget" feature (true/false)
# When disabled, the model generally decides the thinking budget itself
# This value is used when reasoning_effort parameter is not provided in the API request.
ENABLE_THINKING_BUDGET=false

# Default value for "Specific Thinking Budget" (tokens)
# This value is used when reasoning_effort parameter is not provided in the API request.
DEFAULT_THINKING_BUDGET=8192

# Whether to default enable "Google Search" feature (true/false)
# This setting is used as the default switch state for Google Search when the tools parameter is not provided in the API request.
ENABLE_GOOGLE_SEARCH=false
```

### Timeout Configuration

```env
# Response Completion Total Timeout (ms)
RESPONSE_COMPLETION_TIMEOUT=300000

# Polling Interval (ms)
POLLING_INTERVAL=300
POLLING_INTERVAL_STREAM=180

# Silence Timeout (ms)
SILENCE_TIMEOUT_MS=60000

# Initial Wait Time (ms)
INITIAL_WAIT_MS_BEFORE_POLLING=500

# Page Operation Timeout (ms)
POST_SPINNER_CHECK_DELAY_MS=500
FINAL_STATE_CHECK_TIMEOUT_MS=1500
POST_COMPLETION_BUFFER=700

# Clear Chat Related Timeout (ms)
CLEAR_CHAT_VERIFY_TIMEOUT_MS=5000
CLEAR_CHAT_VERIFY_INTERVAL_MS=2000

# Click and Clipboard Operation Timeout (ms)
CLICK_TIMEOUT_MS=3000
CLIPBOARD_READ_TIMEOUT_MS=3000

# Element Wait Timeout (ms)
WAIT_FOR_ELEMENT_TIMEOUT_MS=10000

# Stream Related Configuration
PSEUDO_STREAM_DELAY=0.01
```

### GUI Launcher Configuration (Deprecated)

> [!WARNING]
> The GUI launcher has been moved to the `deprecated/` directory. The following configurations are for reference only.

```env
# GUI Default Proxy Address
GUI_DEFAULT_PROXY_ADDRESS=http://127.0.0.1:7890

# GUI Default Streaming Proxy Port
GUI_DEFAULT_STREAM_PORT=3120

# GUI Default Helper Endpoint
GUI_DEFAULT_HELPER_ENDPOINT=
```

### Script Injection Configuration

```env
# Whether to enable Tampermonkey script injection feature
ENABLE_SCRIPT_INJECTION=true

# Tampermonkey script file path (relative to project root)
# Model data is parsed directly from this script file, no extra config file needed
USERSCRIPT_PATH=browser_utils/more_models.js
```

**Features**:

- **Playwright Native Interception**: Uses Playwright route interception for reliability.
- **Double Assurance Mechanism**: Network interception + Script injection.
- **Direct Script Parsing**: Automatically parses model lists from the Tampermonkey script, no config file needed.
- **Frontend-Backend Sync**: Frontend and backend use the same model data source.
- **Zero Config Maintenance**: Automatically fetches new model lists when the script updates.

For detailed usage, please see [Script Injection Guide](script_injection_guide.md).

## Common Configuration Scenarios

### Scenario 1: Using Proxy

```env
# Enable Proxy
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890

# Use same proxy in GUI
GUI_DEFAULT_PROXY_ADDRESS=http://127.0.0.1:7890
```

### Scenario 2: Debug Mode

```env
# Enable Verbose Logs
DEBUG_LOGS_ENABLED=true
TRACE_LOGS_ENABLED=true
SERVER_LOG_LEVEL=DEBUG
SERVER_REDIRECT_PRINT=true
```

### Scenario 3: Production Environment

```env
# Production Environment Configuration
SERVER_LOG_LEVEL=WARNING
DEBUG_LOGS_ENABLED=false
TRACE_LOGS_ENABLED=false

# Longer Timeouts
RESPONSE_COMPLETION_TIMEOUT=600000
SILENCE_TIMEOUT_MS=120000
```

### Scenario 4: Custom Ports

```env
# Avoid Port Conflicts
DEFAULT_FASTAPI_PORT=3048
DEFAULT_CAMOUFOX_PORT=9223
STREAM_PORT=3121
```

### Scenario 5: Enable Script Injection

```env
# Enable Script Injection Feature
ENABLE_SCRIPT_INJECTION=true

# Use Custom Script (Model data parsed directly from script)
USERSCRIPT_PATH=browser_utils/my_custom_script.js

# Debug Mode to check injection effect
DEBUG_LOGS_ENABLED=true

# Streaming Proxy Configuration (Used with script injection)
STREAM_PORT=3120
```

## Configuration Priority

The project uses a layered configuration system, determining the final configuration in the following priority order:

1. **Command Line Arguments** (Highest Priority)

   ```bash
   # Command line arguments overwrite environment variables and .env settings
   python launch_camoufox.py --headless --server-port 3048
   ```

2. **System Environment Variables**

   ```bash
   # System environment variables overwrite .env file settings
   export DEFAULT_FASTAPI_PORT=2048
   ```

3. **`.env` File Configuration** (Recommended)

   ```env
   # Configuration in .env file
   DEFAULT_FASTAPI_PORT=2048
   ```

4. **Default Values** (Lowest Priority)
   Default values defined in the code.

### Usage Recommendations

- **Daily Use**: Configure all common settings in the `.env` file.
- **Temporary Adjustment**: Use command-line arguments for temporary overrides without modifying the `.env` file.
- **CI/CD Environment**: Can be configured via system environment variables.

## Considerations

### 1. File Security

- The `.env` file is ignored by `.gitignore` and will not be committed to version control.
- Do not include real sensitive information in `.env.example`.
- If sharing configuration, please copy and clean sensitive information before sharing.

### 2. Format Requirements

- Environment variable names are case-sensitive.
- Boolean values use `true`/`false`.
- Arrays use JSON format: `["item1", "item2"]`.
- Use quotes for string values containing special characters.

### 3. Restart to Take Effect

The service needs to be restarted for changes in the `.env` file to take effect.

### 4. Verify Configuration

When starting the service, logs will show loaded configuration information, which can be used to verify if the configuration is correct.

## Troubleshooting

### Configuration Not Taking Effect

1. Check if the `.env` file is in the project root directory.
2. Check if the environment variable name is correct (case-sensitive).
3. Check if the value format is correct.
4. Restart the service.

### Proxy Configuration Issues

1. Confirm proxy server address and port are correct.
2. Check if the proxy server is running normally.
3. Verify network connection.

### Port Conflicts

1. Check if the port is occupied by another program.
2. Use the GUI launcher's port check function.
3. Change to another available port.

## More Information

- [Installation Guide](installation-guide.md)
- [Advanced Configuration](advanced-configuration.md)
- [Troubleshooting](troubleshooting.md)
