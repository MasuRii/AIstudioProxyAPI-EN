# AI Studio Proxy Server (Javascript Version - DEPRECATED)

**⚠️ WARNING: This Javascript version is DEPRECATED and UNMAINTAINED. Please use the Python version in the project root, which is more stable and actively developed.**

**⚠️ 警告：此 Javascript 版本 (`server.cjs`, `auto_connect_aistudio.cjs`) 已被弃用且不再维护。推荐使用项目根目录下的 Python 版本，该版本采用了模块化架构设计，具有更好的稳定性和可维护性。**

**📖 View Latest Documentation**: Please refer to the [`README.md`](../README.md) in the project root for the current Python version.

**📖 查看最新文档**: 请参考项目根目录下的 [`README.md`](../README.md) 了解当前Python版本的完整使用说明。

---

这是一个 Node.js + Playwright 服务器，通过模拟 OpenAI API 的方式来访问 Google AI Studio 网页版，服务器无缝交互转发 Gemini 对话。这使得兼容 OpenAI API 的客户端（如 Open WebUI, NextChat 等）可以使用 AI Studio 的无限额度及能力。

## ✨ 特性 (Javascript 版本)

- **OpenAI API 兼容**: 提供 `/v1/chat/completions` 和 `/v1/models` 端点，兼容大多数 OpenAI 客户端。
- **流式响应**: 支持 `stream=true`，实现打字机效果。
- **非流式响应**: 支持 `stream=false`，一次性返回完整 JSON 响应。
- **系统提示词 (System Prompt)**: 支持通过请求体中的 `messages` 数组的 `system` 角色或额外的 `system_prompt` 字段传递系统提示词。
- **内部 Prompt 优化**: 自动包装用户输入，指导 AI Studio 输出特定格式（流式为 Markdown 代码块，非流式为 JSON），并包含起始标记 `<<<START_RESPONSE>>>` 以便解析。
- **自动连接脚本 (`auto_connect_aistudio.cjs`)**:
  - 自动查找并启动 Chrome/Chromium 浏览器，开启调试端口，**并设置特定窗口宽度 (460px)** 以优化布局，确保"清空聊天"按钮可见。
  - 自动检测并尝试连接已存在的 Chrome 调试实例。
  - 提供交互式选项，允许用户选择连接现有实例或自动结束冲突进程。
  - 自动查找或打开 AI Studio 的 `New chat` 页面。
  - 自动启动 `server.cjs`。
- **服务端 (`server.cjs`)**:
  - 连接到由 `auto_connect_aistudio.cjs` 管理的 Chrome 实例。
  - **自动清空上下文**: 当检测到来自客户端的请求可能是"新对话"时（基于消息历史长度），自动模拟点击 AI Studio 页面上的"Clear chat"按钮及其确认对话框，并验证清空效果，以实现更好的会话隔离。
  - 处理 API 请求，通过 Playwright 操作 AI Studio 页面。
  - 解析 AI Studio 的响应，提取有效内容。
  - 提供简单的 Web UI (`/`) 进行基本测试。
  - 提供健康检查端点 (`/health`)。
- **错误快照**: 在 Playwright 操作、响应解析或**清空聊天**出错时，自动在项目根目录下的 `errors/` 目录下保存页面截图和 HTML，方便调试。(注意: Python 版本错误快照在 `errors_py/`)
- **依赖检测**: 两个脚本在启动时都会检查所需依赖，并提供安装指导。
- **跨平台设计**: 旨在支持 macOS, Linux 和 Windows (WSL 推荐)。

## ⚠️ 重要提示 (Javascript 版本)

- **非官方项目**: 本项目与 Google 无关，依赖于对 AI Studio Web 界面的自动化操作，可能因 AI Studio 页面更新而失效。
- **自动清空功能的脆弱性**: 自动清空上下文的功能依赖于精确的 UI 元素选择器 (`CLEAR_CHAT_BUTTON_SELECTOR`, `CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR` 在 `server.cjs` 中)。如果 AI Studio 页面结构发生变化，此功能可能会失效。届时需要更新这些选择器。
- **不支持历史编辑/分叉**: 即使实现了新对话的上下文清空，本代理仍然无法支持客户端进行历史消息编辑并从该点重新生成对话的功能。AI Studio 内部维护的对话历史是线性的。
- **固定窗口宽度**: `auto_connect_aistudio.cjs` 会以固定的宽度 (460px) 启动 Chrome 窗口，以确保清空按钮可见。
- **安全性**: 启动 Chrome 时开启了远程调试端口 (默认为 `8848`)，请确保此端口仅在受信任的网络环境中使用，或通过防火墙规则限制访问。切勿将此端口暴露到公网。
- **稳定性**: 由于依赖浏览器自动化，其稳定性不如官方 API。长时间运行或频繁请求可能导致页面无响应或连接中断，可能需要重启浏览器或服务器。
- **AI Studio 限制**: AI Studio 本身可能有请求频率限制、内容策略限制等，代理服务器无法绕过这些限制。
- **参数配置**: **像模型选择、温度、输出长度等参数，需要您直接在 AI Studio 页面的右侧设置面板中进行调整。本代理服务器目前不处理或转发这些通过 API 请求传递的参数。** 您需要预先在 AI Studio Web UI 中设置好所需的模型和参数。

## 🛠️ 配置 (Javascript 版本)

虽然不建议频繁修改，但了解以下常量可能有助于理解脚本行为或在特殊情况下进行调整：

**`auto_connect_aistudio.cjs`:**

- `DEBUGGING_PORT`: (默认 `8848`) Chrome 浏览器启动时使用的远程调试端口。
- `TARGET_URL`: (默认 `'https://aistudio.google.com/prompts/new_chat'`) 脚本尝试打开或导航到的 AI Studio 页面。
- `SERVER_SCRIPT_FILENAME`: (默认 `'server.cjs'`) 由此脚本自动启动的 API 服务器文件名。
- `CONNECT_TIMEOUT_MS`: (默认 `20000`) 连接到 Chrome 调试端口的超时时间 (毫秒)。
- `NAVIGATION_TIMEOUT_MS`: (默认 `35000`) Playwright 等待页面导航完成的超时时间 (毫秒)。
- `--window-size=460,...`: 启动 Chrome 时传递的参数，固定宽度以保证 UI 元素（如清空按钮）位置相对稳定。

**`server.cjs`:**

- `SERVER_PORT`: (默认 `2048`) API 服务器监听的端口。
- `AI_STUDIO_URL_PATTERN`: (默认 `'aistudio.google.com/'`) 用于识别 AI Studio 页面的 URL 片段。
- `RESPONSE_COMPLETION_TIMEOUT`: (默认 `300000`) 等待 AI Studio 响应完成的总超时时间 (毫秒，5分钟)。
- `POLLING_INTERVAL`: (默认 `300`) 轮询检查 AI Studio 页面状态的间隔 (毫秒)。
- `SILENCE_TIMEOUT_MS`: (默认 `3000`) 判断 AI Studio 是否停止输出的静默超时时间 (毫秒)。
- `CLEAR_CHAT_VERIFY_TIMEOUT_MS`: (默认 `5000`) 等待并验证清空聊天操作完成的超时时间 (毫秒)。
- **CSS 选择器**: (`INPUT_SELECTOR`, `SUBMIT_BUTTON_SELECTOR`, `RESPONSE_CONTAINER_SELECTOR`, `LOADING_SPINNER_SELECTOR`, `ERROR_TOAST_SELECTOR`, `CLEAR_CHAT_BUTTON_SELECTOR`, `CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR`) 这些常量定义了脚本用于查找页面元素的选择器。**修改这些值需要具备前端知识，并且如果 AI Studio 页面更新，这些是最可能需要调整的部分。**

## ⚙️ Prompt 内部处理 (Javascript 版本)

为了让代理能够解析 AI Studio 的输出，`server.cjs` 会在将你的 Prompt 发送到 AI Studio 前进行包装，加入特定的指令，要求 AI：

1.  **对于非流式请求 (`stream=false`)**: 将整个回复包裹在一个 JSON 对象中，格式为 `{"response": "<<<START_RESPONSE>>>[AI的实际回复]"}`。
2.  **对于流式请求 (`stream=true`)**: 将整个回复（包括开始和结束）包裹在一个 Markdown 代码块 (```) 中，并在实际回复前加上标记 `<<<START_RESPONSE>>>`，形如：
    ```markdown

    ```
    <<<START_RESPONSE>>>[AI的实际回复第一部分]
    [AI的实际回复第二部分]
    ...
    ```

    ```

`server.cjs` 会查找 `<<<START_RESPONSE>>>` 标记来提取真正的回复内容。这意味着你通过 API 得到的回复是经过这个内部处理流程的，AI Studio 页面的原始输出格式会被改变。

## 🚀 开始使用 (Javascript 版本)

### 1. 先决条件

- **Node.js**: v16 或更高版本。
- **NPM / Yarn / PNPM**: 用于安装依赖。
- **Google Chrome / Chromium**: 需要安装浏览器本体。
- **Google AI Studio 账号**: 并能正常访问和使用。

### 2. 安装

1.  **进入弃用版本目录**:

    ```bash
    cd deprecated_javascript_version
    ```

2.  **安装依赖**:
    根据 `package.json` 文件，脚本运行需要以下核心依赖：
    - `express`: Web 框架，用于构建 API 服务器。
    - `cors`: 处理跨域资源共享。
    - `playwright`: 浏览器自动化库。
    - `@playwright/test`: Playwright 的测试库，`server.cjs` 使用其 `expect` 功能进行断言。

    使用你的包管理器安装：

    ```bash
    npm install
    # 或
    yarn install
    # 或
    pnpm install
    ```

### 3. 运行

只需要运行 `auto_connect_aistudio.cjs` 脚本即可启动所有服务：

```bash
node auto_connect_aistudio.cjs
```

这个脚本会执行以下操作：

1.  **检查依赖**: 确认上述 Node.js 模块已安装，且 `server.cjs` 文件存在。
2.  **检查 Chrome 调试端口 (`8848`)**:
    - 如果端口空闲，尝试自动查找并启动一个新的 Chrome 实例（窗口宽度固定为 460px），并打开远程调试端口。
    - 如果端口被占用，询问用户是连接现有实例还是尝试清理端口后启动新实例。
3.  **连接 Playwright**: 尝试连接到 Chrome 的调试端口 (`http://127.0.0.1:8848`)。
4.  **管理 AI Studio 页面**: 查找或打开 AI Studio 的 `New chat` 页面 (`https://aistudio.google.com/prompts/new_chat`)，并尝试置于前台。
5.  **启动 API 服务器**: 如果以上步骤成功，脚本会自动在后台启动 `node server.cjs`。

当 `server.cjs` 成功启动并连接到 Playwright 后，您将在终端看到类似以下的输出（来自 `server.cjs`）：

```
=============================================================
          🚀 AI Studio Proxy Server (Legacy - Queue & Auto Clear) 🚀
=============================================================
🔗 监听地址: http://localhost:2048
   - Web UI (测试): http://localhost:2048/
   - API 端点:   http://localhost:2048/v1/chat/completions
   - 模型接口:   http://localhost:2048/v1/models
   - 健康检查:   http://localhost:2048/health
-------------------------------------------------------------
✅ Playwright 连接成功，服务已准备就绪！
-------------------------------------------------------------
```

_(版本号可能不同)_

此时，代理服务已准备就绪，监听在 `http://localhost:2048`。

### 4. 配置客户端 (以 Open WebUI 为例)

1.  打开 Open WebUI。
2.  进入 "设置" -> "连接"。
3.  在 "模型" 部分，点击 "添加模型"。
4.  **模型名称**: 输入你想要的名字，例如 `aistudio-gemini-cjs`。
5.  **API 基础 URL**: 输入代理服务器的地址，例如 `http://localhost:2048/v1` (注意包含 `/v1`)。
6.  **API 密钥**: 留空或输入任意字符 (服务器不验证)。
7.  保存设置。
8.  现在，你应该可以在 Open WebUI 中选择 `aistudio-gemini-cjs` 模型并开始聊天了。

### 5. 使用测试脚本 (可选)

本目录下提供了一个 `test.js` 脚本，用于在命令行中直接与代理进行交互式聊天。

1.  **安装额外依赖**: `test.js` 使用了 OpenAI 的官方 Node.js SDK。
    ```bash
    npm install openai
    # 或 yarn add openai / pnpm add openai
    ```
2.  **检查配置**: 打开 `test.js`，确认 `LOCAL_PROXY_URL` 指向你的代理服务器地址 (`http://127.0.0.1:2048/v1/`)。`DUMMY_API_KEY` 可以保持不变。
3.  **运行测试**: 在 `deprecated_javascript_version` 目录下运行：
    ```bash
    node test.js
    ```
    之后就可以在命令行输入问题进行测试了。输入 `exit` 退出。

## 💻 多平台指南 (Javascript 版本)

- **macOS**:
  - `auto_connect_aistudio.cjs` 通常能自动找到 Chrome。
  - 防火墙可能会提示是否允许 Node.js 接受网络连接，请允许。
- **Linux**:
  - 确保已安装 `google-chrome-stable` 或 `chromium-browser`。
  - 如果脚本找不到 Chrome，你可能需要修改 `auto_connect_aistudio.cjs` 中的 `getChromePath` 函数，手动指定路径，或者创建一个符号链接 (`/usr/bin/google-chrome`) 指向实际的 Chrome 可执行文件。
  - 某些 Linux 发行版可能需要安装额外的 Playwright 依赖库，参考 [Playwright Linux 文档](https://playwright.dev/docs/intro#system-requirements)。运行 `npx playwright install-deps` 可能有助于安装。
- **Windows**:
  - **强烈建议使用 WSL (Windows Subsystem for Linux)**。在 WSL 中按照 Linux 指南操作通常更顺畅。
  - **直接在 Windows 上运行 (不推荐)**:
    - `auto_connect_aistudio.cjs` 可能需要手动修改 `getChromePath` 函数来指定 Chrome 的完整路径 (例如 `C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe`)。注意路径中的反斜杠需要转义 (`\\`)。
    - 防火墙设置需要允许 Node.js 和 Chrome 监听和连接端口 (`8848` 和 `2048`)。
    - 由于文件系统和权限差异，可能会遇到未知问题，例如端口检查或进程结束操作 (`taskkill`) 失败。

## 🔧 故障排除 (Javascript 版本)

- **`auto_connect_aistudio.cjs` 启动失败或报错**:
  - **依赖未找到**: 确认运行了 `npm install` 等命令。
  - **Chrome 路径找不到**: 确认 Chrome/Chromium 已安装，并按需修改 `getChromePath` 函数或创建符号链接 (Linux)。
  - **端口 (`8848`) 被占用且无法自动清理**: 根据脚本提示，使用系统工具（如 `lsof -i :8848` / `tasklist | findstr "8848"`）手动查找并结束占用端口的进程。
  - **连接 Playwright 超时**: 确认 Chrome 是否已成功启动并监听 `8848` 端口，防火墙是否阻止本地连接 `127.0.0.1:8848`。查看 `auto_connect_aistudio.cjs` 中的 `CONNECT_TIMEOUT_MS` 是否足够。
  - **打开/导航 AI Studio 页面失败**: 检查网络连接，尝试手动在浏览器中打开 `https://aistudio.google.com/prompts/new_chat` 并完成登录。查看 `NAVIGATION_TIMEOUT_MS` 是否足够。
  - **窗口大小问题**: 如果 460px 宽度导致问题，可以尝试修改 `auto_connect_aistudio.cjs` 中的 `--window-size` 参数，但这可能影响自动清空功能。
- **`server.cjs` 启动时提示端口被占用 (`EADDRINUSE`)**:
  - 检查是否有其他程序 (包括旧的服务器实例) 正在使用 `2048` 端口。关闭冲突程序或修改 `server.cjs` 中的 `SERVER_PORT`。
- **服务器日志显示 Playwright 未就绪或连接失败 (在 `server.cjs` 启动后)**:
  - 通常意味着 `auto_connect_aistudio.cjs` 启动的 Chrome 实例意外关闭或无响应。检查 Chrome 窗口是否还在，AI Studio 页面是否崩溃。
  - 尝试关闭所有相关进程（`node` 和 `chrome`），然后重新运行 `node auto_connect_aistudio.cjs`。
  - 检查根目录下的 `errors/` 目录是否有截图和 HTML 文件，它们可能包含 AI Studio 页面的错误信息或状态。
- **客户端 (如 Open WebUI) 无法连接或请求失败**:
  - 确认 API 基础 URL 配置正确 (`http://localhost:2048/v1`)。
  - 检查 `server.cjs` 运行的终端是否有错误输出。
  - 确保客户端和服务器在同一网络中，且防火墙没有阻止从客户端到服务器 `2048` 端口的连接。
- **API 请求返回 5xx 错误**:
  - **503 Service Unavailable / Playwright not ready**: `server.cjs` 无法连接到 Chrome。
  - **504 Gateway Timeout**: 请求处理时间超过了 `RESPONSE_COMPLETION_TIMEOUT`。可能是 AI Studio 响应慢或卡住了。
  - **502 Bad Gateway / AI Studio Error**: `server.cjs` 在 AI Studio 页面上检测到了错误提示 (`toast` 消息)，或无法正确解析 AI 的响应。检查 `errors/` 快照。
  - **500 Internal Server Error**: `server.cjs` 内部发生未捕获的错误。检查服务器日志和 `errors/` 快照。
- **AI 回复不完整、格式错误或包含 `<<<START_RESPONSE>>>` 标记**:
  - AI Studio 的 Web UI 输出不稳定。服务器尽力解析，但可能失败。
  - 非流式请求：如果返回的 JSON 中缺少 `response` 字段或无法解析，服务器可能返回空内容或原始 JSON 字符串。检查 `errors/` 快照确认 AI Studio 页面的实际输出。
  - 流式请求：如果 AI 未按预期输出 Markdown 代码块或起始标记，流式传输可能提前中断或包含非预期内容。
  - 尝试调整 Prompt 或稍后重试。
- **自动清空上下文失败**:
  - 服务器日志出现 "清空聊天记录或验证时出错" 或 "验证超时" 的警告。
  - **原因**: AI Studio 网页更新导致 `server.cjs` 中的 `CLEAR_CHAT_BUTTON_SELECTOR` 或 `CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR` 失效。
  - **解决**: 检查 `errors/` 快照，使用浏览器开发者工具检查实际页面元素，并更新 `server.cjs` 文件顶部的选择器常量。
  - **原因**: 清空操作本身耗时超过了 `CLEAR_CHAT_VERIFY_TIMEOUT_MS`。
  - **解决**: 如果网络或机器较慢，可以尝试在 `server.cjs` 中适当增加这个超时时间。
