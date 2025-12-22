# API Usage Guide

This guide details how to use various functions and endpoints of the AI Studio Proxy API.

## Server Configuration

The proxy server listens on `http://127.0.0.1:2048` by default.

**Configuration Methods**:
- **Environment Variable**: Set `PORT=2048` in `.env` file
- **Command Line Argument**: `--server-port 2048`
- **GUI Launcher**: Configure directly in the graphical interface

---

## API Authentication

### Key Configuration

The project uses `auth_profiles/key.txt` to manage API keys:

```
your-api-key-1
your-api-key-2
# Comment lines are ignored
```

**Validation Logic**:
- If the file is empty or does not exist, authentication is not required
- When keys are configured, all `/v1/*` requests require a valid key (except `/v1/models`)

### Authentication Methods

```bash
# Bearer Token (Recommended)
Authorization: Bearer your-api-key

# X-API-Key (Alternative)
X-API-Key: your-api-key
```

---

## API Endpoints

### Chat Interface

**Endpoint**: `POST /v1/chat/completions`

Fully compatible with OpenAI API, supports streaming and non-streaming responses.

#### Supported Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `messages` | Array | Chat message array (Required) |
| `model` | String | Model ID |
| `stream` | Boolean | Whether to stream output |
| `temperature` | Number | Temperature parameter (0.0-2.0) |
| `max_output_tokens` | Number | Maximum output tokens |
| `top_p` | Number | Top-P sampling (0.0-1.0) |
| `stop` | Array/String | Stop sequences |
| `reasoning_effort` | String/Number | Thinking mode control |
| `tools` | Array | Tool definitions (Supports google_search) |

#### reasoning_effort Parameter Details

| Value | Effect |
|-------|--------|
| `0` or `"0"` | Disable thinking mode |
| Number (e.g. `8000`) | Enable thinking, limit budget |
| `"none"` or `-1` | Enable thinking, unlimited budget |
| `"low"` / `"high"` | Thinking level (Some models) |

#### Request Example

```bash
# Non-streaming
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-pro-preview",
    "messages": [{"role": "user", "content": "Hello"}],
    "temperature": 0.7
  }'

# Streaming
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-pro-preview",
    "messages": [{"role": "user", "content": "Tell me a story"}],
    "stream": true
  }' --no-buffer
```

---

### Model List

**Endpoint**: `GET /v1/models`

Returns the list of available models in AI Studio.

**Features**:
- Dynamically retrieves models from AI Studio page
- Supports excluding specific models via `excluded_models.txt`
- Script-injected models are marked with `"injected": true`

---

### Health Check

**Endpoint**: `GET /health`

Returns service status:
- Playwright status
- Browser connection status
- Page status
- Queue length

---

### Other Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/info` | GET | API configuration info |
| `/v1/queue` | GET | Queue status |
| `/v1/cancel/{req_id}` | POST | Cancel request |
| `/ws/logs` | WebSocket | Real-time log stream |
| `/api/keys` | GET/POST/DELETE | Key management |

---

## Client Configuration

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key"  # Or any value
)

response = client.chat.completions.create(
    model="gemini-2.5-pro-preview",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)
```

### JavaScript (OpenAI SDK)

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:2048/v1",
  apiKey: "your-api-key"
});

const response = await client.chat.completions.create({
  model: "gemini-2.5-pro-preview",
  messages: [{ role: "user", content: "Hello" }]
});
console.log(response.choices[0].message.content);
```

### Open WebUI

1. Go to "Settings" -> "Connections"
2. Add model
3. **API Base URL**: `http://127.0.0.1:2048/v1`
4. **API Key**: Leave blank or any value
5. Save settings

---

## Important Notes

### Three-Layer Response Acquisition Mechanism

1. **Integrated Streaming Proxy** (Default, port 3120): Best performance
2. **External Helper Service** (Optional): Backup solution
3. **Playwright Page Interaction** (Fallback): Full parameter support

> See [Streaming Modes Explained](streaming-modes.md) for details

### Considerations

- **Serial Processing**: Single browser instance, requests are queued
- **Client Managed History**: Client is responsible for maintaining chat history
- **Model Switch Latency**: First switch takes 2-5 seconds

---

## Related Documentation

- [OpenAI Compatibility Note](openai-compatibility.md) - Differences from OpenAI API
- [Environment Variables Reference](env-variables-reference.md) - Configuration parameters
- [Client Integration Examples](client-examples.md) - More code examples
- [Troubleshooting Guide](troubleshooting.md) - Problem solving
