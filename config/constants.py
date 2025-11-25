"""
Constants Configuration Module
Contains all fixed constant definitions, such as model names, markers, filenames, etc.
"""

import os
import json
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# --- Model Related Constants ---
MODEL_NAME = os.environ.get('MODEL_NAME', 'AI-Studio_Proxy_API')
CHAT_COMPLETION_ID_PREFIX = os.environ.get('CHAT_COMPLETION_ID_PREFIX', 'chatcmpl-')
DEFAULT_FALLBACK_MODEL_ID = os.environ.get('DEFAULT_FALLBACK_MODEL_ID', "no model list")

# --- Default Parameter Values ---
DEFAULT_TEMPERATURE = float(os.environ.get('DEFAULT_TEMPERATURE', '1.0'))
DEFAULT_MAX_OUTPUT_TOKENS = int(os.environ.get('DEFAULT_MAX_OUTPUT_TOKENS', '65536'))
DEFAULT_TOP_P = float(os.environ.get('DEFAULT_TOP_P', '0.95'))
# --- Default Feature Toggles ---
ENABLE_URL_CONTEXT = os.environ.get('ENABLE_URL_CONTEXT', 'false').lower() in ('true', '1', 'yes')
ENABLE_THINKING_BUDGET = os.environ.get('ENABLE_THINKING_BUDGET', 'false').lower() in ('true', '1', 'yes')
DEFAULT_THINKING_BUDGET = int(os.environ.get('DEFAULT_THINKING_BUDGET', '8192'))
ENABLE_GOOGLE_SEARCH = os.environ.get('ENABLE_GOOGLE_SEARCH', 'false').lower() in ('true', '1', 'yes')

# Default Stop Sequences - Support JSON format configuration
try:
    DEFAULT_STOP_SEQUENCES = json.loads(os.environ.get('DEFAULT_STOP_SEQUENCES', '["User:"]'))
except (json.JSONDecodeError, TypeError):
    DEFAULT_STOP_SEQUENCES = ["User:"]  # Fallback to default value

# --- URL Patterns ---
AI_STUDIO_URL_PATTERN = os.environ.get('AI_STUDIO_URL_PATTERN', 'aistudio.google.com/')
MODELS_ENDPOINT_URL_CONTAINS = os.environ.get('MODELS_ENDPOINT_URL_CONTAINS', "MakerSuiteService/ListModels")

# --- Input Markers ---
USER_INPUT_START_MARKER_SERVER = os.environ.get('USER_INPUT_START_MARKER_SERVER', "__USER_INPUT_START__")
USER_INPUT_END_MARKER_SERVER = os.environ.get('USER_INPUT_END_MARKER_SERVER', "__USER_INPUT_END__")

# --- Filename Constants ---
EXCLUDED_MODELS_FILENAME = os.environ.get('EXCLUDED_MODELS_FILENAME', "excluded_models.txt")

# --- Stream State Configuration ---
STREAM_TIMEOUT_LOG_STATE = {
    "consecutive_timeouts": 0,
    "last_error_log_time": 0.0,  # 使用 time.monotonic()
    "suppress_until_time": 0.0,  # 使用 time.monotonic()
    "max_initial_errors": int(os.environ.get('STREAM_MAX_INITIAL_ERRORS', '3')),
    "warning_interval_after_suppress": float(os.environ.get('STREAM_WARNING_INTERVAL_AFTER_SUPPRESS', '60.0')),
    "suppress_duration_after_initial_burst": float(os.environ.get('STREAM_SUPPRESS_DURATION_AFTER_INITIAL_BURST', '400.0')),
}