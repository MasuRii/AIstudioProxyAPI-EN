import os
from unittest.mock import patch

from config.settings import (
    get_boolean_env,
    get_environment_variable,
    get_int_env,
)


def test_get_environment_variable():
    """Test getting environment variables."""
    with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
        assert get_environment_variable("TEST_VAR") == "test_value"

    assert get_environment_variable("NON_EXISTENT_VAR", "default") == "default"


def test_get_boolean_env():
    """Test getting boolean environment variables."""
    # Test true values
    with patch.dict(os.environ, {"BOOL_VAR": "true"}):
        assert get_boolean_env("BOOL_VAR") is True
    with patch.dict(os.environ, {"BOOL_VAR": "1"}):
        assert get_boolean_env("BOOL_VAR") is True
    with patch.dict(os.environ, {"BOOL_VAR": "yes"}):
        assert get_boolean_env("BOOL_VAR") is True
    with patch.dict(os.environ, {"BOOL_VAR": "on"}):
        assert get_boolean_env("BOOL_VAR") is True

    # Test false values
    with patch.dict(os.environ, {"BOOL_VAR": "false"}):
        assert get_boolean_env("BOOL_VAR") is False
    with patch.dict(os.environ, {"BOOL_VAR": "0"}):
        assert get_boolean_env("BOOL_VAR") is False
    with patch.dict(os.environ, {"BOOL_VAR": "no"}):
        assert get_boolean_env("BOOL_VAR") is False
    with patch.dict(os.environ, {"BOOL_VAR": "off"}):
        assert get_boolean_env("BOOL_VAR") is False

    # Test default values
    assert get_boolean_env("NON_EXISTENT_BOOL", default=True) is True
    assert get_boolean_env("NON_EXISTENT_BOOL", default=False) is False


def test_get_int_env():
    """Test getting integer environment variables."""
    with patch.dict(os.environ, {"INT_VAR": "123"}):
        assert get_int_env("INT_VAR") == 123

    with patch.dict(os.environ, {"INT_VAR": "invalid"}):
        assert get_int_env("INT_VAR", default=10) == 10

    assert get_int_env("NON_EXISTENT_INT", default=5) == 5
