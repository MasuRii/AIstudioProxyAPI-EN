"""
CSS Selector Configuration Module
Contains all CSS selectors used for page element location.
"""

# --- Input Selectors ---
PROMPT_TEXTAREA_SELECTOR = "ms-prompt-input-wrapper ms-autosize-textarea textarea"
INPUT_SELECTOR = PROMPT_TEXTAREA_SELECTOR
INPUT_SELECTOR2 = PROMPT_TEXTAREA_SELECTOR

# --- Button Selectors ---
# Submit button: Prefer matching buttons with aria-label="Run"; degenerate to submit button inside container if page structure changes.
SUBMIT_BUTTON_SELECTOR = 'button[aria-label="Run"].run-button, ms-run-button button[type="submit"].run-button'
# Regenerate button (Regenerate draft) - Used to determine if generation has truly ended
REGENERATE_BUTTON_SELECTOR = 'button[aria-label="Regenerate draft"], button[aria-label="Regenerate response"]'
CLEAR_CHAT_BUTTON_SELECTOR = 'button[data-test-clear="outside"][aria-label="New chat"], button[aria-label="New chat"]'
CLEAR_CHAT_CONFIRM_BUTTON_SELECTOR = (
    'button.ms-button-primary:has-text("Discard and continue")'
)
UPLOAD_BUTTON_SELECTOR = 'button[aria-label^="Insert assets"]'

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
MESSAGE_TEXTAREA_SELECTOR = "ms-chat-turn:last-child ms-text-chunk ms-autosize-textarea"
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
MAT_CHIP_REMOVE_BUTTON_SELECTOR = (
    'mat-chip-set mat-chip-row button[aria-label*="Remove"]'
)
TOP_P_INPUT_SELECTOR = 'ms-slider input[type="number"][max="1"]'
TEMPERATURE_INPUT_SELECTOR = 'ms-slider input[type="number"][max="2"]'
USE_URL_CONTEXT_SELECTOR = 'button[aria-label="Browse the url context"]'

# --- Thinking Mode Selectors ---
# Thinking Process Content Container (Thinking Content)
THINKING_CONTAINER_SELECTOR = "ms-thought-accordion, ms-thought-chunk, [data-testid*='thinking'], [data-testid*='reasoning']"
THINKING_HEADER_SELECTOR = "ms-thought-accordion .header, ms-thought-chunk .header, [data-testid*='thinking'] .header, [data-testid*='reasoning'] .header"
# [FIX-12] Updated to include ms-thought-chunk .mat-expansion-panel-body
THINKING_CONTENT_SELECTOR = "ms-thought-chunk .mat-expansion-panel-body, ms-thought-accordion .content, ms-thought-accordion .markdown-content, [data-testid*='thinking'] .content, [data-testid*='reasoning'] .content"
# Compatibility selector: Sometimes thinking block might just be a div with specific class
THINKING_DIV_SELECTOR = "div.thinking-process, div.reasoning-process, [class*='thinking'], [class*='reasoning'], [class*='analysis']"
# New: AI Studio latest version thinking block selector
THINKING_ACCORDION_SELECTOR = "ms-thought-accordion, ms-thought-chunk, [data-testid*='accordion'], [class*='accordion'][data-testid*='thinking'], [class*='accordion'][class*='thinking']"
# Final Response Content Selector (Excluding Thinking)
# [FIX-12] Updated to target ms-text-chunk and exclude thinking components
FINAL_RESPONSE_SELECTOR = "ms-text-chunk:not(:has(ms-thought-chunk)), ms-cmark-node.cmark-node:not(ms-thought-accordion .content):not(ms-thought-chunk .mat-expansion-panel-body), [data-testid*='response'], [class*='response-content'], .chat-response"
# Explicit selector for answer part only (AI Studio Update)
ANSWER_TEXT_SELECTOR = "ms-cmark-node.cmark-node"

# Complete Response Container (including thinking + response)
COMPLETE_RESPONSE_CONTAINER_SELECTOR = "ms-chat-turn .chat-turn-container.model, [data-testid*='chat-turn'], [class*='chat-turn']"
# AI Studio Status Indicator
GENERATION_STATUS_SELECTOR = "button[aria-label*='Stop'], button[aria-label*='Generating'], [data-testid*='generating']"
REGENERATE_BUTTON_SELECTOR = 'button[aria-label="Regenerate draft"], button[aria-label="Regenerate response"], [data-testid*="regenerate"]'

# Master Thinking Switch: Controls whether thinking mode is enabled (master switch)
ENABLE_THINKING_MODE_TOGGLE_SELECTOR = (
    'mat-slide-toggle[data-test-toggle="enable-thinking"] button[role="switch"].mdc-switch, '
    '[data-test-toggle="enable-thinking"] button[role="switch"].mdc-switch'
)

# Manual Budget Switch: Controls whether to manually limit thinking budget
SET_THINKING_BUDGET_TOGGLE_SELECTOR = (
    'mat-slide-toggle[data-test-toggle="manual-budget"] button[role="switch"].mdc-switch, '
    '[data-test-toggle="manual-budget"] button[role="switch"].mdc-switch'
)
# Thinking Budget Input Field
THINKING_BUDGET_INPUT_SELECTOR = '[data-test-slider] input[type="number"]'

# Thinking Level Dropdown (Gemini 3.0+ UI Detection) - Must include this
THINKING_LEVEL_DROPDOWN_SELECTOR = 'mat-select[aria-label="Thinking Level"]'

# Thinking Level Dropdown (Generic Selector)
THINKING_LEVEL_SELECT_SELECTOR = '[role="combobox"][aria-label="Thinking Level"], mat-select[aria-label="Thinking Level"], [role="combobox"][aria-label="Thinking level"], mat-select[aria-label="Thinking level"]'
THINKING_LEVEL_OPTION_LOW_SELECTOR = '[role="listbox"][aria-label="Thinking Level"] [role="option"]:has-text("Low"), [role="listbox"][aria-label="Thinking level"] [role="option"]:has-text("Low")'
THINKING_LEVEL_OPTION_HIGH_SELECTOR = '[role="listbox"][aria-label="Thinking Level"] [role="option"]:has-text("High"), [role="listbox"][aria-label="Thinking level"] [role="option"]:has-text("High")'

# --- Google Search Grounding ---
GROUNDING_WITH_GOOGLE_SEARCH_TOGGLE_SELECTOR = (
    'div[data-test-id="searchAsAToolTooltip"] mat-slide-toggle button'
)

# --- Scroll Related Selectors ---
SCROLL_CONTAINER_SELECTOR = "ms-autoscroll-container"
CHAT_SESSION_CONTENT_SELECTOR = ".chat-session-content"
LAST_CHAT_TURN_SELECTOR = "ms-chat-turn:last-of-type"