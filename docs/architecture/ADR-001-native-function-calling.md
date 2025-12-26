# ADR-001: Native Function Calling Architecture

**Date:** 2025-01-23
**Status:** Implemented
**Decision Makers:** Core Team
**Supersedes:** None (New Feature)

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Context & Problem Statement](#2-context--problem-statement)
3. [Decision Drivers](#3-decision-drivers)
4. [Considered Options](#4-considered-options)
5. [Decision Outcome](#5-decision-outcome)
6. [Architecture Design](#6-architecture-design)
7. [Component Specifications](#7-component-specifications)
8. [Data Flow](#8-data-flow)
9. [Configuration Schema](#9-configuration-schema)
10. [API Compatibility Layer](#10-api-compatibility-layer)
11. [Browser Automation Strategy](#11-browser-automation-strategy)
12. [Error Handling](#12-error-handling)
13. [Implementation Roadmap](#13-implementation-roadmap)
14. [Risks & Mitigations](#14-risks--mitigations)

---

## 1. Executive Summary

This ADR defines the architecture for implementing **native function calling** support in AIstudioProxyAPI. Native function calling leverages AI Studio's built-in function/tool UI rather than the current text-based emulation approach.

**Key Outcomes:**
- Full OpenAI API compatibility (`tools` array, `tool_calls` response)
- Dual-mode operation: "emulated" (current) vs "native" (new)
- Both streaming and non-streaming support
- Graceful fallback to emulated mode on UI automation failures

---

## 2. Context & Problem Statement

### Current State
The proxy currently implements function calling via **text-based emulation**:
1. Tool definitions are injected into the system prompt as `Available Tools Catalog:` text
2. The model outputs structured text like `Request function call: {name}`
3. The proxy parses this text and may execute tools server-side

### Limitations
| Issue | Impact |
|-------|--------|
| Model may ignore/misformat tool calls | Unreliable function detection |
| Text parsing is fragile | Edge cases cause failures |
| No structured arguments validation | Invalid JSON in arguments |
| Token overhead | Tool catalog consumes context tokens |
| Not utilizing AI Studio's native capabilities | Suboptimal model behavior |

### Opportunity
AI Studio provides a native function calling UI:
- **Toggle switch** (`data-test-id="functionCallingTooltip"`) to enable function mode
- **Edit button** that opens a modal with JSON textarea for function declarations
- **Structured responses** with distinct UI elements for function calls

---

## 3. Decision Drivers

1. **OpenAI API Compatibility**: Clients expect standard `tools`/`tool_calls` format
2. **Reliability**: Native structured output is more reliable than text parsing
3. **Backward Compatibility**: Existing "emulated" mode must continue to work
4. **Configurability**: Users should choose their preferred mode
5. **Maintainability**: Clean separation of concerns for future updates
6. **Resilience**: Graceful degradation on UI automation failures

---

## 4. Considered Options

### Option A: Native Mode Only (Rejected)
- **Pros:** Simpler implementation
- **Cons:** Breaks backward compatibility, no fallback

### Option B: Emulated Mode Only (Status Quo)
- **Pros:** Already working
- **Cons:** Limitations described above persist

### Option C: Dual-Mode with Configuration (Selected)
- **Pros:** User choice, fallback capability, gradual migration
- **Cons:** More complex implementation

---

## 5. Decision Outcome

**Chosen Option: C - Dual-Mode with Configuration**

Users configure `FUNCTION_CALLING_MODE` to select:
- `emulated` (default): Current text-based approach
- `native`: AI Studio UI-driven function calling
- `auto`: Native with automatic fallback to emulated on failure

---

## 6. Architecture Design

### 6.1 High-Level Component Diagram

```
                    +------------------+
                    |   API Request    |
                    |  (OpenAI Format) |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    | Request Router   |
                    | (chat.py)        |
                    +--------+---------+
                             |
                             v
              +--------------+---------------+
              |      Function Calling        |
              |         Orchestrator         |
              |   (new: fc_orchestrator.py)  |
              +--------------+---------------+
                             |
            +----------------+----------------+
            |                                 |
            v                                 v
   +--------+--------+               +--------+--------+
   |   EMULATED      |               |     NATIVE      |
   |     Mode        |               |      Mode       |
   +--------+--------+               +--------+--------+
            |                                 |
            v                                 v
   +--------+--------+               +--------+--------+
   | Text Injection  |               | Schema Converter|
   | (prompts.py)    |               | (new)           |
   +--------+--------+               +--------+--------+
            |                                 |
            |                                 v
            |                        +--------+--------+
            |                        | UI Automation   |
            |                        | (new: functions)|
            |                        +--------+--------+
            |                                 |
            +----------------+----------------+
                             |
                             v
                    +------------------+
                    |  PageController  |
                    |  submit_prompt   |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    | Response Parser  |
                    | (new: fc_parser) |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    | Response         |
                    | Formatter        |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  API Response    |
                    | (OpenAI Format)  |
                    +------------------+
```

### 6.2 Module Organization

```
api_utils/
  utils_ext/
    function_calling/           # NEW PACKAGE
      __init__.py
      config.py                 # Mode configuration
      orchestrator.py           # Mode routing logic
      schema_converter.py       # OpenAI -> Gemini schema
      response_parser.py        # Parse function call responses
      response_formatter.py     # Format to OpenAI tool_calls
      id_manager.py             # Generate and track call IDs

browser_utils/
  page_controller_modules/
    functions.py                # NEW: UI automation for functions

config/
  selectors.py                  # ADD: Function UI selectors
  settings.py                   # ADD: FUNCTION_CALLING_MODE
```

---

## 7. Component Specifications

### 7.1 Configuration Module (`function_calling/config.py`)

```python
from enum import Enum
from typing import Literal

class FunctionCallingMode(str, Enum):
    EMULATED = "emulated"
    NATIVE = "native"
    AUTO = "auto"

@dataclass
class FunctionCallingConfig:
    mode: FunctionCallingMode
    native_retry_count: int = 2
    fallback_on_failure: bool = True
    clear_functions_between_requests: bool = True
```

**Environment Variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `FUNCTION_CALLING_MODE` | `emulated` | Mode selection |
| `FC_NATIVE_RETRY_COUNT` | `2` | UI automation retry attempts |
| `FC_FALLBACK_ON_FAILURE` | `true` | Auto-fallback to emulated |
| `FC_CLEAR_BETWEEN_REQUESTS` | `true` | Clear function definitions between requests |

---

### 7.2 Schema Converter (`function_calling/schema_converter.py`)

Converts OpenAI tool definitions to Gemini FunctionDeclaration format.

**Input (OpenAI):**
```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Get weather for a location",
    "parameters": {
      "type": "object",
      "properties": {
        "location": { "type": "string" }
      },
      "required": ["location"]
    },
    "strict": true
  }
}
```

**Output (Gemini FunctionDeclaration for UI):**
```json
{
  "name": "get_weather",
  "description": "Get weather for a location",
  "parameters": {
    "type": "object",
    "properties": {
      "location": { "type": "string" }
    },
    "required": ["location"]
  }
}
```

**Conversion Rules:**
| OpenAI Field | Gemini Field | Transformation |
|--------------|--------------|----------------|
| `function.name` | `name` | Direct copy |
| `function.description` | `description` | Direct copy (optional but recommended) |
| `function.parameters` | `parameters` | Direct copy (JSON Schema compatible) |
| `function.strict` | N/A | **Strip** - not supported in UI |
| `additionalProperties: false` | Keep | Gemini may honor this |

**Interface:**
```python
class SchemaConverter:
    def convert_tools(
        self, 
        openai_tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert OpenAI tools array to Gemini FunctionDeclaration array."""
        
    def to_json_string(
        self, 
        declarations: List[Dict[str, Any]]
    ) -> str:
        """Serialize for UI textarea paste."""
```

---

### 7.3 ID Manager (`function_calling/id_manager.py`)

Gemini does not return call IDs. The proxy must generate and track them.

**Interface:**
```python
class CallIdManager:
    def generate_id(self) -> str:
        """Generate unique call ID: call_<uuid4>"""
        return f"call_{uuid.uuid4().hex[:24]}"
    
    def register_call(
        self, 
        call_id: str, 
        function_name: str, 
        arguments: Dict[str, Any]
    ) -> None:
        """Track call for result correlation."""
        
    def get_pending_calls(self) -> List[PendingCall]:
        """Return calls awaiting results."""
```

**ID Format:** `call_<24-character-hex>`

Example: `call_a1b2c3d4e5f6g7h8i9j0k1l2`

---

### 7.4 Response Parser (`function_calling/response_parser.py`)

Extracts function calls from AI Studio's response.

**Detection Strategy (Priority Order):**
1. **DOM Element Detection**: Look for function call UI widgets
2. **Structured JSON in Response**: Parse `{"function_call": ...}` patterns
3. **Text Pattern Fallback**: Parse legacy `Request function call:` text

**Interface:**
```python
@dataclass
class ParsedFunctionCall:
    name: str
    arguments: Dict[str, Any]  # Parsed, not string
    raw_text: Optional[str] = None

class ResponseParser:
    async def parse_native_response(
        self, 
        page: Page,
        raw_text: str
    ) -> Tuple[Optional[str], List[ParsedFunctionCall]]:
        """
        Returns:
            - content: Text content (may be None if pure function call)
            - function_calls: List of detected function calls
        """
        
    def detect_function_call_elements(
        self, 
        page: Page
    ) -> List[Locator]:
        """Find function call UI elements in DOM."""
```

**DOM Selectors for Function Calls (to be validated):**
```python
# Proposed selectors - require browser inspection to confirm
FUNCTION_CALL_WIDGET_SELECTOR = 'ms-function-call, [data-test-id*="function-call"]'
FUNCTION_CALL_NAME_SELECTOR = '.function-name, [data-test-id="function-name"]'
FUNCTION_CALL_ARGS_SELECTOR = '.function-arguments, [data-test-id="function-args"]'
```

---

### 7.5 Response Formatter (`function_calling/response_formatter.py`)

Formats parsed function calls to OpenAI's `tool_calls` structure.

**Non-Streaming Output:**
```python
def format_tool_calls(
    self,
    parsed_calls: List[ParsedFunctionCall],
    id_manager: CallIdManager
) -> List[Dict[str, Any]]:
    """
    Returns:
    [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": "{\"location\": \"Boston\"}"  # STRING, not dict
            }
        }
    ]
    """
```

**Streaming Output (Deltas):**
```python
def format_tool_call_delta(
    self,
    index: int,
    call_id: Optional[str],  # Only on first chunk
    function_name: Optional[str],  # Only on first chunk
    arguments_fragment: str
) -> Dict[str, Any]:
    """
    Returns delta chunk for SSE streaming.
    """
```

**Critical Transformations:**
| Source (Gemini) | Target (OpenAI) | Action |
|-----------------|-----------------|--------|
| No ID | `id` | Generate via IdManager |
| `args: Dict` | `arguments: str` | `json.dumps(args)` |
| Single call | `tool_calls: List` | Wrap in array |

---

### 7.6 Browser Automation (`page_controller_modules/functions.py`)

New controller module for function UI interactions.

**Interface:**
```python
class FunctionController(BaseController):
    async def enable_function_calling(
        self,
        check_client_disconnected: Callable
    ) -> bool:
        """Toggle function calling on. Returns success status."""
        
    async def disable_function_calling(
        self,
        check_client_disconnected: Callable
    ) -> bool:
        """Toggle function calling off."""
        
    async def set_function_declarations(
        self,
        declarations_json: str,
        check_client_disconnected: Callable
    ) -> bool:
        """
        Open edit modal, paste JSON declarations, save.
        Returns success status.
        """
        
    async def clear_function_declarations(
        self,
        check_client_disconnected: Callable
    ) -> bool:
        """Remove all function declarations."""
        
    async def extract_function_call_response(
        self,
        check_client_disconnected: Callable
    ) -> List[ParsedFunctionCall]:
        """Parse function call widgets from response area."""
```

**Required Selectors (add to `config/selectors.py`):**
```python
# --- Function Calling Selectors ---
FUNCTION_CALLING_TOGGLE_SELECTOR = (
    'div[data-test-id="functionCallingTooltip"] mat-slide-toggle button, '
    'button[aria-label*="function calling" i]'
)

FUNCTION_EDIT_BUTTON_SELECTOR = (
    'button[aria-label="Edit functions"], '
    'button:has-text("Edit")'
)

FUNCTION_DECLARATIONS_TEXTAREA_SELECTOR = (
    'textarea[aria-label*="function" i], '
    'textarea.function-declarations, '
    '.function-editor textarea'
)

FUNCTION_SAVE_BUTTON_SELECTOR = (
    'button[aria-label="Save"], '
    'button:has-text("Save"), '
    'button:has-text("Done")'
)

FUNCTION_CALL_RESPONSE_SELECTOR = (
    'ms-function-call, '
    '[data-test-id*="function-call"], '
    '.function-call-widget'
)
```

---

### 7.7 Orchestrator (`function_calling/orchestrator.py`)

Central coordinator that routes between modes.

**Interface:**
```python
class FunctionCallingOrchestrator:
    def __init__(
        self,
        config: FunctionCallingConfig,
        schema_converter: SchemaConverter,
        id_manager: CallIdManager,
        response_parser: ResponseParser,
        response_formatter: ResponseFormatter
    ):
        pass
    
    async def prepare_request(
        self,
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Optional[Union[str, Dict[str, Any]]],
        page_controller: PageController,
        check_client_disconnected: Callable
    ) -> PreparedRequest:
        """
        Prepares request based on mode:
        - EMULATED: Returns modified prompt with tool catalog
        - NATIVE: Configures UI, returns clean prompt
        """
        
    async def process_response(
        self,
        raw_response: str,
        page: Page,
        streaming: bool
    ) -> ProcessedResponse:
        """
        Processes response:
        - Detects function calls
        - Formats to OpenAI structure
        - Determines finish_reason
        """
```

**PreparedRequest:**
```python
@dataclass
class PreparedRequest:
    prompt: str
    files: List[str]
    mode_used: FunctionCallingMode
    tools_configured: bool
```

**ProcessedResponse:**
```python
@dataclass
class ProcessedResponse:
    content: Optional[str]
    tool_calls: Optional[List[Dict[str, Any]]]
    finish_reason: str  # "stop" | "tool_calls"
    mode_used: FunctionCallingMode
```

---

## 8. Data Flow

### 8.1 Native Mode - Non-Streaming

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           REQUEST PHASE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. API receives request with `tools` array                              │
│                     │                                                    │
│                     v                                                    │
│  2. Orchestrator.prepare_request()                                       │
│        ├── mode=NATIVE                                                   │
│        ├── SchemaConverter.convert_tools()                               │
│        │        └── OpenAI tools -> Gemini declarations JSON             │
│        └── FunctionController.set_function_declarations()                │
│                 ├── Toggle ON function calling                           │
│                 ├── Click Edit                                           │
│                 ├── Clear textarea                                       │
│                 ├── Paste JSON declarations                              │
│                 └── Click Save                                           │
│                     │                                                    │
│                     v                                                    │
│  3. PageController.submit_prompt() (clean prompt, no tool text)          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          RESPONSE PHASE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  4. PageController.get_response() waits for completion                   │
│                     │                                                    │
│                     v                                                    │
│  5. ResponseParser.parse_native_response()                               │
│        ├── Check DOM for function call widgets                           │
│        ├── Extract function name and arguments                           │
│        └── Return ParsedFunctionCall list                                │
│                     │                                                    │
│                     v                                                    │
│  6. ResponseFormatter.format_tool_calls()                                │
│        ├── IdManager.generate_id() for each call                         │
│        ├── json.dumps(arguments) -> string                               │
│        └── Build tool_calls array                                        │
│                     │                                                    │
│                     v                                                    │
│  7. Return OpenAI-compatible response                                    │
│        {                                                                 │
│          "choices": [{                                                   │
│            "message": {                                                  │
│              "role": "assistant",                                        │
│              "content": null,                                            │
│              "tool_calls": [{ "id": "call_...", ... }]                   │
│            },                                                            │
│            "finish_reason": "tool_calls"                                 │
│          }]                                                              │
│        }                                                                 │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Native Mode - Streaming

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         STREAMING RESPONSE                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Chunk 1 (Start):                                                        │
│    {                                                                     │
│      "delta": {                                                          │
│        "tool_calls": [{                                                  │
│          "index": 0,                                                     │
│          "id": "call_abc123",      <-- Generated ID                      │
│          "type": "function",                                             │
│          "function": {                                                   │
│            "name": "get_weather",                                        │
│            "arguments": ""                                               │
│          }                                                               │
│        }]                                                                │
│      }                                                                   │
│    }                                                                     │
│                                                                          │
│  Chunk 2...N (Arguments):                                                │
│    {                                                                     │
│      "delta": {                                                          │
│        "tool_calls": [{                                                  │
│          "index": 0,                                                     │
│          "function": {                                                   │
│            "arguments": "{\"loc"   <-- Streamed fragment                 │
│          }                                                               │
│        }]                                                                │
│      }                                                                   │
│    }                                                                     │
│                                                                          │
│  Final Chunk:                                                            │
│    {                                                                     │
│      "delta": {},                                                        │
│      "finish_reason": "tool_calls"                                       │
│    }                                                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Tool Result Flow

When client sends tool results:

```
Request:
{
  "messages": [
    {"role": "user", "content": "What's the weather?"},
    {"role": "assistant", "tool_calls": [{"id": "call_abc123", ...}]},
    {"role": "tool", "tool_call_id": "call_abc123", "content": "{...result...}"}
  ]
}

Processing:
1. Orchestrator detects tool result message(s)
2. In NATIVE mode:
   - Browser may have "Reply" input for function result
   - OR: Format as text and submit as follow-up
3. In EMULATED mode:
   - Append "Tool result (tool_call_id=call_abc123): ..." to prompt
```

---

## 9. Configuration Schema

### 9.1 Environment Variables

```bash
# --- Function Calling Configuration ---

# Mode: "emulated" | "native" | "auto"
FUNCTION_CALLING_MODE=emulated

# Native mode retry attempts before fallback
FC_NATIVE_RETRY_COUNT=2

# Enable automatic fallback to emulated on native failure
FC_FALLBACK_ON_FAILURE=true

# Clear function definitions between requests (stateless behavior)
FC_CLEAR_BETWEEN_REQUESTS=true

# Timeout for function UI operations (ms)
FC_UI_TIMEOUT_MS=5000

# Enable detailed function calling debug logs
FC_DEBUG_LOGS=false
```

### 9.2 Runtime Configuration Override

Per-request override via custom header (optional feature):
```
X-Function-Calling-Mode: native
```

---

## 10. API Compatibility Layer

### 10.1 Request Compatibility

| OpenAI Field | Supported | Notes |
|--------------|-----------|-------|
| `tools` | Yes | Array of function definitions |
| `tool_choice: "auto"` | Yes | Model decides |
| `tool_choice: "none"` | Yes | Disable function calling |
| `tool_choice: "required"` | Partial | May need prompt injection |
| `tool_choice: {type, function}` | Partial | Force specific function |
| `parallel_tool_calls` | No | Gemini behavior, not configurable |

### 10.2 Response Compatibility

| OpenAI Field | Generated | Notes |
|--------------|-----------|-------|
| `tool_calls[].id` | Yes | `call_<uuid>` format |
| `tool_calls[].type` | Yes | Always `"function"` |
| `tool_calls[].function.name` | Yes | Extracted from response |
| `tool_calls[].function.arguments` | Yes | **String** (JSON serialized) |
| `finish_reason: "tool_calls"` | Yes | When function called |
| `finish_reason: "stop"` | Yes | Normal completion |

### 10.3 Special Tool Handling

| Tool Name | Behavior |
|-----------|----------|
| `googleSearch` | Routed to existing Google Search toggle |
| `google_search_retrieval` | Alias for googleSearch |
| Other functions | Native function calling UI |

---

## 11. Browser Automation Strategy

### 11.1 UI Interaction Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FUNCTION UI AUTOMATION SEQUENCE                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ENABLE FUNCTION CALLING:                                                │
│  ┌────────────────────────────────────────────────────┐                  │
│  │ 1. Locate toggle: data-test-id="functionCallingTooltip"              │
│  │ 2. Check aria-checked state                                          │
│  │ 3. If "false", click to enable                                       │
│  │ 4. Wait for toggle state change                                      │
│  └────────────────────────────────────────────────────┘                  │
│                                                                          │
│  SET DECLARATIONS:                                                       │
│  ┌────────────────────────────────────────────────────┐                  │
│  │ 1. Click "Edit" button                                               │
│  │ 2. Wait for modal/panel to appear                                    │
│  │ 3. Locate declarations textarea                                      │
│  │ 4. Triple-click to select all (or Ctrl+A)                            │
│  │ 5. Paste JSON declarations                                           │
│  │ 6. Click "Save" / "Done"                                             │
│  │ 7. Wait for modal to close                                           │
│  └────────────────────────────────────────────────────┘                  │
│                                                                          │
│  PARSE FUNCTION CALL RESPONSE:                                           │
│  ┌────────────────────────────────────────────────────┐                  │
│  │ 1. Wait for response completion                                      │
│  │ 2. Locate function call widgets in response area                     │
│  │ 3. Extract function name from widget                                 │
│  │ 4. Extract arguments JSON from widget                                │
│  │ 5. Parse arguments to Dict                                           │
│  └────────────────────────────────────────────────────┘                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 11.2 Selector Strategy

**Priority Order:**
1. `data-test-id` attributes (most stable)
2. `aria-label` attributes (accessibility)
3. Element structure (component names like `ms-*`)
4. Text content (`:has-text()`) as fallback

**Selector Resilience:**
```python
# Multiple fallback selectors joined with comma
FUNCTION_CALLING_TOGGLE_SELECTOR = (
    'div[data-test-id="functionCallingTooltip"] button[role="switch"], '
    '[data-test-id*="function"] mat-slide-toggle button, '
    'button[aria-label*="function calling" i]'
)
```

### 11.3 Code Editor Preference

As per external research, always prefer the **Code Editor (JSON)** tab over visual form fields:
- More reliable for automation
- Single paste operation vs multiple field fills
- Easier validation (JSON parse check)

---

## 12. Error Handling

### 12.1 Error Categories

| Category | Examples | Handling |
|----------|----------|----------|
| **UI Not Found** | Toggle missing, modal not opening | Fallback to emulated |
| **Timeout** | UI slow to respond | Retry with backoff |
| **Parse Error** | Invalid function call format | Return raw text response |
| **Schema Error** | Invalid tool definition | Reject request with 400 |
| **Client Disconnect** | Connection dropped | Cancel and cleanup |

### 12.2 Fallback Strategy (Auto Mode)

```python
async def process_with_fallback(
    self,
    tools: List[Dict],
    ...
) -> ProcessedResponse:
    if self.config.mode == FunctionCallingMode.AUTO:
        try:
            return await self._process_native(tools, ...)
        except NativeModeError as e:
            logger.warning(f"Native mode failed: {e}, falling back to emulated")
            return await self._process_emulated(tools, ...)
    elif self.config.mode == FunctionCallingMode.NATIVE:
        return await self._process_native(tools, ...)
    else:
        return await self._process_emulated(tools, ...)
```

### 12.3 Error Response Format

```json
{
  "error": {
    "message": "Function calling UI automation failed: toggle not found",
    "type": "function_calling_error",
    "param": null,
    "code": "native_mode_unavailable"
  }
}
```

## 13. Performance & Caching

### 13.1 Problem Statement
Native function calling involves expensive UI operations (opening dialogs, pasting JSON) which can take 2-4 seconds per request. In agentic workflows where tools remain constant across many turns, this adds significant latency.

### 13.2 Caching Strategy
To mitigate this, we employ a digest-based caching mechanism:

1.  **State Tracking**: The system maintains a SHA256 digest of the currently configured tool definitions.
2.  **Cache Hit**: If the incoming request's tools match the cached digest and the function calling toggle is already enabled, UI configuration is skipped completely.
3.  **Cache Miss**: If tools differ, the standard UI automation sequence runs, and the cache is updated.
4.  **Invalidation**: Cache is invalidated on:
    *   Model switching
    *   New chat creation (clearing history)
    *   Explicit cache clear requests

### 13.3 Configuration
*   `FUNCTION_CALLING_CACHE_ENABLED`: Enable/disable caching (default: true)
*   `FUNCTION_CALLING_CACHE_TTL`: Optional time-to-live for cache entries

## 14. Implementation Roadmap


### Phase 1: Foundation (Effort: M)
| Task | Priority | Risk |
|------|----------|------|
| Create `function_calling/` package structure | High | Low |
| Implement `FunctionCallingConfig` | High | Low |
| Add environment variables to `settings.py` | High | Low |
| Implement `SchemaConverter` | High | Low |
| Implement `CallIdManager` | High | Low |

### Phase 2: Browser Automation (Effort: L)
| Task | Priority | Risk |
|------|----------|------|
| Identify and validate UI selectors | High | **High** |
| Implement `FunctionController` | High | Medium |
| Add selectors to `config/selectors.py` | High | Low |
| Test toggle enable/disable | High | Medium |
| Test declaration paste/save | High | Medium |

### Phase 3: Response Handling (Effort: M)
| Task | Priority | Risk |
|------|----------|------|
| Implement `ResponseParser` for native mode | High | Medium |
| Implement `ResponseFormatter` | High | Low |
| Handle streaming deltas | High | Medium |
| Test with real function calls | High | Medium |

### Phase 4: Integration (Effort: M)
| Task | Priority | Risk |
|------|----------|------|
| Implement `Orchestrator` | High | Medium |
| Modify `request_processor.py` to use orchestrator | High | Medium |
| Modify `prompts.py` to skip tool injection in native mode | High | Low |
| Wire up response formatting | High | Low |

### Phase 5: Testing & Polish (Effort: S)
| Task | Priority | Risk |
|------|----------|------|
| Unit tests for converters/formatters | Medium | Low |
| Integration tests with mock browser | Medium | Medium |
| Documentation updates | Medium | Low |
| Performance benchmarking | Low | Low |

---

## 15. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| AI Studio UI changes break selectors | High | High | Use `data-test-id` where possible; implement selector versioning |
| Function call widget DOM structure unknown | Medium | High | Browser inspection spike before Phase 2; flexible parser |
| Modal timing issues | Medium | Medium | Configurable timeouts; retry logic |
| Streaming function calls incomplete | Medium | Medium | Buffer and validate before emitting |
| Performance overhead from UI automation | Low | Medium | Cache function declarations when unchanged |
| Native mode unsupported on some models | Low | Low | Per-model capability detection |
| **Cache Desynchronization** | Low | Medium | Invalidate cache on all state-changing events (model switch, new chat) |

---

## Appendix A: Selector Discovery Checklist

Before implementation, manually inspect AI Studio UI to confirm:

- [ ] Toggle switch exact selector and aria-checked behavior
- [ ] Edit button selector and click behavior
- [ ] Modal/panel structure after Edit click
- [ ] Textarea selector for declarations
- [ ] Save/Done button selector
- [ ] Function call response widget structure
- [ ] Function name location in response widget
- [ ] Arguments location in response widget
- [ ] Any additional confirmation dialogs

---

## Appendix B: Test Scenarios

| Scenario | Expected Behavior |
|----------|-------------------|
| Single function, model calls it | Return tool_calls with 1 item |
| Single function, model declines | Return content with no tool_calls |
| Multiple functions, model picks one | Return tool_calls with 1 item |
| Parallel function calls | Return tool_calls with N items |
| Tool result submission | Continue conversation with result |
| Invalid tool definition | Return 400 error |
| UI automation failure (auto mode) | Fallback to emulated, log warning |
| UI automation failure (native mode) | Return 500 error |
| Streaming with function call | Emit proper delta chunks |

---

## Appendix C: Related Files

| File | Change Type | Description |
|------|-------------|-------------|
| `api_utils/utils_ext/function_calling/*` | **New** | Core function calling package |
| `browser_utils/page_controller_modules/functions.py` | **New** | UI automation |
| `config/settings.py` | Modify | Add FC_* environment variables |
| `config/selectors.py` | Modify | Add function UI selectors |
| `api_utils/utils_ext/prompts.py` | Modify | Skip tool injection when native |
| `api_utils/request_processor.py` | Modify | Integrate orchestrator |
| `api_utils/response_payloads.py` | Modify | Support tool_calls in message |
| `api_utils/response_generators.py` | Modify | Handle tool_calls streaming |

---

**Document Version:** 1.0
**Last Updated:** 2025-01-23
**Author:** Architecture Agent
