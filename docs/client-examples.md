# 客户端集成示例

本文档提供各种编程语言和客户端工具集成 AI Studio Proxy API 的示例代码。

---

## 📋 目录

- [cURL 命令行](#curl-命令行)
- [Python](#python)
- [JavaScript / Node.js](#javascript--nodejs)
- [客户端工具](#客户端工具)

---

## cURL 命令行

### 健康检查

```bash
curl http://127.0.0.1:2048/health
```

### 获取模型列表

```bash
curl http://127.0.0.1:2048/v1/models
```

### 非流式聊天请求

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [
      {
        "role": "user",
        "content": "你好，请介绍一下自己"
      }
    ],
    "stream": false,
    "temperature": 0.7,
    "max_output_tokens": 2048
  }'
```

### 流式聊天请求 (SSE)

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "gemini-1.5-flash",
    "messages": [
      {
        "role": "user",
        "content": "请讲一个关于人工智能的故事"
      }
    ],
    "stream": true
  }' --no-buffer
```

### 带参数的请求

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [
      {
        "role": "system",
        "content": "你是一位专业的 Python 开发者"
      },
      {
        "role": "user",
        "content": "如何使用 asyncio 实现并发?"
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

### 使用 OpenAI SDK

#### 安装

```bash
pip install openai
```

#### 基本用法

```python
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key"  # 如果服务器不需要认证，可以是任意值
)

# 非流式请求
def basic_chat():
    response = client.chat.completions.create(
        model="gemini-1.5-pro",
        messages=[
            {"role": "system", "content": "你是一个有用的助手"},
            {"role": "user", "content": "什么是 FastAPI?"}
        ]
    )

    print(response.choices[0].message.content)

basic_chat()
```

#### 流式响应

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
            {"role": "user", "content": "请讲一个关于机器学习的故事"}
        ],
        stream=True
    )

    print("AI: ", end="", flush=True)
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()  # 换行

streaming_chat()
```

#### 带参数的请求

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
            {"role": "system", "content": "你是一个 Python 专家"},
            {"role": "user", "content": "解释装饰器的工作原理"}
        ],
        temperature=0.7,
        max_tokens=2048,
        top_p=0.9,
        stop=["\n\n用户:", "\n\n助手:"]
    )

    print(response.choices[0].message.content)
    print(f"\n使用的 tokens: {response.usage.total_tokens}")

advanced_chat()
```

#### 错误处理

```python
from openai import OpenAI, APIError, APIConnectionError
import time

client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key",
    timeout=60.0
)

def chat_with_retry(messages, max_retries=3):
    """带重试机制的聊天"""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gemini-1.5-pro",
                messages=messages
            )
            return response.choices[0].message.content

        except APIConnectionError as e:
            print(f"连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
                continue
            raise

        except APIError as e:
            print(f"API 错误: {e}")
            raise

# 使用示例
try:
    result = chat_with_retry([
        {"role": "user", "content": "你好"}
    ])
    print(result)
except Exception as e:
    print(f"请求失败: {e}")
```

### 使用 requests 库

#### 安装

```bash
pip install requests
```

#### 非流式请求

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
            {"role": "user", "content": "什么是深度学习?"}
        ],
        "stream": False
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        result = response.json()
        print(result['choices'][0]['message']['content'])
    else:
        print(f"错误 {response.status_code}: {response.text}")

chat_non_streaming()
```

#### 流式请求 (SSE)

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
            {"role": "user", "content": "请讲一个故事"}
        ],
        "stream": True
    }

    response = requests.post(url, headers=headers, json=data, stream=True)

    print("AI: ", end="", flush=True)
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data_str = line[6:]  # 移除 'data: ' 前缀

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

> **注意**: 以下代码示例展示了如何作为**客户端**连接到 AI Studio Proxy API。这些代码旨在您的应用程序中运行，用于向 Proxy 服务器发送请求，而不是作为服务器代码运行。

### 使用 OpenAI SDK

#### 安装

```bash
npm install openai
```

#### 基本用法

```javascript
// 注意：此示例使用 ES Modules 语法。
// 如果您使用 CommonJS (require)，请改用: const OpenAI = require('openai');
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:2048/v1",
  apiKey: "your-api-key",
});

// 非流式请求
async function basicChat() {
  const response = await client.chat.completions.create({
    model: "gemini-1.5-pro",
    messages: [
      { role: "system", content: "你是一个有用的助手" },
      { role: "user", content: "什么是 Node.js?" },
    ],
  });

  console.log(response.choices[0].message.content);
}

basicChat();
```

#### 流式响应

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:2048/v1",
  apiKey: "your-api-key",
});

async function streamingChat() {
  const stream = await client.chat.completions.create({
    model: "gemini-1.5-pro",
    messages: [{ role: "user", content: "请讲一个关于编程的故事" }],
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

#### 错误处理

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:2048/v1",
  apiKey: "your-api-key",
  timeout: 60 * 1000, // 60秒超时
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
      console.error(`尝试 ${attempt + 1}/${maxRetries} 失败:`, error.message);

      if (attempt < maxRetries - 1) {
        // 指数退避
        await new Promise((resolve) =>
          setTimeout(resolve, 2 ** attempt * 1000),
        );
        continue;
      }

      throw error;
    }
  }
}

// 使用示例
chatWithRetry([{ role: "user", content: "你好" }])
  .then((result) => {
    console.log(result);
  })
  .catch((error) => {
    console.error("请求失败:", error);
  });
```

### 使用 Fetch API

> **注意**: Node.js 18+ 内置了 fetch API。如果您使用旧版本，可能需要安装 `node-fetch`。

```javascript
// 非流式请求
async function chatNonStreaming() {
  const response = await fetch("http://127.0.0.1:2048/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer your-api-key",
    },
    body: JSON.stringify({
      model: "gemini-1.5-pro",
      messages: [{ role: "user", content: "什么是 JavaScript?" }],
      stream: false,
    }),
  });

  const data = await response.json();
  console.log(data.choices[0].message.content);
}

// 流式请求
async function chatStreaming() {
  const response = await fetch("http://127.0.0.1:2048/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer your-api-key",
    },
    body: JSON.stringify({
      model: "gemini-1.5-pro",
      messages: [{ role: "user", content: "请讲一个故事" }],
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
          // 忽略解析错误
        }
      }
    }
  }
}

chatNonStreaming();
chatStreaming();
```

---

## 客户端工具

### Open WebUI

**配置步骤**:

1. 打开 Open WebUI
2. 进入 "设置" → "连接"
3. 在 "模型" 部分，点击 "添加模型"
4. 配置如下:
   - **模型名称**: `aistudio-gemini`
   - **API 基础 URL**: `http://127.0.0.1:2048/v1`
   - **API 密钥**: 输入有效密钥或留空（根据服务器配置）
5. 保存设置

### ChatBox

**配置步骤**:

1. 打开 ChatBox
2. 进入 "设置" → "AI 提供商"
3. 选择 "OpenAI API"
4. 配置如下:
   - **API 域名**: `http://127.0.0.1:2048`
   - **API 密钥**: 输入有效密钥
   - **模型**: 从下拉列表选择模型
5. 保存设置

### LobeChat

**配置步骤**:

1. 打开 LobeChat
2. 点击右上角设置图标
3. 进入 "语言模型" 设置
4. 选择 "OpenAI"
5. 配置如下:
   - **API 地址**: `http://127.0.0.1:2048/v1`
   - **API Key**: 输入有效密钥
6. 保存设置

### Continue (VS Code 扩展)

**配置步骤**:

1. 在 VS Code 中安装 Continue 扩展
2. 打开 Continue 设置 (JSON)
3. 添加配置:

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

4. 保存并重载 VS Code

---

## 最佳实践

### 1. 错误处理

始终实现错误处理和重试机制：

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

### 2. 超时设置

为请求设置合理的超时时间：

```python
client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key",
    timeout=60.0  # 60秒超时
)
```

### 3. 流式处理

对于长文本生成，优先使用流式响应：

```python
stream = client.chat.completions.create(
    model="gemini-1.5-pro",
    messages=[{"role": "user", "content": "写一篇长文"}],
    stream=True
)

for chunk in stream:
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)
```

### 4. 参数调优

根据场景调整参数：

```python
# 创意写作 - 高温度
response = client.chat.completions.create(
    model="gemini-1.5-pro",
    messages=[{"role": "user", "content": "写一首诗"}],
    temperature=0.9,
    max_tokens=2048
)

# 技术问答 - 低温度
response = client.chat.completions.create(
    model="gemini-1.5-pro",
    messages=[{"role": "user", "content": "什么是REST API?"}],
    temperature=0.3,
    max_tokens=1024
)
```

---

## 故障排除

### 连接错误

**问题**: 无法连接到服务器

**解决方案**:

```bash
# 检查服务器是否运行
curl http://127.0.0.1:2048/health

# 检查端口是否正确
# 如果使用自定义端口，需要修改 base_url
```

### 认证错误

**问题**: 401 Unauthorized

**解决方案**:

```python
# 确保提供了有效的 API 密钥
client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-valid-api-key"  # 使用有效密钥
)
```

### 超时错误

**问题**: 请求超时

**解决方案**:

```python
# 增加超时时间
client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key",
    timeout=120.0  # 增加到 120 秒
)
```

---

## 相关文档

- [API 使用指南](api-usage.md) - 详细的 API 端点说明
- [OpenAI 兼容性说明](openai-compatibility.md) - 兼容性和限制
- [故障排除指南](troubleshooting.md) - 常见问题解决

---

如有问题或需要更多示例，请提交 Issue。
