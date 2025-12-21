# OpenAI API 兼容性说明

本文档详细说明 AI Studio Proxy API 与官方 OpenAI API 的兼容性、差异和限制。

> **API 使用指南**: 关于具体请求示例和客户端配置，请参阅 [API 使用指南](api-usage.md)

---

## 概述

AI Studio Proxy API 提供与 OpenAI API 最大程度的兼容性，使现有使用 OpenAI SDK 的应用可以无缝切换到 Google AI Studio。但由于底层实现差异（通过浏览器自动化访问 AI Studio Web UI），存在一些不可避免的限制。

---

## 端点支持

### ✅ 完全支持

| 端点 | 说明 |
|------|------|
| `POST /v1/chat/completions` | 聊天完成，支持流式和非流式 |
| `GET /v1/models` | 模型列表 |

### ⚠️ 自定义端点

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `GET /api/info` | API 信息 |
| `GET /v1/queue` | 队列状态 |
| `POST /v1/cancel/{req_id}` | 取消请求 |
| `/api/keys` | 密钥管理 |

### ❌ 不支持

- `/v1/embeddings` - 嵌入向量
- `/v1/images/generations` - 图像生成
- `/v1/audio/*` - 音频处理
- `/v1/files` - 文件管理
- `/v1/fine-tuning/*` - 微调

---

## 参数支持

### ✅ 完全支持

| 参数 | 说明 |
|------|------|
| `messages` | 聊天消息数组 |
| `model` | 模型 ID |
| `stream` | 流式输出 |
| `temperature` | 温度参数 (0.0-2.0) |
| `max_output_tokens` | 最大输出 token |
| `top_p` | Top-P 采样 |
| `stop` | 停止序列 |

### ⚠️ 部分支持

| 参数 | 限制 |
|------|------|
| `reasoning_effort` | 自定义参数，控制思考模式 |
| `tools` | 支持 Google Search，自定义工具有限 |
| `tool_choice` | 仅支持 `"auto"`, `"none"` |
| `response_format` | 取决于 AI Studio 能力 |
| `seed` | 接受但不保证可重现性 |

### ❌ 不支持

| 参数 | 原因 |
|------|------|
| `frequency_penalty` | AI Studio 不支持 |
| `presence_penalty` | AI Studio 不支持 |
| `logit_bias` | AI Studio 不支持 |
| `logprobs` | AI Studio 不支持 |
| `n` | 不支持多回复 |

---

## 主要差异

### 1. 并发处理

**机制**: 单浏览器实例，所有请求**排队顺序处理**。

**影响**:
- 高并发场景响应时间延长
- 流式请求也需等待前序完成

**建议**: 适合个人使用或低并发场景。

### 2. 速率限制

限制来源于 **Google AI Studio** 账户限制，与 Google 账号绑定。

### 3. 响应延迟

通过浏览器自动化访问，存在额外开销。

**缓解措施**:
- 使用集成流式代理（默认启用）
- 避免频繁切换模型

### 4. Token 计数

`usage` 字段中的 token 数量是**估算值**，误差约 ±10%。

### 5. 思考内容 (reasoning_content)

**扩展字段**，返回 AI Studio 的 "thinking" 过程：

```json
{
  "message": {
    "role": "assistant",
    "content": "最终回答",
    "reasoning_content": "思考过程"
  }
}
```

OpenAI SDK 会忽略此字段，不影响正常使用。

### 6. 模型切换

- 切换需要 2-5 秒
- 连续使用相同模型性能更好
- 模型 ID 必须存在于 `/v1/models` 列表中

### 7. 函数调用

| 功能 | 支持情况 |
|------|----------|
| Google Search | ✅ 原生支持 |
| 自定义函数 | ⚠️ 需要 MCP 适配器 |
| OpenAI 原生格式 | ❌ 不支持直接透传 |

---

## 三层响应机制对参数的影响

| 层级 | 参数支持 | 性能 |
|------|----------|------|
| **流式代理** (默认) | 基础参数 | ⚡ 最优 |
| **Helper 服务** | 取决于实现 | ⚡⚡ 中等 |
| **Playwright** | 所有参数 | ⚡⚡⚡ 较高延迟 |

如需完整参数支持，禁用流式代理：
```env
STREAM_PORT=0
```

---

## 最佳实践

### 客户端配置

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key",
    timeout=60.0  # 适当增加超时
)
```

### 错误处理

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

### 性能优化

1. **启用流式代理**: `STREAM_PORT=3120`
2. **避免频繁切换模型**
3. **合理配置超时**: `RESPONSE_COMPLETION_TIMEOUT=300000`

---

## 常见问题

### 流式响应中断

**检查**:
1. `/health` 确认服务状态
2. 查看 `logs/app.log`
3. 尝试 `STREAM_PORT=0` 使用 Playwright 模式

### 模型列表为空

**检查**:
1. 等待服务完全启动
2. 更新认证文件 (`--debug` 模式)
3. 查看 `errors_py/` 错误快照

### 参数不生效

**检查**:
1. 确认是否使用流式代理模式
2. 查看日志确认参数是否设置成功
3. 参考 AI Studio 官方文档了解模型限制

---

## 相关文档

- [API 使用指南](api-usage.md) - 端点详细说明和代码示例
- [流式处理模式详解](streaming-modes.md) - 三层响应机制
- [故障排除指南](troubleshooting.md) - 常见问题解决
