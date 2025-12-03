# UI State Management

## Overview

The proxy actively manages the AI Studio browser UI state to ensure consistent behavior, reliable automation, and correct feature execution. This document details the various state management mechanisms, including LocalStorage configuration, Temporary Chat mode, Thinking Process controls, and Generation state.

## 1. LocalStorage Configuration (Advanced Settings)

Implemented in `browser_utils/model_management.py`, this system enforces critical UI preferences directly in the browser's `localStorage`.

### Core Requirements

- **`isAdvancedOpen: true`**: Ensures the advanced settings panel is open.
- **`areToolsOpen: true`**: Ensures the tools panel is open (required for some model interactions).

### Implementation Details

#### State Verification

**`_verify_ui_state_settings(page, req_id)`**

- **Function**: Inspects `localStorage.getItem('aiStudioUserPreference')`.
- **Checks**: Verifies if `isAdvancedOpen` and `areToolsOpen` are set to `true`.
- **Returns**: Status dictionary indicating if an update is needed.

#### Force Application

**`_force_ui_state_settings(page, req_id)`**

- **Function**: Directly writes the correct JSON object to `localStorage`.
- **Logic**:
  1. Reads current preferences.
  2. Overwrites `isAdvancedOpen` and `areToolsOpen` to `true`.
  3. Saves back to `localStorage`.
  4. Verifies the write was successful.

#### Integration Points

The system automatically verifies and applies these settings during:

1.  **Page Initialization**: When the browser first connects or loads.
2.  **Model Switching**: Before and after navigating to a new model.
3.  **Page Reloads**: If a reload is triggered by an error or state mismatch.

---

## 2. Temporary Chat Mode (Incognito)

The proxy enforces "Temporary Chat" (Incognito) mode to prevent chat history from cluttering the user's account and to ensure a clean state for each session.

### Implementation

**`enable_temporary_chat_mode(page)`** (in `browser_utils/initialization/core.py`)

- **Detection**: Checks the "Temporary chat toggle" button for the CSS class `ms-button-active`.
- **Action**: If the class is missing, it clicks the button to enable the mode.
- **Verification**: Waits and re-checks the class to confirm activation.

### Trigger Points

- **Initialization**: Immediately after the page loads.
- **After Clear Chat**: When the chat history is cleared (`/new_chat`), the mode is re-verified.
- **After Model Switch**: Switching models may reset UI state, so it is re-applied.

---

## 3. Thinking Process Management

Managed by `browser_utils/page_controller_modules/thinking.py`, this system controls the "Thinking" features of models (e.g., Gemini 2.0 Flash Thinking, Gemini 3 Pro).

### Logic Flow

1.  **Normalization**: The `reasoning_effort` parameter (low/high/integer) is normalized into a directive (Enabled/Disabled, Budget Value, or Level).
2.  **Model Detection**:
    - **Gemini 3 Pro**: Uses a "Thinking Level" dropdown (High/Low).
    - **Standard Thinking Models**: Use a "Thinking Budget" toggle and slider/input.

### Control Mechanisms

#### Main Toggle

**`_control_thinking_mode_toggle`**

- Controls the master "Thinking" switch.
- Verifies state via `aria-checked` attribute.

#### Budget Control (Standard)

**`_control_thinking_budget_toggle`** & **`_set_thinking_budget_value`**

- Enables the manual budget slider.
- **Input Injection**: Uses JavaScript to directly set the input value, bypassing UI drag-and-drop complexities. It handles `min`/`max` attribute constraints dynamically.

#### Thinking Level (Gemini 3 Pro)

**`_set_thinking_level`**

- Interacts with the specific dropdown for Gemini 3 Pro.
- Selects "High" (>= 8k tokens) or "Low" (< 8k tokens) based on the requested effort.

---

## 4. Generation Control (Stop Logic)

Managed by `browser_utils/page_controller_modules/response.py`, ensuring the UI is ready for a new request.

### Stop Generation

**`ensure_generation_stopped`**

- **Detection**: Checks the "Submit" button. If it is **enabled** while no text is in the input, it functions as a "Stop" button.
- **Action**: Clicks the button to halt the current generation.
- **Wait**: Waits for the button to become **disabled** (indicating the stop command was processed and the UI is resetting).

### Clear Chat Logic

**`clear_chat_history`** (in `browser_utils/page_controller_modules/chat.py`)

- **Pre-check**: Before clearing, it calls `ensure_generation_stopped` to prevent "Clear" button lock-ups caused by active generation.
- **Execution**: Clicks "Clear Chat", handles the confirmation dialog, and waits for the "New Chat" state.
- **Recovery**: Re-enables Temporary Chat mode after clearing.

---

## 5. Response Retrieval Interaction

Managed by `browser_utils/operations_modules/interactions.py`, this system handles how the proxy extracts the AI's response from the UI.

### Primary Method: Edit Button

**`get_response_via_edit_button`**

- **Logic**: Hovers over the last message to reveal the "Edit" button, clicks it, and extracts the raw Markdown from the underlying `textarea` or `data-value` attribute.
- **Advantage**: Provides the most accurate, raw Markdown representation of the response.

### Fallback Method: Copy Button

**`get_response_via_copy_button`**

- **Logic**: If the Edit button fails, it attempts to use the "Copy Markdown" option from the "More Options" menu.
- **Mechanism**: Clicks "Copy Markdown" and reads the system clipboard.

### Completion Detection

**`_wait_for_response_completion`**

- **Criteria**:
  1.  Input field is empty.
  2.  Submit button is disabled.
  3.  **Final Confirmation**: The "Edit" button becomes visible on the last message.
- **Heuristic**: If the primary criteria are met for a sustained period but the Edit button doesn't appear, it may assume completion to prevent infinite waits.
