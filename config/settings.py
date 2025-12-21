"""
Main Settings Configuration Module
Contains runtime settings such as environment variable configuration, path configuration, proxy configuration, etc.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# --- Global Log Control Configuration ---
DEBUG_LOGS_ENABLED = os.environ.get("DEBUG_LOGS_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
TRACE_LOGS_ENABLED = os.environ.get("TRACE_LOGS_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
JSON_LOGS_ENABLED = os.environ.get("JSON_LOGS", "false").lower() in (
    "true",
    "1",
    "yes",
)

# --- Log Rotation Configuration ---
LOG_FILE_MAX_BYTES = int(
    os.environ.get("LOG_FILE_MAX_BYTES", str(10 * 1024 * 1024))
)  # 10MB default
LOG_FILE_BACKUP_COUNT = int(os.environ.get("LOG_FILE_BACKUP_COUNT", "5"))

# --- Auth Related Configuration ---
AUTO_SAVE_AUTH = os.environ.get("AUTO_SAVE_AUTH", "").lower() in ("1", "true", "yes")
AUTH_SAVE_TIMEOUT = int(os.environ.get("AUTH_SAVE_TIMEOUT", "30"))
AUTO_CONFIRM_LOGIN = os.environ.get('AUTO_CONFIRM_LOGIN', 'true').lower() in ('1', 'true', 'yes')

# --- Path Configuration (Using pathlib) ---
_CONFIG_DIR = Path(__file__).parent
_PROJECT_ROOT = _CONFIG_DIR.parent

AUTH_PROFILES_DIR = str(_PROJECT_ROOT / "auth_profiles")
ACTIVE_AUTH_DIR = str(_PROJECT_ROOT / "auth_profiles" / "active")
SAVED_AUTH_DIR = str(_PROJECT_ROOT / "auth_profiles" / "saved")
LOG_DIR = str(_PROJECT_ROOT / "logs")
APP_LOG_FILE_PATH = str(_PROJECT_ROOT / "logs" / "app.log")
UPLOAD_FILES_DIR = str(_PROJECT_ROOT / "upload_files")

def get_environment_variable(key: str, default: str = '') -> str:
    """Get environment variable value"""
    return os.environ.get(key, default)

def get_boolean_env(key: str, default: bool = False) -> bool:
    """Get boolean environment variable"""
    value = os.environ.get(key, '').lower()
    if default:
        return value not in ('false', '0', 'no', 'off')
    else:
        return value in ('true', '1', 'yes', 'on')

def get_int_env(key: str, default: int = 0) -> int:
    """Get integer environment variable"""
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default

# --- Proxy Configuration ---
NO_PROXY_ENV = os.environ.get('NO_PROXY')

# --- Script Injection Configuration ---
ENABLE_SCRIPT_INJECTION = get_boolean_env('ENABLE_SCRIPT_INJECTION', True)
ONLY_COLLECT_CURRENT_USER_ATTACHMENTS = get_boolean_env('ONLY_COLLECT_CURRENT_USER_ATTACHMENTS', False)
USERSCRIPT_PATH = get_environment_variable('USERSCRIPT_PATH', 'browser_utils/more_models.js')

# --- Response Integrity Verification Configuration ---
EMERGENCY_WAIT_SECONDS = get_int_env('EMERGENCY_WAIT_SECONDS', 3)

# --- Thinking Budget Configuration ---
DISABLE_THINKING_BUDGET_ON_STREAMING_DISABLE = get_boolean_env("DISABLE_THINKING_BUDGET_ON_STREAMING_DISABLE", default=True)

# --- Proactive Rotation Configuration ---
QUOTA_SOFT_LIMIT = get_int_env('QUOTA_SOFT_LIMIT', 650000)
QUOTA_HARD_LIMIT = get_int_env('QUOTA_HARD_LIMIT', 800000)

MODEL_QUOTA_LIMITS = {}
for key, value in os.environ.items():
    if key.upper().startswith("QUOTA_LIMIT_"):
        try:
            model_id = key[12:].lower()
            MODEL_QUOTA_LIMITS[model_id] = int(value)
        except ValueError:
            continue

PROACTIVE_ROTATION_TOKEN_LIMIT = QUOTA_HARD_LIMIT

# --- Dynamic Rotation Guard Configuration ---
HIGH_TRAFFIC_QUEUE_THRESHOLD = get_int_env('HIGH_TRAFFIC_QUEUE_THRESHOLD', 5)
ROTATION_DEPLETION_GUARD_HIGH_TRAFFIC = get_int_env('ROTATION_DEPLETION_GUARD_HIGH_TRAFFIC', 10)

# --- Granular Configuration for Auth and Budget ---
AUTO_ROTATE_AUTH_PROFILE = get_boolean_env('AUTO_ROTATE_AUTH_PROFILE', True)

def _get_thinking_budget_value(env_key: str, default: int, level_name: str) -> int:
    try:
        value = get_int_env(env_key, default)
        if value <= 0:
            return default
        return value
    except (ValueError, TypeError):
        return default

THINKING_BUDGET_LOW = _get_thinking_budget_value('THINKING_BUDGET_LOW', 8000, "LOW")
THINKING_BUDGET_MEDIUM = _get_thinking_budget_value('THINKING_BUDGET_MEDIUM', 16000, "MEDIUM")
THINKING_BUDGET_HIGH = _get_thinking_budget_value('THINKING_BUDGET_HIGH', 32000, "HIGH")

DEFAULT_THINKING_LEVEL = os.environ.get('DEFAULT_THINKING_LEVEL', 'low')
