"""
CSS Selector Configuration Module
Contains all CSS selectors used for page element location.
"""

# --- Input Related Selectors ---
# Main input textarea compatible with current and old UI structures
PROMPT_TEXTAREA_SELECTOR = (
    "textarea.textarea, "
    "ms-autosize-textarea textarea, "
    "ms-chunk-input textarea, "
    "ms-prompt-input-wrapper ms-autosize-textarea textarea, "
    'ms-prompt-input-wrapper textarea[aria-label*="prompt" i], '
    "ms-prompt-input-wrapper textarea, "
    "ms-prompt-box ms-autosize-textarea textarea, "
    'ms-prompt-box textarea[aria-label="Enter a prompt"], '
    "ms-prompt-box textarea"
)
INPUT_SELECTOR = PROMPT_TEXTAREA_SELECTOR
INPUT_SELECTOR2 = PROMPT_TEXTAREA_SELECTOR

# --- Button Selectors ---
SUBMIT_BUTTON_SELECTOR = (
    'ms-prompt-input-wrapper ms-run-button button[aria-label="Run"], '
    'ms-prompt-input-wrapper button[aria-label="Run"][type="submit"], '
    'button[aria-label="Run"].run-button, '
    'ms-run-button button[type="submit"].run-button, '
    'ms-prompt-box ms-run-button button[aria-label="Run"], '
    'ms-prompt-box button[aria-label="Run"][type="submit"]'
)

REGENERATE_BUTTON_SELECTOR = 'button[aria-label="Regenerate draft"], button[aria-label="Regenerate response"], [data-testid*="regenerate"]'

CLEAR_CHAT_BUTTON_SELECTOR = 'button[data-test-clear="outside"][aria-label="New chat"], button[aria-label="New chat"]'
CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR = (
    'button.ms-button-primary:has-text("Discard and continue")'
)
UPLOAD_BUTTON_SELECTOR = (
    'button[data-test-id="add-media-button"], '
    'button[aria-label^="Insert assets"], '
    'button[aria-label^="Insert images"]'
)

# --- Response Selectors ---
RESPONSE_CONTAINER_SELECTOR = "ms-chat-turn .chat-turn-container.model"
RESPONSE_TEXT_SELECTOR = "ms-cmark-node.cmark-node"

# --- Loading and Status Selectors ---
LOADING_SPINNER_SELECTOR = 'button[aria-label="Run"].run-button svg .stoppable-spinner'
OVERLAY_SELECTOR = ".mat-mdc-dialog-inner-container"

# --- Error Notification Selectors ---
ERROR_TOAST_SELECTOR = "div.toast.warning, div.toast.error"
QUOTA_EXCEEDED_SELECTOR = "ms-callout.error-callout .message"

# --- Edit Related Selectors ---
EDIT_MESSAGE_BUTTON_SELECTOR = (
    "ms-chat-turn:last-child .actions-container button.toggle-edit-button"
)
MESSAGE_TEXTAREA_SELECTOR = (
    "ms-chat-turn:last-child textarea, ms-chat-turn:last-child ms-text-chunk textarea"
)
FINISH_EDIT_BUTTON_SELECTOR = 'ms-chat-turn:last-child .actions-container button.toggle-edit-button[aria-label="Stop editing"]'

# --- Menu and Copy Selectors ---
MORE_OPTIONS_BUTTON_SELECTOR = (
    "div.actions-container div ms-chat-turn-options div > button"
)
COPY_MARKDOWN_BUTTON_SELECTOR = "button.mat-mdc-menu-item:nth-child(4)"
COPY_MARKDOWN_BUTTON_SELECTOR_ALT = 'div[role="menu"] button:has-text("Copy Markdown")'

# --- Settings Selectors ---
MAX_OUTPUT_TOKENS_SELECTOR = 'input[aria-label="Maximum output tokens"]'
STOP_SEQUENCE_INPUT_SELECTOR = 'input[aria-label="Add stop token"]'
MAT_CHIP_REMOVE_BUTTON_SELECTOR = 'mat-chip button.remove-button[aria-label*="Remove"]'
TOP_P_INPUT_SELECTOR = 'ms-slider input[type="number"][max="1"]'
TEMPERATURE_INPUT_SELECTOR = 'ms-slider input[type="number"][max="2"]'
USE_URL_CONTEXT_SELECTOR = 'button[aria-label="Browse the url context"]'

# --- Thinking Mode Selectors ---
THINKING_CONTAINER_SELECTOR = "ms-thought-accordion, ms-thought-chunk, [data-testid*='thinking'], [data-testid*='reasoning']"
THINKING_HEADER_SELECTOR = "ms-thought-accordion .header, ms-thought-chunk .header, [data-testid*='thinking'] .header, [data-testid*='reasoning'] .header"
THINKING_CONTENT_SELECTOR = "ms-thought-chunk .mat-expansion-panel-body, ms-thought-accordion .content, ms-thought-accordion .markdown-content, [data-testid*='thinking'] .content, [data-testid*='reasoning'] .content"
THINKING_DIV_SELECTOR = "div.thinking-process, div.reasoning-process, [class*='thinking'], [class*='reasoning'], [class*='analysis']"
THINKING_ACCORDION_SELECTOR = "ms-thought-accordion, ms-thought-chunk, [data-testid*='accordion'], [class*='accordion'][data-testid*='thinking'], [class*='accordion'][class*='thinking']"

FINAL_RESPONSE_SELECTOR = "ms-text-chunk:not(:has(ms-thought-chunk)), ms-cmark-node.cmark-node:not(ms-thought-accordion .content):not(ms-thought-chunk .mat-expansion-panel-body), [data-testid*='response'], [class*='response-content'], .chat-response"
ANSWER_TEXT_SELECTOR = "ms-cmark-node.cmark-node"

COMPLETE_RESPONSE_CONTAINER_SELECTOR = "ms-chat-turn .chat-turn-container.model, [data-testid*='chat-turn'], [class*='chat-turn']"
GENERATION_STATUS_SELECTOR = "button[aria-label*='Stop'], button[aria-label*='Generating'], [data-testid*='generating']"

ENABLE_THINKING_MODE_TOGGLE_SELECTOR = (
    'button[role="switch"][aria-label="Toggle thinking mode"], '
    'mat-slide-toggle[data-test-toggle="enable-thinking"] button[role="switch"].mdc-switch, '
    '[data-test-toggle="enable-thinking"] button[role="switch"].mdc-switch'
)

SET_THINKING_BUDGET_TOGGLE_SELECTOR = (
    'button[role="switch"][aria-label="Toggle thinking budget between auto and manual"], '
    'mat-slide-toggle[data-test-toggle="manual-budget"] button[role="switch"].mdc-switch, '
    '[data-test-toggle="manual-budget"] button[role="switch"].mdc-switch'
)

THINKING_BUDGET_INPUT_SELECTOR = (
    '[data-test-id="user-setting-budget-animation-wrapper"] input[type="number"]'
)

THINKING_LEVEL_DROPDOWN_SELECTOR = 'mat-select[aria-label="Thinking Level"]'
THINKING_LEVEL_SELECT_SELECTOR = '[role="combobox"][aria-label="Thinking Level"], mat-select[aria-label="Thinking Level"], [role="combobox"][aria-label="Thinking level"], mat-select[aria-label="Thinking level"]'
THINKING_LEVEL_OPTION_LOW_SELECTOR = '[role="listbox"][aria-label="Thinking Level"] [role="option"]:has-text("Low"), [role="listbox"][aria-label="Thinking level"] [role="option"]:has-text("Low")'
THINKING_LEVEL_OPTION_HIGH_SELECTOR = '[role="listbox"][aria-label="Thinking Level"] [role="option"]:has-text("High"), [role="listbox"][aria-label="Thinking level"] [role="option"]:has-text("High")'
THINKING_LEVEL_OPTION_MEDIUM_SELECTOR = '[role="listbox"][aria-label="Thinking Level"] [role="option"]:has-text("Medium"), [role="listbox"][aria-label="Thinking level"] [role="option"]:has-text("Medium")'
THINKING_LEVEL_OPTION_MINIMAL_SELECTOR = '[role="listbox"][aria-label="Thinking Level"] [role="option"]:has-text("Minimal"), [role="listbox"][aria-label="Thinking level"] [role="option"]:has-text("Minimal")'

GROUNDING_WITH_GOOGLE_SEARCH_TOGGLE_SELECTOR = (
    'div[data-test-id="searchAsAToolTooltip"] mat-slide-toggle button'
)

SCROLL_CONTAINER_SELECTOR = "ms-autoscroll-container"
CHAT_SESSION_CONTENT_SELECTOR = ".chat-session-content"
LAST_CHAT_TURN_SELECTOR = "ms-chat-turn:last-of-type"

MODEL_NAME_SELECTOR = '[data-test-id="model-name"]'
CDK_OVERLAY_CONTAINER_SELECTOR = "div.cdk-overlay-container"
CHAT_TURN_SELECTOR = "ms-chat-turn"

THINKING_MODE_TOGGLE_PARENT_SELECTOR = (
    'mat-slide-toggle:has(button[aria-label="Toggle thinking mode"])'
)
THINKING_MODE_TOGGLE_OLD_ROOT_SELECTOR = (
    'mat-slide-toggle[data-test-toggle="enable-thinking"]'
)
THINKING_BUDGET_TOGGLE_PARENT_SELECTOR = 'mat-slide-toggle:has(button[aria-label="Toggle thinking budget between auto and manual"])'
THINKING_BUDGET_TOGGLE_OLD_ROOT_SELECTOR = (
    'mat-slide-toggle[data-test-toggle="manual-budget"]'
)

# --- Function Call Response Selectors ---
# Selectors for detecting and parsing function call widgets in AI Studio responses.
# These are displayed when the model wants to call a function.

# Native Function Call Response Selectors (AI Studio's built-in function calling UI)
# These are used when native function calling is enabled and the model returns tool calls.

# Native function call chunk container (primary selector for native FC responses)
NATIVE_FUNCTION_CALL_CHUNK_SELECTOR = (
    "ms-function-call-chunk, ms-prompt-chunk:has(ms-function-call-chunk)"
)

# Native function call code block (contains function name and args)
NATIVE_FUNCTION_CALL_CODE_BLOCK_SELECTOR = (
    'ms-function-call-chunk ms-code-block[icon="function"], '
    "ms-function-call-chunk ms-code-block"
)

# Native function call name selector (in the expansion panel header)
NATIVE_FUNCTION_CALL_NAME_SELECTOR = (
    "ms-function-call-chunk ms-code-block mat-panel-title span:not(.material-symbols-outlined), "
    "ms-function-call-chunk ms-code-block .mat-expansion-panel-header-title span:nth-child(2)"
)

# Native function call arguments selector (JSON in pre > code block)
NATIVE_FUNCTION_CALL_ARGS_SELECTOR = (
    "ms-function-call-chunk ms-code-block pre code, "
    "ms-function-call-chunk ms-code-block .mat-expansion-panel-body pre code, "
    "ms-function-call-chunk pre code"
)

# Function call widget container (wraps the entire function call block) - legacy/fallback
FUNCTION_CALL_WIDGET_SELECTOR = (
    "ms-function-call-chunk, "
    "ms-function-call, "
    "[data-test-id='function-call'], "
    "[data-testid='function-call'], "
    ".function-call-widget, "
    ".function-call-container, "
    "ms-chat-turn .function-call"
)

# Function call header containing the function name
FUNCTION_CALL_NAME_SELECTOR = (
    "ms-function-call-chunk ms-code-block mat-panel-title span:not(.material-symbols-outlined), "
    "ms-function-call .function-name, "
    "[data-test-id='function-call'] .function-name, "
    ".function-call-widget .function-name, "
    ".function-call-name, "
    "ms-function-call [data-testid='function-name'], "
    "[data-test-id='function-call-name']"
)

# Function call arguments/parameters container (usually JSON or formatted view)
FUNCTION_CALL_ARGS_SELECTOR = (
    "ms-function-call-chunk ms-code-block pre code, "
    "ms-function-call .function-args, "
    "ms-function-call .function-arguments, "
    "ms-function-call pre, "
    "ms-function-call code, "
    "[data-test-id='function-call'] .arguments, "
    "[data-test-id='function-call'] pre, "
    "[data-test-id='function-call'] code, "
    ".function-call-widget .arguments, "
    ".function-call-arguments, "
    "[data-testid='function-arguments']"
)

# Code block containing function call JSON (alternative to structured widget)
FUNCTION_CALL_CODE_BLOCK_SELECTOR = (
    "ms-function-call-chunk ms-code-block, "
    "ms-chat-turn pre:has(code.language-json), "
    "ms-chat-turn pre:has(code.language-tool_code), "
    "ms-chat-turn .code-block:has-text('function_call'), "
    "ms-chat-turn .code-block:has-text('tool_call')"
)

# --- Function Calling Selectors ---
# Container for the function calling toggle and edit button
FUNCTION_CALLING_CONTAINER_SELECTOR = '[data-test-id="functionCallingTooltip"]'

# Toggle switch to enable/disable function calling
FUNCTION_CALLING_TOGGLE_SELECTOR = (
    '[data-test-id="functionCallingTooltip"] mat-slide-toggle button[role="switch"].mdc-switch, '
    '[data-test-id="functionCallingTooltip"] .function-calling-toggle button[role="switch"], '
    '[data-test-id="functionCallingTooltip"] button.mdc-switch'
)

# Button to open the function declarations editor modal
FUNCTION_DECLARATIONS_EDIT_BUTTON_SELECTOR = (
    '[data-test-id="functionCallingTooltip"] .edit-function-declarations-button, '
    'button.edit-function-declarations-button[aria-label="Edit function declarations"], '
    "button.edit-function-declarations-button"
)

# Function declarations modal dialog container
FUNCTION_DECLARATIONS_DIALOG_SELECTOR = (
    'mat-dialog-container:has(h2:has-text("Function declarations")), '
    'mat-mdc-dialog-container:has(h2:has-text("Function declarations")), '
    ".mat-mdc-dialog-container"
)

# Code Editor tab in the function declarations modal
FUNCTION_DECLARATIONS_CODE_EDITOR_TAB_SELECTOR = (
    'mat-dialog-container ms-tab-group button[role="tab"]:has-text("Code Editor"), '
    'mat-mdc-dialog-container ms-tab-group button[role="tab"]:has-text("Code Editor")'
)

# Visual Editor tab in the function declarations modal
FUNCTION_DECLARATIONS_VISUAL_EDITOR_TAB_SELECTOR = (
    'mat-dialog-container ms-tab-group button[role="tab"]:has-text("Visual Editor"), '
    'mat-mdc-dialog-container ms-tab-group button[role="tab"]:has-text("Visual Editor")'
)

# Textarea for entering function declarations JSON in Code Editor mode
FUNCTION_DECLARATIONS_TEXTAREA_SELECTOR = (
    "mat-dialog-container ms-text-editor textarea, "
    "mat-mdc-dialog-container ms-text-editor textarea, "
    'mat-dialog-container textarea[placeholder*="Tab"], '
    'mat-mdc-dialog-container textarea[placeholder*="Tab"]'
)

# Save button in the function declarations modal
FUNCTION_DECLARATIONS_SAVE_BUTTON_SELECTOR = (
    'mat-dialog-container button[aria-label="Save the current function declarations"], '
    'mat-mdc-dialog-container button[aria-label="Save the current function declarations"], '
    'mat-dialog-container button:has-text("Save"), '
    'mat-mdc-dialog-container button:has-text("Save")'
)

# Reset button in the function declarations modal
FUNCTION_DECLARATIONS_RESET_BUTTON_SELECTOR = (
    'mat-dialog-container button[aria-label="Reset the function declarations"], '
    'mat-mdc-dialog-container button[aria-label="Reset the function declarations"], '
    'mat-dialog-container button:has-text("Reset"), '
    'mat-mdc-dialog-container button:has-text("Reset")'
)

# Close/Cancel button in the function declarations modal (typically an X or Cancel button)
FUNCTION_DECLARATIONS_CLOSE_BUTTON_SELECTOR = (
    'mat-dialog-container button[aria-label="Close"], '
    'mat-mdc-dialog-container button[aria-label="Close"], '
    "mat-dialog-container button.close-button, "
    "mat-mdc-dialog-container button.close-button, "
    'mat-dialog-container button:has-text("Cancel"), '
    'mat-mdc-dialog-container button:has-text("Cancel")'
)
