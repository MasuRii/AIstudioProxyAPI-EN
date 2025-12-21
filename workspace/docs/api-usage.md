# API 使用指南

本指南详细介绍如何使用 AI Studio Proxy API 的各种功能和端点。

## 服务器配置

代理服务器默认监听 `http://127.0.0.1:2048`。

**配置方式**:
- **环境变量**: `.env` 文件中设置 `PORT=2048`
- **命令行参数**: `--server-port 2048`
- **GUI 启动器**: 图形界面直接配置

---

## API 认证

### 密钥配置

项目使用 `auth_profiles/key.txt` 管理 API 密钥：

```
your-api-key-1
your-api-key-2
# 注释行会被忽略
```

**验证逻辑**:
- 文件为空或不存在时，不需要认证
- 配置了密钥时，所有 `/v1/*` 请求需要有效密钥（除 `/v1/models`）

### 认证方式

```bash
# Bearer Token (推荐)
Authorization: Bearer your-api-key

# X-API-Key (备用)
X-API-Key: your-api-key
```

---

## API 端点

### 聊天接口

**端点**: `POST /v1/chat/completions`

与 OpenAI API 完全兼容，支持流式和非流式响应。

#### 支持的参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `messages` | Array | 聊天消息数组 (必需) |
| `model` | String | 模型 ID |
| `stream` | Boolean | 是否流式输出 |
| `temperature` | Number | 温度参数 (0.0-2.0) |
| `max_output_tokens` | Number | 最大输出 token 数 |
| `top_p` | Number | Top-P 采样 (0.0-1.0) |
| `stop` | Array/String | 停止序列 |
| `reasoning_effort` | String/Number | 思考模式控制 |
| `tools` | Array | 工具定义 (支持 google_search) |

#### reasoning_effort 参数详解

| 值 | 效果 |
|----|------|
| `0` 或 `"0"` | 关闭思考模式 |
| 数值 (如 `8000`) | 开启思考，限制预算 |
| `"none"` 或 `-1` | 开启思考，不限制预算 |
| `"low"` / `"high"` | 思考等级 (部分模型) |

#### 示例请求

```bash
# 非流式
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-pro-preview",
    "messages": [{"role": "user", "content": "Hello"}],
    "temperature": 0.7
  }'

# 流式
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-pro-preview",
    "messages": [{"role": "user", "content": "讲个故事"}],
    "stream": true
  }' --no-buffer
```

---

### 模型列表

**端点**: `GET /v1/models`

返回 AI Studio 可用模型列表。

**特点**:
- 动态获取 AI Studio 页面模型
- 支持 `excluded_models.txt` 排除特定模型
- 脚本注入模型标记 `"injected": true`

---

### 健康检查

**端点**: `GET /health`

返回服务状态：
- Playwright 状态
- 浏览器连接状态
- 页面状态
- 队列长度

---

### 其他端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/info` | GET | API 配置信息 |
| `/v1/queue` | GET | 队列状态 |
| `/v1/cancel/{req_id}` | POST | 取消请求 |
| `/ws/logs` | WebSocket | 实时日志流 |
| `/api/keys` | GET/POST/DELETE | 密钥管理 |

---

## 客户端配置

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:2048/v1",
    api_key="your-api-key"  # 或任意值
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

1. 进入 "设置" → "连接"
2. 添加模型
3. **API 基础 URL**: `http://127.0.0.1:2048/v1`
4. **API 密钥**: 留空或任意值
5. 保存设置

---

## 重要说明

### 三层响应获取机制

1. **集成流式代理** (默认，端口 3120): 最佳性能
2. **外部 Helper 服务** (可选): 备用方案
3. **Playwright 页面交互** (后备): 完整参数支持

> 详见 [流式处理模式详解](streaming-modes.md)

### 注意事项

- **串行处理**: 单浏览器实例，请求排队处理
- **客户端管理历史**: 客户端负责维护聊天记录
- **模型切换延迟**: 首次切换需要 2-5 秒

---

## 相关文档

- [OpenAI 兼容性说明](openai-compatibility.md) - 与 OpenAI API 的差异
- [环境变量完整参考](env-variables-reference.md) - 配置参数
- [客户端集成示例](client-examples.md) - 更多代码示例
- [故障排除指南](troubleshooting.md) - 问题解决
