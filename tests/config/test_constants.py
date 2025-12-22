"""
High-quality tests for config/constants.py - Constants configuration.

Focus: Test all environment variable parsing with edge cases.
Strategy: Use importlib to reload module with mocked environment variables.
"""

import os
import sys
from unittest.mock import patch

import pytest

# ===================== DEFAULT_STOP_SEQUENCES Tests =====================


def test_default_stop_sequences_invalid_json():
    """
    Test scenario: DEFAULT_STOP_SEQUENCES environment variable contains invalid JSON
    Expected: JSONDecodeError caught, falls back to empty list (lines 44-45)
    """
    original_module = sys.modules.get("config.constants")

    try:
        with patch.dict(os.environ, {"DEFAULT_STOP_SEQUENCES": "invalid json {["}):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.DEFAULT_STOP_SEQUENCES == ["User:"]
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


def test_default_stop_sequences_valid_json():
    """
    Test scenario: DEFAULT_STOP_SEQUENCES environment variable contains valid JSON
    Expected: Successfully parsed into a list (line 43)
    """
    original_module = sys.modules.get("config.constants")

    try:
        with patch.dict(os.environ, {"DEFAULT_STOP_SEQUENCES": '["stop1", "stop2"]'}):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.DEFAULT_STOP_SEQUENCES == ["stop1", "stop2"]
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


def test_default_stop_sequences_empty_default():
    """
    Test scenario: DEFAULT_STOP_SEQUENCES not configured
    Expected: Use empty list default value (line 43)
    """
    original_module = sys.modules.get("config.constants")

    try:
        env_overrides = {
            k: v for k, v in os.environ.items() if k != "DEFAULT_STOP_SEQUENCES"
        }
        with (
            patch.dict(os.environ, env_overrides, clear=True),
            patch("dotenv.load_dotenv"),
        ):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.DEFAULT_STOP_SEQUENCES == ["User:"]
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


# ===================== Boolean Flag Tests =====================


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("", False),
        ("invalid", False),
    ],
)
def test_enable_url_context_parsing(env_value: str, expected: bool):
    """
    Test scenario: ENABLE_URL_CONTEXT boolean value parsing
    Coverage: true/True/TRUE/1/yes -> True, others -> False
    """
    original_module = sys.modules.get("config.constants")

    try:
        with (
            patch.dict(os.environ, {"ENABLE_URL_CONTEXT": env_value}),
            patch("dotenv.load_dotenv"),
        ):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.ENABLE_URL_CONTEXT == expected
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
    ],
)
def test_enable_thinking_budget_parsing(env_value: str, expected: bool):
    """
    Test scenario: ENABLE_THINKING_BUDGET boolean value parsing
    """
    original_module = sys.modules.get("config.constants")

    try:
        with (
            patch.dict(os.environ, {"ENABLE_THINKING_BUDGET": env_value}),
            patch("dotenv.load_dotenv"),
        ):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.ENABLE_THINKING_BUDGET == expected
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
    ],
)
def test_enable_google_search_parsing(env_value: str, expected: bool):
    """
    Test scenario: ENABLE_GOOGLE_SEARCH boolean value parsing
    """
    original_module = sys.modules.get("config.constants")

    try:
        with (
            patch.dict(os.environ, {"ENABLE_GOOGLE_SEARCH": env_value}),
            patch("dotenv.load_dotenv"),
        ):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.ENABLE_GOOGLE_SEARCH == expected
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


# ===================== Thinking Level Tests =====================


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("high", "high"),
        ("HIGH", "high"),
        ("low", "low"),
        ("LOW", "low"),
        ("medium", "high"),  # Invalid value falls back to "high"
        ("invalid", "high"),  # Invalid value falls back to "high"
        ("", "high"),  # Empty defaults to "high"
    ],
)
def test_thinking_level_pro_validation(env_value: str, expected: str):
    """
    Test scenario: DEFAULT_THINKING_LEVEL_PRO validation (only supports high/low)
    Invalid values fall back to "high"
    """
    original_module = sys.modules.get("config.constants")

    try:
        with (
            patch.dict(os.environ, {"DEFAULT_THINKING_LEVEL_PRO": env_value}),
            patch("dotenv.load_dotenv"),
        ):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.DEFAULT_THINKING_LEVEL_PRO == expected
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("high", "high"),
        ("HIGH", "high"),
        ("medium", "medium"),
        ("MEDIUM", "medium"),
        ("low", "low"),
        ("minimal", "minimal"),
        ("MINIMAL", "minimal"),
        ("invalid", "high"),  # Invalid value falls back to "high"
        ("", "high"),  # Empty defaults to "high"
    ],
)
def test_thinking_level_flash_validation(env_value: str, expected: str):
    """
    Test scenario: DEFAULT_THINKING_LEVEL_FLASH validation (supports high/medium/low/minimal)
    Invalid values fall back to "high"
    """
    original_module = sys.modules.get("config.constants")

    try:
        with (
            patch.dict(os.environ, {"DEFAULT_THINKING_LEVEL_FLASH": env_value}),
            patch("dotenv.load_dotenv"),
        ):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.DEFAULT_THINKING_LEVEL_FLASH == expected
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


# ===================== Numeric Defaults Tests =====================


def test_numeric_defaults_parsing():
    """
    Test scenario: Numeric type default values parsing
    Verify float/int conversion is correct
    """
    original_module = sys.modules.get("config.constants")

    try:
        with (
            patch.dict(
                os.environ,
                {
                    "DEFAULT_TEMPERATURE": "0.7",
                    "DEFAULT_MAX_OUTPUT_TOKENS": "4096",
                    "DEFAULT_TOP_P": "0.9",
                    "DEFAULT_THINKING_BUDGET": "16384",
                },
            ),
            patch("dotenv.load_dotenv"),
        ):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.DEFAULT_TEMPERATURE == 0.7
            assert constants.DEFAULT_MAX_OUTPUT_TOKENS == 4096
            assert constants.DEFAULT_TOP_P == 0.9
            assert constants.DEFAULT_THINKING_BUDGET == 16384
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


def test_stream_timeout_log_state_config():
    """
    Test scenario: STREAM_TIMEOUT_LOG_STATE configuration parsing
    Verify numbers in nested dictionary correctly parsed
    """
    original_module = sys.modules.get("config.constants")

    try:
        with (
            patch.dict(
                os.environ,
                {
                    "STREAM_MAX_INITIAL_ERRORS": "5",
                    "STREAM_WARNING_INTERVAL_AFTER_SUPPRESS": "120.0",
                    "STREAM_SUPPRESS_DURATION_AFTER_INITIAL_BURST": "600.0",
                },
            ),
            patch("dotenv.load_dotenv"),
        ):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.STREAM_TIMEOUT_LOG_STATE["max_initial_errors"] == 5
            assert (
                constants.STREAM_TIMEOUT_LOG_STATE["warning_interval_after_suppress"]
                == 120.0
            )
            assert (
                constants.STREAM_TIMEOUT_LOG_STATE[
                    "suppress_duration_after_initial_burst"
                ]
                == 600.0
            )
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


# ===================== String Constants Tests =====================


def test_string_constants_custom_values():
    """
    Test scenario: String constant custom values
    """
    original_module = sys.modules.get("config.constants")

    try:
        with (
            patch.dict(
                os.environ,
                {
                    "MODEL_NAME": "Custom-Model-Name",
                    "CHAT_COMPLETION_ID_PREFIX": "custom-",
                    "USER_INPUT_START_MARKER_SERVER": "__START__",
                    "USER_INPUT_END_MARKER_SERVER": "__END__",
                },
            ),
            patch("dotenv.load_dotenv"),
        ):
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            import config.constants as constants

            assert constants.MODEL_NAME == "Custom-Model-Name"
            assert constants.CHAT_COMPLETION_ID_PREFIX == "custom-"
            assert constants.USER_INPUT_START_MARKER_SERVER == "__START__"
            assert constants.USER_INPUT_END_MARKER_SERVER == "__END__"
    finally:
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]
