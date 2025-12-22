# Advanced Configuration Guide

This document introduces advanced configuration options and features of the project.

## Proxy Configuration Management

### Proxy Configuration Priority

The project uses a unified proxy configuration management system, determining proxy settings in the following priority order:

1. **`--internal-camoufox-proxy` command line argument** (Highest priority)
   - Explicitly specify proxy: `--internal-camoufox-proxy 'http://127.0.0.1:7890'`
   - Explicitly disable proxy: `--internal-camoufox-proxy ''`
2. **`UNIFIED_PROXY_CONFIG` environment variable** (Recommended, configured in .env file)
3. **`HTTP_PROXY` / `HTTPS_PROXY` environment variables**
4. **System proxy settings** (gsettings under Linux, lowest priority)

**Recommended Configuration Method**:

```env
# Unified proxy configuration in .env file
UNIFIED_PROXY_CONFIG=http://127.0.0.1:7890
# Or disable proxy
UNIFIED_PROXY_CONFIG=
```

### Unified Proxy Configuration

This proxy configuration applies to both the Camoufox browser and the upstream connection of the streaming proxy service, ensuring consistent proxy behavior across the system.

## Response Acquisition Mode Configuration

### Mode 1: Prefer Integrated Streaming Proxy (Default Recommended)

**Recommended using .env configuration**:

```env
# .env file configuration
DEFAULT_FASTAPI_PORT=2048
STREAM_PORT=3120
UNIFIED_PROXY_CONFIG=
```

```bash
# Simplified start command (Recommended)
python launch_camoufox.py --headless

# Traditional command line way (Still supported)
python launch_camoufox.py --headless --server-port 2048 --stream-port 3120 --helper '' --internal-camoufox-proxy ''
```

```bash
# Enable unified proxy configuration (Applies to both browser and streaming proxy)
python launch_camoufox.py --headless --server-port 2048 --stream-port 3120 --helper '' --internal-camoufox-proxy 'http://127.0.0.1:7890'
```

In this mode, the main server prioritizes attempting to get response via the integrated streaming proxy on port `3120` (or specified `--stream-port`). If it fails, it falls back to Playwright page interaction.

### Mode 2: Prefer External Helper Service (Disable Integrated Streaming Proxy)

```bash
# Basic External Helper mode, explicitly disable proxy
python launch_camoufox.py --headless --server-port 2048 --stream-port 0 --helper 'http://your-helper-service.com/api/getStreamResponse' --internal-camoufox-proxy ''

# External Helper mode + Unified proxy configuration
python launch_camoufox.py --headless --server-port 2048 --stream-port 0 --helper 'http://your-helper-service.com/api/getStreamResponse' --internal-camoufox-proxy 'http://127.0.0.1:7890'
```

In this mode, the main server prioritizes attempting to get response via the endpoint specified by `--helper` (requires valid `auth_profiles/active/*.json` to extract `SAPISID`). If it fails, it falls back to Playwright page interaction.

### Mode 3: Use Playwright Page Interaction Only (Disable All Streaming Proxies and Helpers)

```bash
# Pure Playwright mode, explicitly disable proxy
python launch_camoufox.py --headless --server-port 2048 --stream-port 0 --helper '' --internal-camoufox-proxy ''

# Playwright mode + Unified proxy configuration
python launch_camoufox.py --headless --server-port 2048 --stream-port 0 --helper '' --internal-camoufox-proxy 'http://127.0.0.1:7890'
```

In this mode, the main server will only get response by interacting with the AI Studio page via Playwright (simulating clicking "Edit" or "Copy" buttons). This is the traditional fallback method.

## Virtual Display Mode (Linux)

### About `--virtual-display`

- **Why use it**: Compared to standard headless mode, virtual display mode runs the browser by creating a complete virtual X server environment (Xvfb). This can simulate a more realistic desktop environment, potentially further reducing the risk of being detected as an automated script or bot.
- **When to use it**: When you run under Linux environment and wish to operate in headless mode.
- **How to use it**:
  1. Ensure your Linux system has `xvfb` installed.
  2. Add `--virtual-display` flag at runtime:
     ```bash
     python launch_camoufox.py --virtual-display --server-port 2048 --stream-port 3120 --internal-camoufox-proxy ''
     ```

## Streaming Proxy Service Configuration

### Self-Signed Certificate Management

The integrated streaming proxy service generates self-signed root certificates in the `certs` folder.

#### Certificate Deletion and Regeneration

- You can delete root certificates (`ca.crt`, `ca.key`) in `certs` directory, the code will regenerate them at next startup.
- **Important**: When deleting root certificates, **it is strongly recommended to delete all other files in `certs` directory** to avoid trust chain errors.

#### Manual Certificate Generation

If you need to regenerate certificates, you can use the following commands:

```bash
openssl genrsa -out certs/ca.key 2048
openssl req -new -x509 -days 3650 -key certs/ca.key -out certs/ca.crt -subj "/C=US/ST=State/L=City/O=AiStudioProxyHelper/OU=CA/CN=AiStudioProxyHelper CA/emailAddress=ca@example.com"
openssl rsa -in certs/ca.key -out certs/ca.key
```

### How It Works

Streaming proxy service features:

- Creates an HTTP proxy server (Default port: 3120)
- Intercepts HTTPS requests to Google domains
- Dynamically auto-generates server certificates using self-signed CA certificate
- Parses AIStudio responses into OpenAI compatible format

## Model Exclusion Configuration

### excluded_models.txt

The `excluded_models.txt` file in the project root can be used to exclude specific model IDs from the list returned by `/v1/models` endpoint.

One model ID per line, for example:

```
gemini-1.0-pro
gemini-1.0-pro-vision
deprecated-model-id
```

## Script Injection Configuration

The script injection feature allows you to dynamically mount Tampermonkey scripts to enhance AI Studio's model list. This feature uses Playwright native network interception technology to ensure reliability.

For detailed usage guide, working principles, and troubleshooting, please refer to [Script Injection Guide](script_injection_guide.md).

### Key Configuration

```env
# Enable script injection feature
ENABLE_SCRIPT_INJECTION=true

# Specify custom script path (Defaults to browser_utils/more_models.js)
USERSCRIPT_PATH=custom_scripts/my_enhanced_script.js
```

### Debugging

If you encounter issues, you can enable verbose logs:

```env
DEBUG_LOGS_ENABLED=true
```

## Feature Flags

The following environment variables can be used to enable experimental features or adjust specific behaviors:

### Thinking Model Budget Control

```env
# Enable Token budget control for Thinking models
ENABLE_THINKING_BUDGET=true
# Set default thinking budget (Tokens)
DEFAULT_THINKING_BUDGET=8192
```

### Web Search Enhancement

```env
# Enable Google Search tool (If model supports it)
ENABLE_GOOGLE_SEARCH=true
```

### URL Context Retrieval

```env
# Allow parsing URL content in Prompt
ENABLE_URL_CONTEXT=true
```

### Attachment Processing Optimization

```env
# Only collect attachments from current user message (Ignore attachments in history messages, reduce Token consumption)
ONLY_COLLECT_CURRENT_USER_ATTACHMENTS=true
```

### Frontend Build Control

```env
# Skip frontend resource build check at startup (Suitable for environments without Node.js or using pre-built resources)
SKIP_FRONTEND_BUILD=true
```

Can also be set via command line argument:

```bash
python launch_camoufox.py --headless --skip-frontend-build
```

## Model Capability Configuration

### config/model_capabilities.json

Model capability configuration has been externalized to `config/model_capabilities.json` file. This configuration defines each model's:

- **thinkingType**: Thinking mode type (`none`, `level`, `budget`)
- **supportsGoogleSearch**: Whether supports Google Search tool
- **levels/budgetRange**: Thinking levels or budget range

**Advantage**: When Google releases new models, just edit the JSON file, no code changes needed.

Example structure:

```json
{
  "categories": {
    "gemini3Flash": {
      "thinkingType": "level",
      "levels": ["minimal", "low", "medium", "high"],
      "supportsGoogleSearch": true
    }
  },
  "matchers": [{ "pattern": "gemini-3.*-flash", "category": "gemini3Flash" }]
}
```

## GUI Launcher Advanced Features

### Local LLM Mock Service

GUI integrates the function to start and manage a local LLM mock service:

- **Function**: Listens on port `11434`, simulates partial Ollama API endpoints and OpenAI compatible `/v1/chat/completions` endpoint.
- **Start**: In GUI "Launch Options" area, click "Start Local LLM Mock Service" button.
- **Dependency Check**: Before starting, it automatically detects if `localhost:2048` port is available.
- **Usage**: Mainly used for testing client integration with Ollama or OpenAI compatible API.

### Port Process Management

GUI provides port process management function:

- Query processes currently running on specific ports
- Select and try to stop processes found on specified ports
- Manually enter PID to terminate process

**Safety Mechanism**: Process termination function verifies if PID belongs to configured ports (FastAPI, Camoufox, Stream Proxy), preventing accidental termination of unrelated processes.

## Environment Variable Configuration

### Proxy Configuration

```bash
# Use environment variable to configure proxy (Not recommended, explicit specification suggested)
export UNIFIED_PROXY_CONFIG=http://127.0.0.1:7890
python launch_camoufox.py --headless --server-port 2048 --stream-port 3120 --helper ''
```

### Log Control

See [Log Control Guide](logging-control.md).

## Important Notes

### Proxy Configuration Recommendation

**It is strongly recommended to explicitly specify `--internal-camoufox-proxy` argument in all `launch_camoufox.py` commands, even if the value is an empty string (`''`), to avoid accidentally using proxy settings from system environment variables.**

### Parameter Control Limitation

Model parameters in API requests (like `temperature`, `max_output_tokens`, `top_p`, `stop`) **only take effect when obtaining response via Playwright page interaction**. When using integrated streaming proxy or external Helper service, how these parameters are passed and applied depends on the implementation of these services themselves.

### First Access Performance

When accessing a new HTTPS host via streaming proxy for the first time, the service needs to dynamically generate and sign a new child certificate for that host. This process can be time-consuming, causing slow response for the first connection request to that new host. Once the certificate is generated and cached, subsequent access to the same host will be significantly faster.

## Next Steps

After advanced configuration is complete, please refer to:

- [Script Injection Guide](script_injection_guide.md) - Detailed usage instructions for script injection
- [Log Control Guide](logging-control.md)
- [Troubleshooting Guide](troubleshooting.md)

## Toolcall / MCP Compatibility Note

- Request structure must follow OpenAI Completions compatible format:
  - `messages`: Standard message array, containing `role` and `content`
  - `tools`: Tool declaration array, elements like `{ "type": "function", "function": { "name": "sum", "parameters": { ... } } }`
  - `tool_choice`: Can be specific function name or `{ "type": "function", "function": { "name": "sum" } }`; when `"auto"` and only one tool declared, executes automatically
- Tool execution behavior:
  - Built-in tools (`get_current_time`, `echo`, `sum`) execute directly; results injected as JSON string
  - Non-built-in tools declared in current request `tools`, if MCP endpoint provided (request field `mcp_endpoint` or env var `MCP_HTTP_ENDPOINT`), invoke MCP service and return result
  - Returns `Unknown tool` if undeclared or endpoint missing
- Response compatibility:
  - Both streaming and non-streaming output OpenAI compatible `tool_calls` structure and `finish_reason: "tool_calls"`; finally includes `usage` stats and `[DONE]`

### Request Example (Python requests)

```python
import requests

API_URL = "http://localhost:2048/v1/chat/completions"

data = {
  "model": "AI-Studio_Proxy_API",
  "stream": True,
  "messages": [
    {"role": "user", "content": "Please calculate the sum of these numbers: {\"values\": [1, 2.5, 3]}"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "sum",
        "parameters": {
          "type": "object",
          "properties": {
            "values": {"type": "array", "items": {"type": "number"}}
          },
          "required": ["values"]
        }
      }
    }
  ],
  "tool_choice": {"type": "function", "function": {"name": "sum"}},
  # Optional: MCP endpoint for this request (enabled for non-built-in tools)
  # "mcp_endpoint": "http://127.0.0.1:7000"
}

resp = requests.post(API_URL, json=data, stream=data["stream"])
for line in resp.iter_lines():
  if not line:
    continue
  print(line.decode("utf-8"))
```

### Behavior Description

- When tool execution occurs, response will contain `tool_calls` fragments and `finish_reason: "tool_calls"`; client needs to handle parsing according to OpenAI Completions way.
- If declaring non-built-in tool and providing `mcp_endpoint` (or setting env `MCP_HTTP_ENDPOINT`), server will forward call to MCP service and return its result.
