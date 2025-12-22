"""
High-quality tests for config/settings.py - Settings configuration.

Focus: Test helper functions and path configuration.
"""

import os
import sys
from unittest.mock import patch

import pytest

from config.settings import (
    get_boolean_env,
    get_environment_variable,
    get_int_env,
)

# ===================== get_environment_variable Tests =====================


def test_get_environment_variable_returns_value():
    """Test scenario: Return environment variable value when it exists."""
    with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
        assert get_environment_variable("TEST_VAR") == "test_value"


def test_get_environment_variable_returns_default():
    """Test scenario: Return default value when environment variable does not exist."""
    assert get_environment_variable("NON_EXISTENT_VAR", "default") == "default"


def test_get_environment_variable_returns_empty_default():
    """Test scenario: Return empty string when no default value is provided."""
    assert get_environment_variable("NON_EXISTENT_VAR") == ""


# ===================== get_boolean_env Tests =====================


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("YES", True),
        ("on", True),
        ("ON", True),
    ],
)
def test_get_boolean_env_true_values(env_value: str, expected: bool):
    """Test scenario: Boolean true value parsing (true/1/yes/on)."""
    with patch.dict(os.environ, {"BOOL_VAR": env_value}):
        assert get_boolean_env("BOOL_VAR") is expected


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("NO", False),
        ("off", False),
        ("OFF", False),
        ("", False),
        ("invalid", False),
    ],
)
def test_get_boolean_env_false_values(env_value: str, expected: bool):
    """Test scenario: Boolean false value parsing (false/0/no/off/empty/invalid)."""
    with patch.dict(os.environ, {"BOOL_VAR": env_value}):
        assert get_boolean_env("BOOL_VAR") is expected


def test_get_boolean_env_default_true():
    """Test scenario: Logic reversal when default value is True."""
    # When default=True, only explicit false values return False
    assert get_boolean_env("NON_EXISTENT", default=True) is True

    with patch.dict(os.environ, {"BOOL_VAR": "false"}):
        assert get_boolean_env("BOOL_VAR", default=True) is False
    with patch.dict(os.environ, {"BOOL_VAR": "0"}):
        assert get_boolean_env("BOOL_VAR", default=True) is False
    with patch.dict(os.environ, {"BOOL_VAR": "no"}):
        assert get_boolean_env("BOOL_VAR", default=True) is False
    with patch.dict(os.environ, {"BOOL_VAR": "off"}):
        assert get_boolean_env("BOOL_VAR", default=True) is False

    # Non-false values with default=True should return True
    with patch.dict(os.environ, {"BOOL_VAR": "anything"}):
        assert get_boolean_env("BOOL_VAR", default=True) is True


def test_get_boolean_env_default_false():
    """Test scenario: Standard logic when default value is False."""
    assert get_boolean_env("NON_EXISTENT", default=False) is False


# ===================== get_int_env Tests =====================


def test_get_int_env_valid_integer():
    """Test scenario: Valid integer string parsing."""
    with patch.dict(os.environ, {"INT_VAR": "123"}):
        assert get_int_env("INT_VAR") == 123


def test_get_int_env_negative_integer():
    """Test scenario: Negative integer parsing."""
    with patch.dict(os.environ, {"INT_VAR": "-456"}):
        assert get_int_env("INT_VAR") == -456


def test_get_int_env_zero():
    """Test scenario: Zero value parsing."""
    with patch.dict(os.environ, {"INT_VAR": "0"}):
        assert get_int_env("INT_VAR") == 0


def test_get_int_env_invalid_returns_default():
    """Test scenario: Invalid string falls back to default value."""
    with patch.dict(os.environ, {"INT_VAR": "invalid"}):
        assert get_int_env("INT_VAR", default=10) == 10


def test_get_int_env_float_string_returns_default():
    """Test scenario: Float string falls back to default value."""
    with patch.dict(os.environ, {"INT_VAR": "3.14"}):
        assert get_int_env("INT_VAR", default=5) == 5


def test_get_int_env_empty_returns_default():
    """Test scenario: Empty string falls back to default value."""
    with patch.dict(os.environ, {"INT_VAR": ""}):
        assert get_int_env("INT_VAR", default=7) == 7


def test_get_int_env_non_existent_returns_default():
    """Test scenario: Return default value when environment variable does not exist."""
    assert get_int_env("NON_EXISTENT_INT", default=5) == 5


# ===================== Path Constants Tests =====================


def test_path_constants_are_strings():
    """Test scenario: Path constants are all string types."""
    from config.settings import (
        ACTIVE_AUTH_DIR,
        APP_LOG_FILE_PATH,
        AUTH_PROFILES_DIR,
        LOG_DIR,
        SAVED_AUTH_DIR,
        UPLOAD_FILES_DIR,
    )

    assert isinstance(AUTH_PROFILES_DIR, str)
    assert isinstance(ACTIVE_AUTH_DIR, str)
    assert isinstance(SAVED_AUTH_DIR, str)
    assert isinstance(LOG_DIR, str)
    assert isinstance(APP_LOG_FILE_PATH, str)
    assert isinstance(UPLOAD_FILES_DIR, str)


def test_path_constants_contain_expected_dirs():
    """Test scenario: Path constants contain expected directory names."""
    from config.settings import (
        ACTIVE_AUTH_DIR,
        APP_LOG_FILE_PATH,
        AUTH_PROFILES_DIR,
        LOG_DIR,
        SAVED_AUTH_DIR,
        UPLOAD_FILES_DIR,
    )

    assert "auth_profiles" in AUTH_PROFILES_DIR
    assert "active" in ACTIVE_AUTH_DIR
    assert "saved" in SAVED_AUTH_DIR
    assert "logs" in LOG_DIR
    assert "app.log" in APP_LOG_FILE_PATH
    assert "upload_files" in UPLOAD_FILES_DIR


def test_path_relationship_active_under_profiles():
    """Test scenario: active directory should be under auth_profiles."""
    from config.settings import ACTIVE_AUTH_DIR, AUTH_PROFILES_DIR

    # ACTIVE_AUTH_DIR should be a subdirectory of AUTH_PROFILES_DIR
    assert AUTH_PROFILES_DIR in ACTIVE_AUTH_DIR


def test_path_relationship_saved_under_profiles():
    """Test scenario: saved directory should be under auth_profiles."""
    from config.settings import AUTH_PROFILES_DIR, SAVED_AUTH_DIR

    assert AUTH_PROFILES_DIR in SAVED_AUTH_DIR


# ===================== Module-level Constants Tests =====================


def test_module_constants_with_env_override():
    """Test scenario: Module-level constants can be overridden by environment variables."""
    original_module = sys.modules.get("config.settings")

    try:
        with (
            patch.dict(
                os.environ,
                {
                    "DEBUG_LOGS_ENABLED": "true",
                    "TRACE_LOGS_ENABLED": "1",
                    "JSON_LOGS": "yes",
                },
            ),
            patch("dotenv.load_dotenv"),
        ):
            if "config.settings" in sys.modules:
                del sys.modules["config.settings"]

            import config.settings as settings

            assert settings.DEBUG_LOGS_ENABLED is True
            assert settings.TRACE_LOGS_ENABLED is True
            assert settings.JSON_LOGS_ENABLED is True
    finally:
        if original_module is not None:
            sys.modules["config.settings"] = original_module
        elif "config.settings" in sys.modules:
            del sys.modules["config.settings"]


def test_log_rotation_config():
    """Test scenario: Log rotation configuration parsing."""
    original_module = sys.modules.get("config.settings")

    try:
        with (
            patch.dict(
                os.environ,
                {
                    "LOG_FILE_MAX_BYTES": "5242880",  # 5MB
                    "LOG_FILE_BACKUP_COUNT": "10",
                },
            ),
            patch("dotenv.load_dotenv"),
        ):
            if "config.settings" in sys.modules:
                del sys.modules["config.settings"]

            import config.settings as settings

            assert settings.LOG_FILE_MAX_BYTES == 5242880
            assert settings.LOG_FILE_BACKUP_COUNT == 10
    finally:
        if original_module is not None:
            sys.modules["config.settings"] = original_module
        elif "config.settings" in sys.modules:
            del sys.modules["config.settings"]
