# OpenAI API Compatibility Note

This document details the compatibility, differences, and limitations of the AI Studio Proxy API compared to the official OpenAI API.

> **API Usage Guide**: For specific request examples and client configuration, please refer to [API Usage Guide](api-usage.md)

---

## Overview

AI Studio Proxy API provides maximum compatibility with OpenAI API, allowing existing applications using OpenAI SDK to seamlessly switch to Google AI Studio. However, due to underlying implementation differences (accessing AI Studio Web UI via browser automation), there are some unavoidable limitations.

---

## Endpoint Support

### ✅ Fully Supported

| Endpoint | Description |
|---|---|
| `POST /v1/chat/completions` | Chat completions, supports streaming and non-streaming |
| `GET /v1/models` | Model list |

### ⚠️ Custom Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /api/info` | API information |
| `GET /v1/queue` | Queue status |
| `POST /v1/cancel/{req_id}` | Cancel request |
| `/api/keys` | Key management |

### ❌ Not Supported

- `/v1/embeddings` - Embeddings
- `/v1/images/generations` - Image generation
- `/v1/audio/*` - Audio processing
- `/v1/files` - File management
- `/v1/fine-tuning/*` - Fine-tuning

---

## Parameter Support

### ✅ Fully Supported

| Parameter | Description |
|---|---|
| `messages` | Chat message array |
| `model` | Model ID |
| `stream` | Streaming output |
| `temperature` | Temperature parameter (0.0-2.0) |
| `max_output_tokens` | Maximum output tokens |
| `top_p` | Top-P sampling |
| `stop` | Stop sequences |

### ⚠️ Partially Supported

| Parameter | Limitation |
|---|---|
| `reasoning_effort` | Custom parameter, controls thinking mode |
| `tools` | Supports Google Search, limited custom tools |
| `tool_choice` | Only supports `"auto"`, `"none"` |
| `response_format` | Depends on AI Studio capability |
| `seed` | Accepted but reproducibility not guaranteed |

### ❌ Not Supported

| Parameter | Reason |
|---|---|
| `frequency_penalty` | AI Studio does not support |
| `presence_penalty` | AI Studio does not support |
| `logit_bias` | AI Studio does not support |
| `logprobs` | AI Studio does not support |
| `n` | Multiple replies not supported |

---

## Major Differences

### 1. Concurrency Processing

**Mechanism**: Single browser instance, all requests are **queued and processed sequentially**.

**Impact**:
- Increased response time in high concurrency scenarios
- Streaming requests also need to wait for preceding ones to complete

**Recommendation**: Suitable for personal use or low concurrency scenarios.

### 2. Rate Limits

Limits come from **Google AI Studio** account limits, bound to the Google account.

### 3. Response Latency

Accessing via browser automation incurs extra overhead.

**Mitigation**:
- Use integrated streaming proxy (default enabled)
- Avoid frequent model switching

### 4. Token Counting

Token count in `usage` field is an **estimate**, error approx. ±10%.

### 5. Thinking Content (reasoning_content)

**Extension field**, returns AI Studio's "thinking" process:

```json
{
  "message": {
    "role": "assistant",
    "content": "Final Answer",
    "reasoning_content": "Thinking Process"
  }
}
```

OpenAI SDK will ignore this field, normal usage is not affected.

### 6. Model Switching

- Switching takes 2-5 seconds
- Continuous use of same model performs better
- Model ID must exist in `/v1/models` list

### 7. Function Calling

| Feature | Support Status |
|---|---|
| Google Search | ✅ Native Support |
| Custom Function | ⚠️ Requires MCP Adapter |
| OpenAI Native Format | ❌ Direct passthrough not supported |

---

## Three-Layer Response Mechanism Impact on Parameters

| Layer | Parameter Support | Performance |
|---|---|---|
| **Streaming Proxy** (Default) | Basic Parameters | ⚡ Best |
| **Helper Service** | Implementation Dependent | ⚡⚡ Medium |
| **Playwright** | All Parameters | ⚡⚡⚡ Higher Latency |

To require full parameter support, disable streaming proxy:
```env
STREAM_PORT=0
```

---

## Best Practices

### Client Configuration

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key",
    timeout=60.0  # Appropriately increase timeout
)
```

### Error Handling

```python
from openai import APIError
import time

def chat_with_retry(client, messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model="gemini-2.5-pro-preview",
                messages=messages
            )
        except APIError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
```

### Performance Optimization

1. **Enable Streaming Proxy**: `STREAM_PORT=3120`
2. **Avoid Frequent Model Switching**
3. **Reasonable Timeout Config**: `RESPONSE_COMPLETION_TIMEOUT=300000`

---

## Common Issues

### Streaming Response Interrupted

**Check**:
1. `/health` confirm service status
2. View `logs/app.log`
3. Try `STREAM_PORT=0` to use Playwright mode

### Empty Model List

**Check**:
1. Wait for service to fully start
2. Update auth file (`--debug` mode)
3. View `errors_py/` error snapshots

### Parameters Not Taking Effect

**Check**:
1. Confirm if using streaming proxy mode
2. View logs to confirm if parameters are set successfully
3. Refer to AI Studio official documentation for model limitations

---

## Related Documentation

- [API Usage Guide](api-usage.md) - Detailed API endpoint description and code examples
- [Streaming Modes Explained](streaming-modes.md) - Three-layer response mechanism
- [Troubleshooting Guide](troubleshooting.md) - Common issue solutions
