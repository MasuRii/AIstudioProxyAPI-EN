# Project Architecture Guide

This document details the modular architecture design, component responsibilities, and interactions of the AI Studio Proxy API project.

## 🏗️ Architecture Overview

### Core Design Principles

- **Modular Separation**: Divide modules by functional area to avoid circular dependencies
- **Single Responsibility**: Each module focuses on specific functions
- **Unified Configuration**: `.env` file and `config/` module manage configuration uniformly
- **Async First**: Adopt asynchronous programming patterns comprehensively

---

## 📁 Module Structure

```
AIstudioProxyAPI/
├── api_utils/                  # FastAPI application core module
│   ├── app.py                 # Application entry and lifecycle management
│   ├── routers/               # API routers (split by responsibility)
│   │   ├── api_keys.py        # /api/keys* Key management
│   │   ├── auth_files.py      # /api/auth-files* Auth file management
│   │   ├── chat.py            # /v1/chat/completions
│   │   ├── health.py          # /health Health check
│   │   ├── helper.py          # /api/helper* Helper service config
│   │   ├── info.py            # /api/info Info endpoint
│   │   ├── logs_ws.py         # /ws/logs WebSocket logs
│   │   ├── model_capabilities.py  # /api/model-capabilities
│   │   ├── models.py          # /v1/models Model list
│   │   ├── ports.py           # /api/ports* Port config
│   │   ├── proxy.py           # /api/proxy* Proxy config
│   │   ├── queue.py           # /v1/queue, /v1/cancel
│   │   ├── server.py          # /api/server* Server control
│   │   └── static.py          # /, /assets/* React SPA
│   ├── request_processor.py   # Request processing core logic
│   ├── queue_worker.py        # Async queue worker
│   ├── response_generators.py # SSE response generator
│   ├── auth_utils.py          # Auth tools
│   ├── auth_manager.py        # Auth manager
│   ├── dependencies.py        # FastAPI dependency injection
│   ├── client_connection.py   # Client connection management
│   ├── server_state.py        # Server state management
│   ├── model_switching.py     # Model switching logic
│   ├── mcp_adapter.py         # MCP protocol adapter
│   ├── sse.py                 # SSE streaming response handling
│   ├── utils.py               # Common utility functions
│   └── utils_ext/             # Extended utility modules
│       ├── files.py           # File/Attachment handling
│       ├── helper.py          # Helper service tools
│       ├── prompts.py         # Prompt handling
│       ├── stream.py          # Stream handling tools
│       ├── string_utils.py    # String tools
│       ├── tokens.py          # Token calculation
│       ├── tools_execution.py # Tool execution
│       └── validation.py      # Request validation
│
├── browser_utils/              # Browser automation module
│   ├── page_controller.py     # Page controller (Aggregate entry)
│   ├── page_controller_modules/  # Controller submodules (Mixin)
│   │   ├── base.py            # Base controller
│   │   ├── chat.py            # Chat history management
│   │   ├── input.py           # Input control
│   │   ├── parameters.py      # Parameter control
│   │   ├── response.py        # Response acquisition
│   │   └── thinking.py        # Thinking process control
│   ├── initialization/        # Initialization module
│   │   ├── core.py            # Browser context creation, navigation
│   │   ├── network.py         # Network interception config
│   │   ├── auth.py            # Auth state save/restore
│   │   ├── scripts.py         # UserScript injection
│   │   └── debug.py           # Debug listener
│   ├── operations_modules/    # Operation submodules
│   │   ├── parsers.py         # Data parsing
│   │   ├── interactions.py    # Page interactions
│   │   └── errors.py          # Error handling
│   ├── model_management.py    # Model management
│   ├── operations.py          # Operation aggregate entry
│   ├── debug_utils.py         # Debug tools
│   ├── thinking_normalizer.py # Thinking process normalization
│   └── more_models.js         # Tampermonkey script template
│
├── config/                     # Configuration management module
│   ├── settings.py            # Main settings and environment variables
│   ├── constants.py           # System constant definitions
│   ├── timeouts.py            # Timeout configurations
│   ├── selectors.py           # CSS selector definitions
│   ├── selector_utils.py      # Selector utility functions
│   └── model_capabilities.json # Model capability configuration
│
├── models/                     # Data model definitions
│   ├── chat.py                # Chat related models
│   ├── exceptions.py          # Custom exception classes
│   └── logging.py             # Log related models
│
├── stream/                     # Streaming proxy service module
│   ├── main.py                # Proxy service entry
│   ├── proxy_server.py        # Proxy server implementation
│   ├── proxy_connector.py     # Proxy connector
│   ├── cert_manager.py        # Certificate management
│   ├── interceptors.py        # Request interceptors
│   └── utils.py               # Stream handling tools
│
├── launcher/                   # Launcher module
│   ├── runner.py              # Launch logic core
│   ├── config.py              # Launch config processing
│   ├── checks.py              # Environment and dependency checks
│   ├── process.py             # Camoufox process management
│   ├── frontend_build.py      # Frontend build check
│   ├── internal.py            # Internal tools
│   ├── logging_setup.py       # Log configuration
│   └── utils.py               # Launcher tools
│
├── logging_utils/              # Log management module
│   ├── setup.py               # Log system configuration
│   └── grid_logger.py         # Grid logger
│
├── server.py                   # Application entry point
├── launch_camoufox.py          # Command line launcher (Main entry)
├── deprecated/                 # Deprecated modules
│   └── gui_launcher.py         # [Deprecated] GUI Launcher
└── pyproject.toml              # Poetry configuration
```

---

## 🔧 Core Modules Details

### 1. api_utils/ - FastAPI Application Core

**Responsibility**: API routing, authentication, request processing.

#### app.py - Application Entry

- FastAPI application creation and configuration
- Lifecycle management (startup/shutdown)
- Middleware configuration (API key authentication)

#### routers/ - API Routes

Routes are split into independent modules by responsibility:

| Module | Endpoint | Responsibility |
| ----------------------- | ------------------------- | ------------------ |
| `chat.py` | `/v1/chat/completions` | Chat completion interface |
| `models.py` | `/v1/models` | Model list |
| `model_capabilities.py` | `/api/model-capabilities` | Model capability query |
| `health.py` | `/health` | Health check |
| `queue.py` | `/v1/queue`, `/v1/cancel` | Queue management |
| `api_keys.py` | `/api/keys*` | Key management |
| `logs_ws.py` | `/ws/logs` | Real-time log stream |
| `static.py` | `/`, `/assets/*` | React SPA static resources |
| `info.py` | `/api/info` | API information |
| `auth_files.py` | `/api/auth-files*` | Auth file management |
| `ports.py` | `/api/ports*` | Port config and process management |
| `proxy.py` | `/api/proxy*` | Proxy config management |
| `server.py` | `/api/server*` | Server control |
| `helper.py` | `/api/helper*` | Helper service config |

#### queue_worker.py - Queue Worker

- Asynchronous request queue processing (FIFO)
- Concurrency control and resource management
- **Tiered Error Recovery Mechanism**:
  - **Tier 1**: Page quick refresh (Handle temporary DOM errors)
  - **Tier 2**: Auth profile switching (Handle quota exhaustion)

### 2. browser_utils/ - Browser Automation

**Responsibility**: Browser control, page interaction, script injection.

#### page_controller.py - Page Controller

Aggregate controller based on Mixin pattern, inheriting from `page_controller_modules/` submodules.

#### initialization/ - Initialization Module

| Module | Responsibility |
| ------------ | -------------------------------- |
| `core.py` | Browser context creation, navigation, login detection |
| `network.py` | Network interception, model list injection |
| `auth.py` | Auth state save/restore |
| `scripts.py` | UserScript script injection |
| `debug.py` | Debug listener settings |

#### Script Injection Mechanism

Script injection is implemented via `initialization/network.py`:

- Playwright native route interception `/api/models`
- Parse model data from Tampermonkey script (`more_models.js`)
- Model data automatically synced to page

### 3. stream/ - Streaming Proxy Service

**Responsibility**: High-performance streaming response proxy.

- **proxy_server.py**: HTTP/HTTPS proxy implementation
- **interceptors.py**: AI Studio request interception and response parsing
- **cert_manager.py**: Self-signed certificate management

### 4. launcher/ - Launcher Module

**Responsibility**: Application startup and process management.

| Module | Responsibility |
| ------------ | ----------------- |
| `runner.py` | Launch logic core |
| `config.py` | Launch config processing |
| `checks.py` | Environment and dependency checks |
| `process.py` | Camoufox process management |

---

## 🔄 Response Acquisition Mechanism

The project implements a three-layer response acquisition mechanism to ensure high availability:

```
Request → Layer 1: Streaming Proxy → Layer 2: Helper → Layer 3: Playwright
```

| Layer | Type | Latency | Parameter Support | Applicable Scenario |
| -------------- | ---------------- | ---- | ---------- | --------------- |
| **Streaming Proxy** | True Streaming | Lowest | Basic | Production (Recommended) |
| **Helper** | Implementation Dependent | Medium | Implementation Dependent | Special Network Environment |
| **Playwright** | Pseudo-Streaming | Highest | All | Debugging, Parameter Testing |

### Request Processing Path

**Auxiliary Stream Path (STREAM)**:

- Entry: `_handle_auxiliary_stream_response`
- Consume from `STREAM_QUEUE`, produce OpenAI compatible SSE

**Playwright Path**:

- Entry: `_handle_playwright_response`
- Pull text via `PageController.get_response`, output by chunk

---

## 🔐 Authentication System

### API Key Management

- **Storage**: `auth_profiles/key.txt`
- **Validation**: Bearer Token and X-API-Key dual support
- **Management**: Web UI tiered permission view

### Browser Authentication

- **File**: `auth_profiles/active/*.json`
- **Content**: Browser session and Cookies
- **Update**: Re-acquire via `--debug` mode

---

## 📊 Configuration Management

### Priority

1. **Command Line Arguments** (Highest)
2. **Environment Variables** (`.env` file)
3. **Default Values** (Code defined)

### config/ Module

| File | Responsibility |
| ------------------------- | ---------------------------------------------- |
| `settings.py` | Environment variable loading and parsing |
| `constants.py` | System constant definitions |
| `timeouts.py` | Timeout configurations |
| `selectors.py` | CSS selector definitions |
| `selector_utils.py` | Selector utility functions |
| `model_capabilities.json` | Model capability configuration (Thinking type, Google Search support, etc.) |

> **Note**: `model_capabilities.json` is an externalized JSON configuration file defining capability parameters for each model.
> When Google releases new models, just edit the JSON file, no code changes needed.

---

## 🚀 Script Injection v3.0

### Workflow

1. **Script Parsing**: Parse `MODELS_TO_INJECT` array from Tampermonkey script
2. **Network Interception**: Playwright intercepts `/api/models` request
3. **Data Merge**: Injected models add `__NETWORK_INJECTED__` marker
4. **Script Injection**: Script injected into page context

### Technical Advantages

- ✅ **100% Reliable**: Playwright native interception, no timing issues
- ✅ **Zero Maintenance**: Script updates automatically take effect
- ✅ **Fully Synced**: Frontend and backend use same data source

---

## 📈 Development Tools

| Tool | Usage |
| ----------- | ----------------- |
| **Poetry** | Dependency management |
| **Pyright** | Type checking |
| **Ruff** | Code formatting and Lint |
| **pytest** | Testing framework |

---

## Related Documentation

- [Developer Guide](development-guide.md) - Poetry, Pyright workflow
- [Streaming Modes Explained](streaming-modes.md) - Three-layer response mechanism details
- [Script Injection Guide](script_injection_guide.md) - Tampermonkey script features
