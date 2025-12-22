"""
High-quality tests for api_utils/routers/api_keys.py - API key management endpoints.

Focus: Test all 4 endpoints (get, add, test, delete) with success and error paths.
Strategy: Mock auth_utils module and file operations, test validation and exception handling.
"""

from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi import HTTPException

from api_utils.routers.api_keys import (
    ApiKeyRequest,
    ApiKeyTestRequest,
    add_api_key,
    delete_api_key,
    get_api_keys,
)
from api_utils.routers.api_keys import (
    test_api_key as api_key_test_endpoint,  # Alias doesn't start with 'test_'
)


@pytest.fixture
def mock_auth_utils():
    """Mock auth_utils module with API_KEYS set and KEY_FILE_PATH."""
    with patch("api_utils.auth_utils") as mock_auth:
        mock_auth.API_KEYS = set()
        mock_auth.KEY_FILE_PATH = "/fake/path/key.txt"
        mock_auth.initialize_keys = MagicMock()
        mock_auth.verify_api_key = MagicMock()
        yield mock_auth


@pytest.fixture
def mock_logger():
    """Mock logger instance."""
    return MagicMock()


@pytest.mark.asyncio
async def test_get_api_keys_success_with_keys(mock_auth_utils, mock_logger):
    """
    Test scenario: Successfully get API key list (with keys)
    Expected: Return JSON response containing all keys (lines 18-26)
    """
    # Setup: API_KEYS has 3 keys
    mock_auth_utils.API_KEYS = {"key1", "key2", "key3"}

    response = await get_api_keys(logger=mock_logger)

    # Verify: initialize_keys called (line 22)
    mock_auth_utils.initialize_keys.assert_called_once()

    # Verify: Response structure (lines 23-26)
    assert response.status_code == 200
    content = bytes(response.body).decode()
    assert '"success":true' in content.lower()
    assert '"total_count":3' in content.lower()


@pytest.mark.asyncio
async def test_get_api_keys_success_empty(mock_auth_utils, mock_logger):
    """
    Test scenario: Successfully get API key list (no keys)
    Expected: Return empty list
    """
    mock_auth_utils.API_KEYS = set()

    response = await get_api_keys(logger=mock_logger)

    # Verify: Empty keys list
    assert response.status_code == 200
    content = bytes(response.body).decode()
    assert '"total_count":0' in content.lower()


@pytest.mark.asyncio
async def test_get_api_keys_exception_handling(mock_auth_utils, mock_logger):
    """
    Test scenario: initialize_keys throws exception
    Expected: Throw HTTPException 500 (lines 27-29)
    """
    mock_auth_utils.initialize_keys.side_effect = RuntimeError("File permission error")

    with pytest.raises(HTTPException) as exc_info:
        await get_api_keys(logger=mock_logger)

    # Verify: HTTPException 500
    assert exc_info.value.status_code == 500
    assert "File permission error" in exc_info.value.detail

    # Verify: logger.error called (line 28)
    assert mock_logger.error.call_count == 1
    assert "Failed to get API key list" in mock_logger.error.call_args[0][0]


@pytest.mark.asyncio
async def test_add_api_key_success(mock_auth_utils, mock_logger):
    """
    Test scenario: Successfully add new API key
    Expected: Write to file and return success response (lines 35-61)
    """
    mock_auth_utils.API_KEYS = set()  # Initially empty
    request = ApiKeyRequest(key="valid-key-123456")

    # Mock file operations
    mock_file = mock_open(read_data="")
    with patch("builtins.open", mock_file):
        response = await add_api_key(request=request, logger=mock_logger)

    # Verify: initialize_keys called twice (lines 41, 53)
    assert mock_auth_utils.initialize_keys.call_count == 2

    # Verify: File write (lines 47-51)
    mock_file.assert_called()
    handle = mock_file()
    # Key written to file
    written_data = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "valid-key-123456" in written_data

    # Verify: logger.info called (line 54)
    assert mock_logger.info.call_count == 1
    assert "API key added" in mock_logger.info.call_args[0][0]

    # Verify: Response (lines 55-61)
    assert response.status_code == 200
    content = bytes(response.body).decode()
    assert '"success":true' in content.lower()
    assert '"message":"api key added successfully"' in content.lower()


@pytest.mark.asyncio
async def test_add_api_key_invalid_empty(mock_logger):
    """
    Test scenario: Add empty key
    Expected: Throw HTTPException 400 (lines 37-39)
    """
    request = ApiKeyRequest(key="   ")  # Whitespace only

    with pytest.raises(HTTPException) as exc_info:
        await add_api_key(request=request, logger=mock_logger)

    # Verify: HTTPException 400 (line 39)
    assert exc_info.value.status_code == 400
    assert "Invalid API key format" in exc_info.value.detail


@pytest.mark.asyncio
async def test_add_api_key_invalid_too_short(mock_logger):
    """
    Test scenario: Add too short key (< 8 characters)
    Expected: Throw HTTPException 400 (lines 38-39)
    """
    request = ApiKeyRequest(key="short")  # Only 5 characters

    with pytest.raises(HTTPException) as exc_info:
        await add_api_key(request=request, logger=mock_logger)

    # Verify: HTTPException 400
    assert exc_info.value.status_code == 400
    assert "Invalid API key format" in exc_info.value.detail


@pytest.mark.asyncio
async def test_add_api_key_duplicate(mock_auth_utils, mock_logger):
    """
    Test scenario: Add existing key
    Expected: Throw HTTPException 400 (lines 42-43)
    """
    mock_auth_utils.API_KEYS = {"existing-key-123"}
    request = ApiKeyRequest(key="existing-key-123")

    with pytest.raises(HTTPException) as exc_info:
        await add_api_key(request=request, logger=mock_logger)

    # Verify: HTTPException 400 (line 43)
    assert exc_info.value.status_code == 400
    assert "API key already exists" in exc_info.value.detail


@pytest.mark.asyncio
async def test_add_api_key_file_exception(mock_auth_utils, mock_logger):
    """
    Test scenario: File write failed
    Expected: Throw HTTPException 500 (lines 62-64)
    """
    mock_auth_utils.API_KEYS = set()
    request = ApiKeyRequest(key="valid-key-123456")

    # Mock file open to raise exception
    with patch("builtins.open", side_effect=IOError("Disk full")):
        with pytest.raises(HTTPException) as exc_info:
            await add_api_key(request=request, logger=mock_logger)

    # Verify: HTTPException 500 (line 64)
    assert exc_info.value.status_code == 500
    assert "Disk full" in exc_info.value.detail

    # Verify: logger.error called (line 63)
    assert mock_logger.error.call_count == 1
    assert "Failed to add API key" in mock_logger.error.call_args[0][0]


@pytest.mark.asyncio
async def test_add_api_key_appends_newline_when_file_has_content(
    mock_auth_utils, mock_logger
):
    """
    Test scenario: File already has content, append newline when adding key
    Expected: Write newline then write key (lines 48-51)
    """
    mock_auth_utils.API_KEYS = set()
    request = ApiKeyRequest(key="new-key-987654")

    # Mock file with existing content
    mock_file = mock_open(read_data="existing-key\n")
    with patch("builtins.open", mock_file):
        await add_api_key(request=request, logger=mock_logger)

    # Verify: Newline written before key (line 50)
    handle = mock_file()
    write_calls = [call.args[0] for call in handle.write.call_args_list]
    # Should have both newline and key
    assert any("\n" in call for call in write_calls)
    assert any("new-key-987654" in call for call in write_calls)


@pytest.mark.asyncio
async def test_test_api_key_valid(mock_auth_utils, mock_logger):
    """
    Test scenario: Test valid API key
    Expected: Return valid=True (lines 70-87)
    """
    request = ApiKeyTestRequest(key="valid-key-123")
    mock_auth_utils.verify_api_key.return_value = True

    response = await api_key_test_endpoint(request=request, logger=mock_logger)

    # Verify: verify_api_key called (line 77)
    mock_auth_utils.verify_api_key.assert_called_once_with("valid-key-123")

    # Verify: logger.info called (lines 78-80)
    assert mock_logger.info.call_count == 1
    log_msg = mock_logger.info.call_args[0][0]
    assert "API key test" in log_msg
    assert "Valid" in log_msg

    # Verify: Response (lines 81-87)
    assert response.status_code == 200
    content = bytes(response.body).decode()
    assert '"valid":true' in content.lower()
    assert '"message":"key valid"' in content.lower()


@pytest.mark.asyncio
async def test_test_api_key_invalid(mock_auth_utils, mock_logger):
    """
    Test scenario: Test invalid API key
    Expected: Return valid=False
    """
    request = ApiKeyTestRequest(key="invalid-key-999")
    mock_auth_utils.verify_api_key.return_value = False

    response = await api_key_test_endpoint(request=request, logger=mock_logger)

    # Verify: verify_api_key called
    mock_auth_utils.verify_api_key.assert_called_once_with("invalid-key-999")

    # Verify: Response
    assert response.status_code == 200
    content = bytes(response.body).decode()
    assert '"valid":false' in content.lower()
    assert '"message":"key invalid or non-existent"' in content.lower()


@pytest.mark.asyncio
async def test_test_api_key_empty_validation(mock_logger):
    """
    Test scenario: Test empty key
    Expected: Throw HTTPException 400 (lines 73-74)
    """
    request = ApiKeyTestRequest(key="   ")  # Whitespace only

    with pytest.raises(HTTPException) as exc_info:
        await api_key_test_endpoint(request=request, logger=mock_logger)

    # Verify: HTTPException 400
    assert exc_info.value.status_code == 400
    assert "API key cannot be empty" in exc_info.value.detail


@pytest.mark.asyncio
async def test_delete_api_key_success(mock_auth_utils, mock_logger):
    """
    Test scenario: Successfully delete API key
    Expected: Delete key from file and return success response (lines 93-119)
    """
    mock_auth_utils.API_KEYS = {"key-to-delete", "key-to-keep"}
    request = ApiKeyRequest(key="key-to-delete")

    # Mock file operations
    mock_file = mock_open(read_data="key-to-delete\nkey-to-keep\n")
    with patch("builtins.open", mock_file):
        response = await delete_api_key(request=request, logger=mock_logger)

    # Verify: initialize_keys called twice (lines 99, 111)
    assert mock_auth_utils.initialize_keys.call_count == 2

    # Verify: File read and write (lines 105-109)
    assert mock_file.call_count == 2  # Once for read, once for write

    # Verify: logger.info called (line 112)
    assert mock_logger.info.call_count == 1
    assert "API key deleted" in mock_logger.info.call_args[0][0]

    # Verify: Response (lines 113-119)
    assert response.status_code == 200
    content = bytes(response.body).decode()
    assert '"success":true' in content.lower()
    assert '"message":"api key deleted successfully"' in content.lower()


@pytest.mark.asyncio
async def test_delete_api_key_empty_validation(mock_logger):
    """
    Test scenario: Delete empty key
    Expected: Throw HTTPException 400 (lines 96-97)
    """
    request = ApiKeyRequest(key="  ")  # Whitespace only

    with pytest.raises(HTTPException) as exc_info:
        await delete_api_key(request=request, logger=mock_logger)

    # Verify: HTTPException 400
    assert exc_info.value.status_code == 400
    assert "API key cannot be empty" in exc_info.value.detail


@pytest.mark.asyncio
async def test_delete_api_key_not_found(mock_auth_utils, mock_logger):
    """
    Test scenario: Delete non-existent key
    Expected: Throw HTTPException 404 (lines 100-101)
    """
    mock_auth_utils.API_KEYS = {"existing-key"}
    request = ApiKeyRequest(key="non-existent-key")

    with pytest.raises(HTTPException) as exc_info:
        await delete_api_key(request=request, logger=mock_logger)

    # Verify: HTTPException 404 (line 101)
    assert exc_info.value.status_code == 404
    assert "API key does not exist" in exc_info.value.detail


@pytest.mark.asyncio
async def test_delete_api_key_file_exception(mock_auth_utils, mock_logger):
    """
    Test scenario: File operation failed
    Expected: Throw HTTPException 500 (lines 120-122)
    """
    mock_auth_utils.API_KEYS = {"key-to-delete"}
    request = ApiKeyRequest(key="key-to-delete")

    # Mock file open to raise exception
    with patch("builtins.open", side_effect=IOError("Permission denied")):
        with pytest.raises(HTTPException) as exc_info:
            await delete_api_key(request=request, logger=mock_logger)

    # Verify: HTTPException 500 (line 122)
    assert exc_info.value.status_code == 500
    assert "Permission denied" in exc_info.value.detail

    # Verify: logger.error called (line 121)
    assert mock_logger.error.call_count == 1
    assert "Failed to delete API key" in mock_logger.error.call_args[0][0]
