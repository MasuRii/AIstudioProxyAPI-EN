from unittest.mock import mock_open, patch

from api_utils.auth_utils import (
    API_KEYS,
    KEY_FILE_PATH,
    initialize_keys,
    load_api_keys,
    verify_api_key,
)


def test_load_api_keys():
    """Test loading API keys from file."""
    mock_content = "key1\nkey2\n\nkey3"
    with patch("builtins.open", mock_open(read_data=mock_content)):
        with patch("os.path.exists", return_value=True):
            load_api_keys()
            assert "key1" in API_KEYS
            assert "key2" in API_KEYS
            assert "key3" in API_KEYS
            assert len(API_KEYS) == 3


def test_initialize_keys_creates_file():
    """Test initialize_keys creates file if not exists."""
    with patch("os.path.exists", return_value=False):
        with patch("builtins.open", mock_open()) as mock_file:
            initialize_keys()
            mock_file.assert_called_with(KEY_FILE_PATH, "w")


def test_verify_api_key():
    """Test API key verification."""
    # Case 1: No keys configured (should allow all)
    API_KEYS.clear()
    assert verify_api_key("any_key") is True

    # Case 2: Keys configured
    API_KEYS.add("valid_key")
    assert verify_api_key("valid_key") is True
    assert verify_api_key("invalid_key") is False
