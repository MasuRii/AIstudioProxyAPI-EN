# Client Integration Examples

This document provides example code for integrating AI Studio Proxy API with various programming languages and client tools.

---

## 📋 Table of Contents

- [cURL Command Line](#curl-command-line)
- [Python](#python)
- [JavaScript / Node.js](#javascript--nodejs)
- [Client Tools](#client-tools)

---

## cURL Command Line

### Health Check

```bash
curl http://127.0.0.1:2048/health
```

### Get Model List

```bash
curl http://127.0.0.1:2048/v1/models
```

### Non-Streaming Chat Request

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [
      {
        "role": "user",
        "content": "Hello, please introduce yourself"
      }
    ],
    "stream": false,
    "temperature": 0.7,
    "max_output_tokens": 2048
  }'
```

### Streaming Chat Request (SSE)

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "gemini-1.5-flash",
    "messages": [
      {
        "role": "user",
        "content": "Tell me a story about AI"
      }
    ],
    "stream": true
  }' --no-buffer
```

### Request with Parameters

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [
      {
        "role": "system",
        "content": "You are a professional Python developer"
      },
      {
        "role": "user",
        "content": "How to implement concurrency using asyncio?"
      }
    ],
    "stream": false,
    "temperature": 0.5,
    "max_output_tokens": 4096,
    "top_p": 0.9,
    "stop": ["\n\nUser:", "\n\nAssistant:"]
  }'
```

---

## Python

### Using OpenAI SDK

#### Installation

```bash
pip install openai
```

#### Basic Usage

```python
from openai import OpenAI

# Initialize client
client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key"  # Can be any value if server doesn't require auth
)

# Non-streaming request
def basic_chat():
    response = client.chat.completions.create(
        model="gemini-1.5-pro",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "What is FastAPI?"}
        ]
    )

    print(response.choices[0].message.content)

basic_chat()
```

#### Streaming Response

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key"
)

def streaming_chat():
    stream = client.chat.completions.create(
        model="gemini-1.5-pro",
        messages=[
            {"role": "user", "content": "Tell me a story about machine learning"}
        ],
        stream=True
    )

    print("AI: ", end="", flush=True)
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()  # Newline

streaming_chat()
```

#### Request with Parameters

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key"
)

def advanced_chat():
    response = client.chat.completions.create(
        model="gemini-1.5-pro",
        messages=[
            {"role": "system", "content": "You are a Python expert"},
            {"role": "user", "content": "Explain how decorators work"}
        ],
        temperature=0.7,
        max_tokens=2048,
        top_p=0.9,
        stop=["\n\nUser:", "\n\nAssistant:"]
    )

    print(response.choices[0].message.content)
    print(f"\nTokens used: {response.usage.total_tokens}")

advanced_chat()
```

#### Error Handling

```python
from openai import OpenAI, APIError, APIConnectionError
import time

client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key",
    timeout=60.0
)

def chat_with_retry(messages, max_retries=3):
    """Chat with retry mechanism"""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gemini-1.5-pro",
                messages=messages
            )
            return response.choices[0].message.content

        except APIConnectionError as e:
            print(f"Connection error (Attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise

        except APIError as e:
            print(f"API Error: {e}")
            raise

# Usage example
try:
    result = chat_with_retry([
        {"role": "user", "content": "Hello"}
    ])
    print(result)
except Exception as e:
    print(f"Request failed: {e}")
```

### Using requests Library

#### Installation

```bash
pip install requests
```

#### Non-Streaming Request

```python
import requests
import json

def chat_non_streaming():
    url = "http://127.0.0.1:2048/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer your-api-key"
    }
    data = {
        "model": "gemini-1.5-pro",
        "messages": [
            {"role": "user", "content": "What is Deep Learning?"}
        ],
        "stream": False
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        result = response.json()
        print(result['choices'][0]['message']['content'])
    else:
        print(f"Error {response.status_code}: {response.text}")

chat_non_streaming()
```

#### Streaming Request (SSE)

```python
import requests
import json

def chat_streaming():
    url = "http://127.0.0.1:2048/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer your-api-key"
    }
    data = {
        "model": "gemini-1.5-pro",
        "messages": [
            {"role": "user", "content": "Tell me a story"}
        ],
        "stream": True
    }

    response = requests.post(url, headers=headers, json=data, stream=True)

    print("AI: ", end="", flush=True)
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data_str = line[6:]  # Remove 'data: ' prefix

                if data_str.strip() == '[DONE]':
                    print("\n")
                    break

                try:
                    chunk = json.loads(data_str)
                    if 'choices' in chunk:
                        delta = chunk['choices'][0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            print(content, end="", flush=True)
                except json.JSONDecodeError:
                    continue

chat_streaming()
```

---

## JavaScript / Node.js

> **Note**: The following code examples show how to connect to the AI Studio Proxy API as a **client**. These codes are intended to run in your application to send requests to the Proxy server, not to run as server code.

### Using OpenAI SDK

#### Installation

```bash
npm install openai
```

#### Basic Usage

```javascript
// Note: This example uses ES Modules syntax.
// If you use CommonJS (require), use: const OpenAI = require('openai');
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:2048/v1",
  apiKey: "your-api-key",
});

// Non-streaming request
async function basicChat() {
  const response = await client.chat.completions.create({
    model: "gemini-1.5-pro",
    messages: [
      { role: "system", content: "You are a helpful assistant" },
      { role: "user", content: "What is Node.js?" },
    ],
  });

  console.log(response.choices[0].message.content);
}

basicChat();
```

#### Streaming Response

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:2048/v1",
  apiKey: "your-api-key",
});

async function streamingChat() {
  const stream = await client.chat.completions.create({
    model: "gemini-1.5-pro",
    messages: [{ role: "user", content: "Tell me a story about programming" }],
    stream: true,
  });

  process.stdout.write("AI: ");
  for await (const chunk of stream) {
    const content = chunk.choices[0]?.delta?.content || "";
    process.stdout.write(content);
  }
  console.log("\n");
}

streamingChat();
```

#### Error Handling

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:2048/v1",
  apiKey: "your-api-key",
  timeout: 60 * 1000, // 60s timeout
});

async function chatWithRetry(messages, maxRetries = 3) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await client.chat.completions.create({
        model: "gemini-1.5-pro",
        messages: messages,
      });

      return response.choices[0].message.content;
    } catch (error) {
      console.error(`Attempt ${attempt + 1}/${maxRetries} failed:`, error.message);

      if (attempt < maxRetries - 1) {
        // Exponential backoff
        await new Promise((resolve) =>
          setTimeout(resolve, 2 ** attempt * 1000),
        );
        continue;
      }

      throw error;
    }
  }
}

// Usage example
chatWithRetry([{ role: "user", content: "Hello" }])
  .then((result) => {
    console.log(result);
  })
  .catch((error) => {
    console.error("Request failed:", error);
  });
```

### Using Fetch API

> **Note**: Node.js 18+ has built-in fetch API. If you use an older version, you may need to install `node-fetch`.

```javascript
// Non-streaming request
async function chatNonStreaming() {
  const response = await fetch("http://127.0.0.1:2048/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer your-api-key",
    },
    body: JSON.stringify({
      model: "gemini-1.5-pro",
      messages: [{ role: "user", content: "What is JavaScript?" }],
      stream: false,
    }),
  });

  const data = await response.json();
  console.log(data.choices[0].message.content);
}

// Streaming request
async function chatStreaming() {
  const response = await fetch("http://127.0.0.1:2048/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer your-api-key",
    },
    body: JSON.stringify({
      model: "gemini-1.5-pro",
      messages: [{ role: "user", content: "Tell me a story" }],
      stream: true,
    }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  process.stdout.write("AI: ");
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split("\n");

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6);
        if (data.trim() === "[DONE]") {
          console.log("\n");
          return;
        }

        try {
          const parsed = JSON.parse(data);
          const content = parsed.choices[0]?.delta?.content || "";
          process.stdout.write(content);
        } catch (e) {
          // Ignore parse errors
        }
      }
    }
  }
}

chatNonStreaming();
chatStreaming();
```

---

## Client Tools

### Open WebUI

**Configuration Steps**:

1. Open Open WebUI
2. Go to "Settings" -> "Connections"
3. In "Models" section, click "Add Model"
4. Configure as follows:
   - **Model Name**: `aistudio-gemini`
   - **API Base URL**: `http://127.0.0.1:2048/v1`
   - **API Key**: Enter valid key or leave blank (depending on server config)
5. Save settings

### ChatBox

**Configuration Steps**:

1. Open ChatBox
2. Go to "Settings" -> "AI Provider"
3. Select "OpenAI API"
4. Configure as follows:
   - **API Domain**: `http://127.0.0.1:2048`
   - **API Key**: Enter valid key
   - **Model**: Select model from dropdown
5. Save settings

### LobeChat

**Configuration Steps**:

1. Open LobeChat
2. Click settings icon on top right
3. Go to "Language Model" settings
4. Select "OpenAI"
5. Configure as follows:
   - **API Proxy URL**: `http://127.0.0.1:2048/v1`
   - **API Key**: Enter valid key
6. Save settings

### Continue (VS Code Extension)

**Configuration Steps**:

1. Install Continue extension in VS Code
2. Open Continue settings (JSON)
3. Add configuration:

```json
{
  "models": [
    {
      "title": "AI Studio Gemini",
      "provider": "openai",
      "model": "gemini-1.5-pro",
      "apiBase": "http://127.0.0.1:2048/v1",
      "apiKey": "your-api-key"
    }
  ]
}
```

4. Save and reload VS Code

---

## Best Practices

### 1. Error Handling

Always implement error handling and retry mechanisms:

```python
def robust_chat(client, messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gemini-1.5-pro",
                messages=messages,
                timeout=60
            )
            return response
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
```

### 2. Timeout Settings

Set reasonable timeouts for requests:

```python
client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key",
    timeout=60.0  # 60s timeout
)
```

### 3. Streaming

Prefer streaming response for long text generation:

```python
stream = client.chat.completions.create(
    model="gemini-1.5-pro",
    messages=[{"role": "user", "content": "Write a long article"}],
    stream=True
)

for chunk in stream:
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)
```

### 4. Parameter Tuning

Adjust parameters based on scenario:

```python
# Creative Writing - High Temperature
response = client.chat.completions.create(
    model="gemini-1.5-pro",
    messages=[{"role": "user", "content": "Write a poem"}],
    temperature=0.9,
    max_tokens=2048
)

# Technical Q&A - Low Temperature
response = client.chat.completions.create(
    model="gemini-1.5-pro",
    messages=[{"role": "user", "content": "What is REST API?"}],
    temperature=0.3,
    max_tokens=1024
)
```

---

## Troubleshooting

### Connection Error

**Issue**: Unable to connect to server

**Solution**:

```bash
# Check if server is running
curl http://127.0.0.1:2048/health

# Check if port is correct
# If using custom port, modify base_url
```

### Authentication Error

**Issue**: 401 Unauthorized

**Solution**:

```python
# Ensure valid API key is provided
client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-valid-api-key"  # Use valid key
)
```

### Timeout Error

**Issue**: Request timeout

**Solution**:

```python
# Increase timeout duration
client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key",
    timeout=120.0  # Increase to 120 seconds
)
```

---

## Related Documentation

- [API Usage Guide](api-usage.md) - Detailed API endpoint description
- [OpenAI Compatibility Note](openai-compatibility.md) - Compatibility and limitations
- [Troubleshooting Guide](troubleshooting.md) - Common issue solutions

---

If you have questions or need more examples, please submit an Issue.
