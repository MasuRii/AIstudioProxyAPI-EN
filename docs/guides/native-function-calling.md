# Native Function Calling Guide

This guide explains how to use native function calling (tool calls) with the AI Studio Proxy API. Native function calling provides reliable, structured tool invocation that is fully compatible with the OpenAI API format.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [How It Works](#how-it-works)
4. [Configuration](#configuration)
5. [Modes Explained](#modes-explained)
6. [Client Integration](#client-integration)
7. [Caching & Performance](#caching--performance)
8. [Troubleshooting](#troubleshooting)
9. [Debug Logging](#debug-logging)

---

## Overview

The AI Studio Proxy supports two approaches for function calling:

| Mode | Description | Best For |
|------|-------------|----------|
| **Native** | Uses AI Studio's built-in function calling UI | Maximum reliability, structured responses |
| **Emulated** | Injects tool definitions into prompt text | Legacy clients, backward compatibility |
| **Auto** | Tries native first, falls back to emulated | Most users (recommended) |

### Key Benefits of Native Function Calling

- **Structured Responses**: Gemini outputs function calls in a structured format, not as text
- **Better Reliability**: No text parsing required, fewer edge cases
- **Token Efficiency**: Tool definitions aren't injected into the prompt
- **OpenAI Compatibility**: Full `tools`/`tool_calls` API support

---

## Quick Start

### 1. Enable Native Function Calling

Add to your `.env` file:

```bash
# Recommended: Auto mode with fallback
FUNCTION_CALLING_MODE=auto

# Enable caching for performance (reduces UI operations)
FUNCTION_CALLING_CACHE_ENABLED=true
```

### 2. Send a Request with Tools

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:2048/v1",
    api_key="your-api-key"  # Optional if auth is disabled
)

response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[
        {"role": "user", "content": "What's the weather in Tokyo?"}
    ],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, e.g., 'Tokyo, Japan'"
                    }
                },
                "required": ["location"]
            }
        }
    }],
    tool_choice="auto"
)

# Check for tool calls
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        print(f"Function: {tool_call.function.name}")
        print(f"Arguments: {tool_call.function.arguments}")
```

### 3. Handle the Tool Response

```python
# Execute your function
weather_result = get_weather(location="Tokyo, Japan")

# Send the result back
follow_up = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[
        {"role": "user", "content": "What's the weather in Tokyo?"},
        response.choices[0].message,  # Assistant's tool call
        {
            "role": "tool",
            "tool_call_id": response.choices[0].message.tool_calls[0].id,
            "content": json.dumps(weather_result)
        }
    ],
    tools=[...]  # Same tools as before
)

print(follow_up.choices[0].message.content)
```

---

## How It Works

### Request Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           REQUEST PHASE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Client sends request with `tools` array (OpenAI format)              │
│                     │                                                    │
│                     v                                                    │
│  2. FunctionCallingOrchestrator.prepare_request()                        │
│        ├── Check cache: same tools as before?                            │
│        ├── Convert OpenAI tools → Gemini FunctionDeclarations            │
│        └── Configure AI Studio UI (if cache miss):                       │
│                 ├── Enable function calling toggle                       │
│                 ├── Open declarations editor                             │
│                 ├── Paste JSON declarations                              │
│                 └── Save and close                                       │
│                     │                                                    │
│                     v                                                    │
│  3. Submit prompt (clean, no tool text injection)                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          RESPONSE PHASE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  4. Parse response using multiple strategies:                            │
│        ├── Strategy 1: Wire format (network interception)                │
│        ├── Strategy 2: Native DOM parsing (ms-function-call-chunk)       │
│        └── Strategy 3: Emulated text fallback                            │
│                     │                                                    │
│                     v                                                    │
│  5. Format to OpenAI tool_calls structure:                               │
│        {                                                                 │
│          "tool_calls": [{                                                │
│            "id": "call_abc123",                                          │
│            "type": "function",                                           │
│            "function": {                                                 │
│              "name": "get_weather",                                      │
│              "arguments": "{\"location\": \"Tokyo\"}"                    │
│            }                                                             │
│          }],                                                             │
│          "finish_reason": "tool_calls"                                   │
│        }                                                                 │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Schema Conversion

The proxy automatically converts OpenAI tool definitions to Gemini's FunctionDeclaration format:

| OpenAI Field | Gemini Field | Notes |
|--------------|--------------|-------|
| `function.name` | `name` | Direct copy |
| `function.description` | `description` | Direct copy |
| `function.parameters` | `parameters` | JSON Schema compatible |
| `function.strict` | N/A | Stripped (not supported) |

**Unsupported JSON Schema fields** (automatically stripped):
- `minimum`, `maximum`, `pattern`
- `minLength`, `maxLength`
- `minItems`, `maxItems`
- `$schema`, `$id`, `$ref`

---

## Configuration

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FUNCTION_CALLING_MODE` | `emulated` | Mode: `emulated`, `native`, or `auto` |
| `FUNCTION_CALLING_NATIVE_FALLBACK` | `true` | Fall back to emulated if native fails |
| `FUNCTION_CALLING_UI_TIMEOUT` | `5000` | UI operation timeout in milliseconds |
| `FUNCTION_CALLING_NATIVE_RETRY_COUNT` | `2` | Retry attempts for native mode |
| `FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS` | `true` | Clear declarations after each request |

### Caching Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FUNCTION_CALLING_CACHE_ENABLED` | `true` | Enable digest-based caching |
| `FUNCTION_CALLING_CACHE_TTL` | `0` | Cache TTL in seconds (0 = no expiry) |

### Recommended Production Configuration

```bash
# .env
FUNCTION_CALLING_MODE=auto
FUNCTION_CALLING_CACHE_ENABLED=true
FUNCTION_CALLING_CACHE_TTL=0
FUNCTION_CALLING_CLEAR_BETWEEN_REQUESTS=false
FUNCTION_CALLING_DEBUG=false
```

---

## Modes Explained

### Emulated Mode (`FUNCTION_CALLING_MODE=emulated`)

- Tools are injected into the system prompt as text
- Model outputs function calls as structured text (`Request function call: ...`)
- Proxy parses the text to extract function calls
- **Pros**: Works with any model, no UI automation required
- **Cons**: Less reliable, consumes tokens, parsing edge cases

### Native Mode (`FUNCTION_CALLING_MODE=native`)

- Uses AI Studio's built-in function calling UI
- Tools configured via browser automation
- Model returns structured function calls
- **Pros**: Most reliable, structured output, token efficient
- **Cons**: Requires UI automation, may fail if UI changes

### Auto Mode (`FUNCTION_CALLING_MODE=auto`) - Recommended

- Attempts native mode first
- Automatically falls back to emulated if native fails
- Best of both worlds: reliability with resilience
- **Pros**: Resilient, self-healing, recommended for production

---

## Client Integration

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:2048/v1",
    api_key="optional-key"
)

# Works exactly like OpenAI API
response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "..."}],
    tools=[...],
    tool_choice="auto"  # or "none", "required", {"type": "function", "function": {"name": "..."}}
)
```

### OpenAI Node.js SDK

```javascript
import OpenAI from 'openai';

const client = new OpenAI({
    baseURL: 'http://localhost:2048/v1',
    apiKey: 'optional-key'
});

const response = await client.chat.completions.create({
    model: 'gemini-2.5-flash',
    messages: [{ role: 'user', content: '...' }],
    tools: [...],
    tool_choice: 'auto'
});
```

### cURL

```bash
curl http://localhost:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"}
          },
          "required": ["location"]
        }
      }
    }]
  }'
```

### Streaming with Tool Calls

```python
# Streaming also works with tool calls
stream = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[...],
    tools=[...],
    stream=True
)

tool_calls = []
for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.tool_calls:
        for tc in delta.tool_calls:
            # Accumulate tool call fragments
            if tc.id:
                tool_calls.append({"id": tc.id, "name": "", "arguments": ""})
            if tc.function.name:
                tool_calls[-1]["name"] = tc.function.name
            if tc.function.arguments:
                tool_calls[-1]["arguments"] += tc.function.arguments
```

---

## Caching & Performance

### How Caching Works

1. **Digest Calculation**: SHA256 hash of the `tools` array
2. **Cache Hit**: If digest matches cached digest AND toggle is enabled, skip UI operations
3. **Cache Miss**: Full UI automation, then update cache
4. **Invalidation**: On model switch, new chat, or explicit clear

### Performance Impact

| Scenario | Latency |
|----------|---------|
| Cache HIT (same tools) | ~50ms |
| Cache MISS (different tools) | ~2-4 seconds |
| Emulated mode | ~100ms |

### Monitoring Cache Performance

Enable cache logging to monitor:

```bash
FUNCTION_CALLING_DEBUG=true
FC_DEBUG_CACHE=true
```

Log output:
```
[FC:CACHE] HIT - digest=a1b2c3..., skip UI operations
[FC:CACHE] MISS - reason=digest_mismatch, performing UI setup
```

---

## Troubleshooting

### Common Issues

#### "Tool calls not detected"

**Symptoms**: Model outputs text instead of structured function calls

**Causes & Solutions**:
1. **Model behavior**: Gemini may sometimes output text format even with native FC enabled
   - The proxy has fallback parsing that handles this automatically
   - Check logs for `Recovered function calls from emulated text`

2. **UI automation failed**: Check if toggle was properly enabled
   ```bash
   FUNCTION_CALLING_DEBUG=true
   FC_DEBUG_UI=true
   ```

3. **Cache desync**: Try clearing cache
   - Switch models or start new chat to invalidate

#### "Function name truncated"

**Symptoms**: `gh_grep_searchGitH` instead of `gh_grep_searchGitHub`

**Cause**: Model hallucination in text-format output

**Solution**: The proxy now includes fuzzy matching to auto-correct truncated names (70% threshold)

#### "Invalid tool schema error"

**Symptoms**: 400 error when sending tools

**Cause**: Unsupported JSON Schema fields

**Solution**: Remove unsupported fields:
```javascript
// Remove these from your tool parameters:
// minimum, maximum, pattern, minLength, maxLength
// minItems, maxItems, $schema, $id, $ref
```

#### "UI automation timeout"

**Symptoms**: Native mode fails, falls back to emulated

**Solutions**:
1. Increase timeout: `FUNCTION_CALLING_UI_TIMEOUT=10000`
2. Check if AI Studio UI has changed (selectors may need updating)
3. Try `FUNCTION_CALLING_MODE=emulated` as workaround

### Conflict with Google Search / URL Context

Native function calling is **mutually exclusive** with:
- Google Search grounding
- URL Context

The proxy automatically disables these features when native FC is active.

---

## Debug Logging

### Enable Debug Logging

The function calling subsystem has a powerful modular logging system.

```bash
# Master switch
# When true, ALL modules are enabled by default.
FUNCTION_CALLING_DEBUG=true

# Optional: Disable specific modules to reduce noise
FC_DEBUG_WIRE=false
FC_DEBUG_DOM=false
```

### Modular Logging Configuration

If you want granular control, you can enable only what you need:

1. Set `FUNCTION_CALLING_DEBUG=true`
2. Individual modules default to `true`. Set them to `false` to disable.

| Module | Description | Log File |
|--------|-------------|----------|
| `FC_DEBUG_ORCHESTRATOR` | Overall flow and mode selection | `fc_orchestrator.log` |
| `FC_DEBUG_UI` | Browser automation steps | `fc_ui.log` |
| `FC_DEBUG_CACHE` | Cache hits/misses | `fc_cache.log` |
| `FC_DEBUG_WIRE` | Network response parsing | `fc_wire.log` |
| `FC_DEBUG_DOM` | HTML extraction | `fc_dom.log` |
| `FC_DEBUG_SCHEMA` | Tool conversion | `fc_schema.log` |
| `FC_DEBUG_RESPONSE` | Final formatting | `fc_response.log` |

### Log File Locations

Logs are written to `logs/fc_debug/`.

---

## Related Documentation

- [ADR-001: Native Function Calling Architecture](../architecture/ADR-001-native-function-calling.md) - Architecture decision record
- [Environment Variables Reference](./env-variables-reference.md) - Complete configuration reference

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-26 | Initial release |

---

*Last Updated: 2025-12-26*
