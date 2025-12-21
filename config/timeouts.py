"""
Timeouts and Timing Configuration Module
Contains all time-related configurations such as timeouts and polling intervals.
"""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# --- Response Wait Configuration ---
RESPONSE_COMPLETION_TIMEOUT = int(os.environ.get('RESPONSE_COMPLETION_TIMEOUT', '300000'))  # 5 minutes total timeout (in ms)
INITIAL_WAIT_MS_BEFORE_POLLING = int(os.environ.get('INITIAL_WAIT_MS_BEFORE_POLLING', '500'))  # ms, initial wait before polling for response completion

# --- Polling Interval Configuration ---
POLLING_INTERVAL = int(os.environ.get('POLLING_INTERVAL', '300'))  # ms
POLLING_INTERVAL_STREAM = int(os.environ.get('POLLING_INTERVAL_STREAM', '180'))  # ms

# --- Silence Timeout Configuration ---
SILENCE_TIMEOUT_MS = int(os.environ.get('SILENCE_TIMEOUT_MS', '60000'))  # ms

# --- Page Operation Timeout Configuration ---
POST_SPINNER_CHECK_DELAY_MS = int(os.environ.get('POST_SPINNER_CHECK_DELAY_MS', '500'))
FINAL_STATE_CHECK_TIMEOUT_MS = int(os.environ.get('FINAL_STATE_CHECK_TIMEOUT_MS', '1500'))
POST_COMPLETION_BUFFER = int(os.environ.get('POST_COMPLETION_BUFFER', '700'))

# --- Chat Clearing Timeout Configuration ---
CLEAR_CHAT_VERIFY_TIMEOUT_MS = int(os.environ.get('CLEAR_CHAT_VERIFY_TIMEOUT_MS', '5000'))
CLEAR_CHAT_VERIFY_INTERVAL_MS = int(os.environ.get('CLEAR_CHAT_VERIFY_INTERVAL_MS', '2000'))

# --- Click and Clipboard Operation Timeout ---
CLICK_TIMEOUT_MS = int(os.environ.get('CLICK_TIMEOUT_MS', '3000'))
CLIPBOARD_READ_TIMEOUT_MS = int(os.environ.get('CLIPBOARD_READ_TIMEOUT_MS', '3000'))

# --- Element Wait Timeout ---
WAIT_FOR_ELEMENT_TIMEOUT_MS = int(os.environ.get('WAIT_FOR_ELEMENT_TIMEOUT_MS', '10000'))  # Timeout for waiting for elements like overlays

# --- UI Generation Wait Configuration ---
UI_GENERATION_WAIT_TIMEOUT_MS = int(os.environ.get('UI_GENERATION_WAIT_TIMEOUT_MS', '3000'))

# --- Adaptive Cooldown Configuration ---
# Rate Limit (429) - Shorter cooldown (default 5 minutes)
RATE_LIMIT_COOLDOWN_SECONDS = int(os.environ.get('RATE_LIMIT_COOLDOWN_SECONDS', '300'))
# Quota Exceeded (Resource Exhausted) - Longer cooldown (default 4 hours)
QUOTA_EXCEEDED_COOLDOWN_SECONDS = int(os.environ.get('QUOTA_EXCEEDED_COOLDOWN_SECONDS', '14400'))

# --- Stream Related Configuration ---
PSEUDO_STREAM_DELAY = float(os.environ.get('PSEUDO_STREAM_DELAY', '0.01'))

# --- Fast-Fail Configuration ---
# Submit button enable timeout - Lowered for fast-fail detection
SUBMIT_BUTTON_ENABLE_TIMEOUT_MS = int(os.environ.get("SUBMIT_BUTTON_ENABLE_TIMEOUT_MS", "5000"))

# --- Selector Timeout Configuration ---
# Quick existence check timeout (for rapid detection of elements in DOM)
SELECTOR_EXISTENCE_CHECK_TIMEOUT_MS = int(os.environ.get("SELECTOR_EXISTENCE_CHECK_TIMEOUT_MS", "500"))
# Element visibility wait timeout (general UI operations)
SELECTOR_VISIBILITY_TIMEOUT_MS = int(os.environ.get("SELECTOR_VISIBILITY_TIMEOUT_MS", "5000"))
# Startup selector visibility timeout (longer for page load)
STARTUP_SELECTOR_VISIBILITY_TIMEOUT_MS = int(os.environ.get("STARTUP_SELECTOR_VISIBILITY_TIMEOUT_MS", "30000"))
