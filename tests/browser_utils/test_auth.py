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
    # Ensure run_in_executor returns a Future
    future = asyncio.Future()
    future.set_result("test_result")
    loop.run_in_executor.return_value = future
    return loop


@pytest.mark.asyncio
async def test_handle_auth_file_save_auto(mock_context, tmp_path):
    # Mock SAVED_AUTH_DIR to a temp dir
    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth._handle_auth_file_save_auto(mock_context)

        mock_context.storage_state.assert_called_once()
        args, kwargs = mock_context.storage_state.call_args
        assert str(tmp_path) in kwargs["path"]
        assert "auth_auto_" in kwargs["path"]


@pytest.mark.asyncio
async def test_handle_auth_file_save_with_filename(mock_context, tmp_path):
    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth._handle_auth_file_save_with_filename(mock_context, "my_auth")

        mock_context.storage_state.assert_called_once()
        kwargs = mock_context.storage_state.call_args[1]
        assert kwargs["path"].endswith("my_auth.json")


@pytest.mark.asyncio
async def test_handle_auth_file_save_manual_success(mock_context, mock_loop, tmp_path):
    future = asyncio.Future()
    future.set_result("custom_name")
    mock_loop.run_in_executor.return_value = future

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth._handle_auth_file_save(mock_context, mock_loop)

        mock_context.storage_state.assert_called_once()
        kwargs = mock_context.storage_state.call_args[1]
        assert kwargs["path"].endswith("custom_name.json")


@pytest.mark.asyncio
async def test_handle_auth_file_save_manual_cancel(mock_context, mock_loop, tmp_path):
    future = asyncio.Future()
    future.set_result("cancel")
    mock_loop.run_in_executor.return_value = future

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
    ):
        await auth._handle_auth_file_save(mock_context, mock_loop)

        mock_context.storage_state.assert_not_called()


@pytest.mark.asyncio
async def test_wait_for_model_list_success(mock_context, mock_loop):
    import server

    server.model_list_fetch_event.set()

    with (
        patch(
            "browser_utils.initialization.auth._interactive_auth_save"
        ) as mock_interactive,
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth.wait_for_model_list_and_handle_auth_save(
            mock_context, "normal", mock_loop
        )

        mock_interactive.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_model_list_timeout(mock_context, mock_loop):
    import server

    server.model_list_fetch_event.clear()

    # We can't easily patch asyncio.wait_for only for the first call because it's used internally
    # But wait_for_model_list calls wait_for(event.wait(), timeout=30.0)

    # We can use a side effect for wait_for that checks the coroutine
    original_wait_for = asyncio.wait_for

    async def side_effect(coro, timeout):
        # Identify if this is the event wait
        # This is tricky. simpler to just let it timeout if we set timeout to very small?
        # No, the code hardcodes timeout=30.0

        # We can patch server.model_list_fetch_event.wait to raise TimeoutError?
        # No, wait() just waits. wait_for raises TimeoutError.

        # Let's mock server.model_list_fetch_event.wait to be an AsyncMock that sleeps forever?
        # Then patch asyncio.wait_for to raise TimeoutError immediately if timeout=30.0
        if timeout == 30.0:
            raise asyncio.TimeoutError()
        return await original_wait_for(coro, timeout)

    with (
        patch("asyncio.wait_for", side_effect=side_effect),
        patch(
            "browser_utils.initialization.auth._interactive_auth_save"
        ) as mock_interactive,
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth.wait_for_model_list_and_handle_auth_save(
            mock_context, "normal", mock_loop
        )

        mock_interactive.assert_called_once()


@pytest.mark.asyncio
async def test_wait_for_model_list_with_env_filename(mock_context, mock_loop):
    import server

    server.model_list_fetch_event.set()

    with (
        patch.dict(os.environ, {"SAVE_AUTH_FILENAME": "env_auth"}),
        patch(
            "browser_utils.initialization.auth._handle_auth_file_save_with_filename"
        ) as mock_save_file,
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth.wait_for_model_list_and_handle_auth_save(
            mock_context, "normal", mock_loop
        )

        mock_save_file.assert_called_with(mock_context, "env_auth")


@pytest.mark.asyncio
async def test_interactive_auth_save_auto_confirm(mock_context, mock_loop):
    with (
        patch("browser_utils.initialization.auth.AUTO_CONFIRM_LOGIN", True),
        patch(
            "browser_utils.initialization.auth._handle_auth_file_save_auto"
        ) as mock_save_auto,
        patch("browser_utils.initialization.auth.print"),
    ):
        await auth._interactive_auth_save(mock_context, "normal", mock_loop)

        mock_save_auto.assert_called_once()


@pytest.mark.asyncio
async def test_interactive_auth_save_manual_yes(mock_context, mock_loop):
    # Mock input to return 'y'
    future = asyncio.Future()
    future.set_result("y")
    mock_loop.run_in_executor.return_value = future

    with (
        patch("browser_utils.initialization.auth.AUTO_CONFIRM_LOGIN", False),
        patch(
            "browser_utils.initialization.auth._handle_auth_file_save"
        ) as mock_save_manual,
        patch("browser_utils.initialization.auth.print"),
    ):
        await auth._interactive_auth_save(mock_context, "normal", mock_loop)

        mock_save_manual.assert_called_once()


@pytest.mark.asyncio
async def test_interactive_auth_save_manual_no(mock_context, mock_loop):
    # Mock input to return 'n'
    future = asyncio.Future()
    future.set_result("n")
    mock_loop.run_in_executor.return_value = future

    with (
        patch("browser_utils.initialization.auth.AUTO_CONFIRM_LOGIN", False),
        patch(
            "browser_utils.initialization.auth._handle_auth_file_save"
        ) as mock_save_manual,
        patch("browser_utils.initialization.auth.print"),
    ):
        await auth._interactive_auth_save(mock_context, "normal", mock_loop)

        mock_save_manual.assert_not_called()


# ==================== Additional Tests for Coverage Improvement ====================


@pytest.mark.asyncio
async def test_interactive_auth_save_auto_save_debug_mode(mock_context, mock_loop):
    """Test AUTO_SAVE_AUTH + debug mode auto-saves (lines 65-66)."""
    with (
        patch("browser_utils.initialization.auth.AUTO_CONFIRM_LOGIN", False),
        patch("browser_utils.initialization.auth.AUTO_SAVE_AUTH", True),
        patch(
            "browser_utils.initialization.auth._handle_auth_file_save"
        ) as mock_save_manual,
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth._interactive_auth_save(mock_context, "debug", mock_loop)

        # Should auto-select 'y' and call manual save
        mock_save_manual.assert_called_once()


@pytest.mark.asyncio
async def test_interactive_auth_save_input_timeout(mock_context, mock_loop):
    """Test input timeout defaults to 'n' (lines 75-80)."""
    # Simulate timeout when waiting for user input
    future = asyncio.Future()
    future.set_exception(asyncio.TimeoutError())
    mock_loop.run_in_executor.return_value = future

    with (
        patch("browser_utils.initialization.auth.AUTO_CONFIRM_LOGIN", False),
        patch("browser_utils.initialization.auth.AUTO_SAVE_AUTH", False),
        patch(
            "browser_utils.initialization.auth._handle_auth_file_save"
        ) as mock_save_manual,
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth._interactive_auth_save(mock_context, "normal", mock_loop)

        # Should default to 'n' and not save
        mock_save_manual.assert_not_called()


@pytest.mark.asyncio
async def test_handle_auth_file_save_filename_timeout(
    mock_context, mock_loop, tmp_path
):
    """Test filename input timeout uses default filename (lines 106-111)."""
    # Simulate timeout when waiting for filename input
    future = asyncio.Future()
    future.set_exception(asyncio.TimeoutError())
    mock_loop.run_in_executor.return_value = future

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger"),
    ):
        await auth._handle_auth_file_save(mock_context, mock_loop)

        # Should use default filename
        mock_context.storage_state.assert_called_once()
        kwargs = mock_context.storage_state.call_args[1]
        assert "auth_state_" in kwargs["path"]


@pytest.mark.asyncio
async def test_handle_auth_file_save_storage_exception(
    mock_context, mock_loop, tmp_path
):
    """Test exception handling in manual save (lines 131-133)."""
    # Simulate successful filename input
    future = asyncio.Future()
    future.set_result("test_auth")
    mock_loop.run_in_executor.return_value = future

    # Make storage_state raise an exception
    mock_context.storage_state.side_effect = Exception("Storage failed")

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger") as mock_logger,
    ):
        # Should not raise, just log error
        await auth._handle_auth_file_save(mock_context, mock_loop)

        # Verify error was logged
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_handle_auth_file_save_cancelled_error(mock_context, mock_loop, tmp_path):
    """Test CancelledError is re-raised in manual save (lines 129-130)."""
    # Simulate successful filename input
    future = asyncio.Future()
    future.set_result("test_auth")
    mock_loop.run_in_executor.return_value = future

    # Make storage_state raise CancelledError
    mock_context.storage_state.side_effect = asyncio.CancelledError()

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
    ):
        # Should re-raise CancelledError
        with pytest.raises(asyncio.CancelledError):
            await auth._handle_auth_file_save(mock_context, mock_loop)


@pytest.mark.asyncio
async def test_handle_auth_file_save_with_filename_exception(mock_context, tmp_path):
    """Test exception handling in save_with_filename (lines 153-155)."""
    # Make storage_state raise an exception
    mock_context.storage_state.side_effect = Exception("Save failed")

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger") as mock_logger,
    ):
        # Should not raise, just log error
        await auth._handle_auth_file_save_with_filename(mock_context, "test_file")

        # Verify error was logged
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_handle_auth_file_save_with_filename_cancelled(mock_context, tmp_path):
    """Test CancelledError is re-raised in save_with_filename (lines 151-152)."""
    # Make storage_state raise CancelledError
    mock_context.storage_state.side_effect = asyncio.CancelledError()

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
    ):
        # Should re-raise CancelledError
        with pytest.raises(asyncio.CancelledError):
            await auth._handle_auth_file_save_with_filename(mock_context, "test_file")


@pytest.mark.asyncio
async def test_handle_auth_file_save_auto_exception(mock_context, tmp_path):
    """Test exception handling in auto save (lines 173-175)."""
    # Make storage_state raise an exception
    mock_context.storage_state.side_effect = Exception("Auto save failed")

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
        patch("browser_utils.initialization.auth.logger") as mock_logger,
    ):
        # Should not raise, just log error
        await auth._handle_auth_file_save_auto(mock_context)

        # Verify error was logged
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_handle_auth_file_save_auto_cancelled(mock_context, tmp_path):
    """Test CancelledError is re-raised in auto save (lines 171-172)."""
    # Make storage_state raise CancelledError
    mock_context.storage_state.side_effect = asyncio.CancelledError()

    with (
        patch("browser_utils.initialization.auth.SAVED_AUTH_DIR", str(tmp_path)),
        patch("browser_utils.initialization.auth.print"),
    ):
        # Should re-raise CancelledError
        with pytest.raises(asyncio.CancelledError):
            await auth._handle_auth_file_save_auto(mock_context)
