import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_utils.initialization import auth


@pytest.fixture
def mock_context():
    context = AsyncMock()
    context.storage_state = AsyncMock()
    return context


@pytest.fixture
def mock_loop():
    loop = MagicMock()
    future = asyncio.Future()
    future.set_result("test_result")
    loop.run_in_executor.return_value = future
    return loop


# ==================== _save_auth_state Tests ====================


@pytest.mark.asyncio
async def test_save_auth_state_success(mock_context, tmp_path):
    """Test _save_auth_state saves auth correctly with auto-generated filename."""
    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth._save_auth_state(mock_context, "test_auth")

        mock_context.storage_state.assert_called_once()
        kwargs = mock_context.storage_state.call_args[1]
        assert kwargs["path"].endswith("test_auth.json")
        assert str(tmp_path) in kwargs["path"]


@pytest.mark.asyncio
async def test_save_auth_state_adds_json_extension(mock_context, tmp_path):
    """Test _save_auth_state adds .json extension if missing."""
    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth._save_auth_state(mock_context, "my_profile")

        kwargs = mock_context.storage_state.call_args[1]
        assert kwargs["path"].endswith("my_profile.json")


@pytest.mark.asyncio
async def test_save_auth_state_preserves_json_extension(mock_context, tmp_path):
    """Test _save_auth_state preserves .json if already present."""
    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth._save_auth_state(mock_context, "already.json")

        kwargs = mock_context.storage_state.call_args[1]
        assert kwargs["path"].endswith("already.json")
        assert not kwargs["path"].endswith("already.json.json")


@pytest.mark.asyncio
async def test_save_auth_state_exception(mock_context, tmp_path):
    """Test _save_auth_state catches and logs exceptions."""
    mock_context.storage_state.side_effect = Exception("Storage failed")

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger") as mock_logger,
    ):
        # Should not raise
        await auth._save_auth_state(mock_context, "test_auth")

        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_save_auth_state_cancelled_error(mock_context, tmp_path):
    """Test _save_auth_state re-raises CancelledError."""
    mock_context.storage_state.side_effect = asyncio.CancelledError()

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
    ):
        with pytest.raises(asyncio.CancelledError):
            await auth._save_auth_state(mock_context, "test_auth")


# ==================== wait_for_model_list_and_handle_auth_save Tests ====================


@pytest.mark.asyncio
async def test_wait_for_model_list_success(mock_context, mock_loop, tmp_path):
    """Test wait_for_model_list calls _save_auth_state on success."""
    import server

    server.model_list_fetch_event.set()

    with (
        patch("browser_utils.initialization.auth._save_auth_state") as mock_save,
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth.wait_for_model_list_and_handle_auth_save(
            mock_context, "normal", mock_loop
        )

        mock_save.assert_called_once()
        # Should be called with auto-generated filename
        args = mock_save.call_args[0]
        assert args[0] == mock_context
        assert args[1].startswith("auth_auto_")


@pytest.mark.asyncio
async def test_wait_for_model_list_timeout(mock_context, mock_loop):
    """Test wait_for_model_list handles timeout and still saves."""
    import server

    server.model_list_fetch_event.clear()

    original_wait_for = asyncio.wait_for

    async def side_effect(coro, timeout):
        if timeout == 30.0:
            raise asyncio.TimeoutError()
        return await original_wait_for(coro, timeout)

    with (
        patch("asyncio.wait_for", side_effect=side_effect),
        patch("browser_utils.initialization.auth._save_auth_state") as mock_save,
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth.wait_for_model_list_and_handle_auth_save(
            mock_context, "normal", mock_loop
        )

        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_model_list_with_env_filename(mock_context, mock_loop):
    """Test wait_for_model_list uses SAVE_AUTH_FILENAME env var."""
    import server

    server.model_list_fetch_event.set()

    with (
        patch.dict(os.environ, {"SAVE_AUTH_FILENAME": "env_auth"}),
        patch("browser_utils.initialization.auth._save_auth_state") as mock_save,
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth.wait_for_model_list_and_handle_auth_save(
            mock_context, "normal", mock_loop
        )

        mock_save.assert_called_with(mock_context, "env_auth")
