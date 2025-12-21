import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from playwright.async_api import Error as PlaywrightAsyncError

from browser_utils.initialization import (
    _close_page_logic,
    _initialize_page_logic,
    enable_temporary_chat_mode,
    signal_camoufox_shutdown,
)

# --- Existing Tests (Preserved) ---


@pytest.mark.asyncio
async def test_initialize_page_logic_success(
    mock_browser, mock_browser_context, mock_page, mock_env, mock_expect
):
    # Mock server module
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        import server

        setattr(server, "PLAYWRIGHT_PROXY_SETTINGS", None)

        # Mock page finding logic
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.is_closed.return_value = False
        mock_browser_context.pages = [mock_page]

        # Mock locators for verification
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        page, ready = await _initialize_page_logic(mock_browser)

        assert page == mock_page
        assert ready is True
        mock_browser.new_context.assert_called()


@pytest.mark.asyncio
async def test_initialize_page_logic_new_page(
    mock_browser, mock_browser_context, mock_page, mock_env, mock_expect
):
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        import server

        setattr(server, "PLAYWRIGHT_PROXY_SETTINGS", None)

        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"

        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        page, ready = await _initialize_page_logic(mock_browser)

        assert page == mock_page
        assert ready is True
        mock_page.goto.assert_called()


@pytest.mark.asyncio
async def test_close_page_logic_success():
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)

    from api_utils.server_state import state

    original_page = state.page_instance
    original_ready = state.is_page_ready

    try:
        state.page_instance = mock_page
        state.is_page_ready = True

        await _close_page_logic()

        mock_page.close.assert_called()
        assert state.page_instance is None
        assert state.is_page_ready is False
    finally:
        state.page_instance = original_page
        state.is_page_ready = original_ready


@pytest.mark.asyncio
async def test_close_page_logic_already_closed():
    from api_utils.server_state import state

    original_page = state.page_instance

    try:
        mock_page = AsyncMock()
        mock_page.is_closed.return_value = True
        state.page_instance = mock_page

        await _close_page_logic()

        mock_page.close.assert_not_called()
        assert state.page_instance is None
    finally:
        state.page_instance = original_page


@pytest.mark.asyncio
async def test_initialize_page_logic_headless_auth_missing(mock_browser, mock_env):
    with (
        patch.dict(
            "os.environ", {"LAUNCH_MODE": "headless", "ACTIVE_AUTH_JSON_PATH": ""}
        ),
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        with pytest.raises(RuntimeError) as exc:
            await _initialize_page_logic(mock_browser)
        assert "ACTIVE_AUTH_JSON_PATH" in str(exc.value)


@pytest.mark.asyncio
async def test_initialize_page_logic_proxy_settings(
    mock_browser, mock_browser_context, mock_page, mock_env, mock_expect
):
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        import server

        setattr(server, "PLAYWRIGHT_PROXY_SETTINGS", {"server": "http://proxy:8080"})

        mock_browser_context.pages = [mock_page]
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.is_closed.return_value = False

        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Gemini 1.5 Pro"
        )

        await _initialize_page_logic(mock_browser)

        call_args = mock_browser.new_context.call_args
        assert call_args is not None
        assert call_args[1]["proxy"] == {"server": "http://proxy:8080"}


# --- New Tests ---

# 1. Storage State & Launch Modes


@pytest.mark.asyncio
async def test_init_storage_state_explicit_exists(
    mock_browser, mock_browser_context, mock_page, mock_expect
):
    with (
        patch("os.path.exists", return_value=True),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(
            mock_browser, storage_state_path="/path/to/auth.json"
        )

        call_args = mock_browser.new_context.call_args
        assert call_args[1]["storage_state"] == "/path/to/auth.json"


@pytest.mark.asyncio
async def test_init_storage_state_explicit_missing(mock_browser):
    with patch("os.path.exists", return_value=False):
        with pytest.raises(RuntimeError, match="指定的认证文件不存在"):
            await _initialize_page_logic(
                mock_browser, storage_state_path="/path/to/missing.json"
            )


@pytest.mark.asyncio
async def test_init_headless_auth_exists(
    mock_browser, mock_browser_context, mock_page, mock_expect
):
    with (
        patch.dict(
            "os.environ",
            {"LAUNCH_MODE": "headless", "ACTIVE_AUTH_JSON_PATH": "/env/auth.json"},
        ),
        patch("os.path.exists", return_value=True),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert call_args[1]["storage_state"] == "/env/auth.json"


@pytest.mark.asyncio
async def test_init_headless_auth_invalid(mock_browser):
    with (
        patch.dict(
            "os.environ",
            {"LAUNCH_MODE": "headless", "ACTIVE_AUTH_JSON_PATH": "/env/invalid.json"},
        ),
        patch("os.path.exists", return_value=False),
    ):
        with pytest.raises(RuntimeError, match="headless 模式认证文件无效"):
            await _initialize_page_logic(mock_browser)


@pytest.mark.asyncio
async def test_init_debug_auth_exists(
    mock_browser, mock_browser_context, mock_page, mock_expect
):
    with (
        patch.dict(
            "os.environ",
            {"LAUNCH_MODE": "debug", "ACTIVE_AUTH_JSON_PATH": "/env/debug.json"},
        ),
        patch("os.path.exists", return_value=True),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert call_args[1]["storage_state"] == "/env/debug.json"


@pytest.mark.asyncio
async def test_init_debug_auth_missing_file(
    mock_browser, mock_browser_context, mock_page, mock_expect
):
    with (
        patch.dict(
            "os.environ",
            {"LAUNCH_MODE": "debug", "ACTIVE_AUTH_JSON_PATH": "/env/missing.json"},
        ),
        patch("os.path.exists", return_value=False),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert "storage_state" not in call_args[1]


@pytest.mark.asyncio
async def test_init_direct_debug_no_browser(
    mock_browser, mock_browser_context, mock_page, mock_expect
):
    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "direct_debug_no_browser"}),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert "storage_state" not in call_args[1]


@pytest.mark.asyncio
async def test_init_unknown_launch_mode(
    mock_browser, mock_browser_context, mock_page, mock_expect
):
    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "unknown_mode"}),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)
        call_args = mock_browser.new_context.call_args
        assert "storage_state" not in call_args[1]


# 2. Page Discovery & Navigation Errors


@pytest.mark.asyncio
async def test_init_page_discovery_errors(
    mock_browser, mock_browser_context, mock_page, mock_expect
):
    """Test error handling during iteration of existing pages."""
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        # Create 3 pages:
        # 1. Raises PlaywrightAsyncError
        # 2. Raises AttributeError
        # 3. Raises generic Exception
        # 4. Valid page (to ensure loop continues or finishes)

        page1 = AsyncMock()
        type(page1).url = PropertyMock(side_effect=PlaywrightAsyncError("PW Error"))

        page2 = AsyncMock()
        type(page2).url = PropertyMock(side_effect=AttributeError("Attr Error"))

        page3 = AsyncMock()
        type(page3).url = PropertyMock(side_effect=Exception("Generic Error"))

        # We need to mock the pages property to return these
        mock_browser_context.pages = [page1, page2, page3]

        # It should fall through to creating a new page
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)

        # Should have tried to create a new page since no existing one was found
        mock_browser_context.new_page.assert_called()


@pytest.mark.asyncio
async def test_init_new_page_nav_error_generic(
    mock_browser, mock_browser_context, mock_page
):
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.goto.side_effect = Exception("Navigation Failed")

        with pytest.raises(RuntimeError):
            await _initialize_page_logic(mock_browser)

        mock_snapshot.assert_any_call("init_new_page_nav_fail")


@pytest.mark.asyncio
async def test_init_new_page_nav_error_net_interrupt(
    mock_browser, mock_browser_context, mock_page
):
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.goto.side_effect = Exception("NS_ERROR_NET_INTERRUPT")

        with pytest.raises(RuntimeError):
            await _initialize_page_logic(mock_browser)

        mock_snapshot.assert_any_call("init_new_page_nav_fail")


# 3. Login Logic


@pytest.mark.asyncio
async def test_init_login_headless_fail(mock_browser, mock_browser_context, mock_page):
    # Ensure ACTIVE_AUTH_JSON_PATH is set so we pass the initial check
    with (
        patch.dict(
            "os.environ",
            {"LAUNCH_MODE": "headless", "ACTIVE_AUTH_JSON_PATH": "/path/to/auth.json"},
        ),
        patch("os.path.exists", return_value=True),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        # First URL check (after goto) returns login URL
        mock_page.url = "https://accounts.google.com/signin"
        mock_page.goto = AsyncMock()

        with pytest.raises(RuntimeError) as exc:
            await _initialize_page_logic(mock_browser)
        assert "无头模式认证失败" in str(exc.value)


@pytest.mark.asyncio
async def test_init_login_interactive_success(
    mock_browser, mock_browser_context, mock_page, mock_expect
):
    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug", "SUPPRESS_LOGIN_WAIT": "0"}),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.core.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch("builtins.input", return_value=""),
        patch("builtins.print"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        # Sequence of URLs:
        # 1. After goto -> signin
        # 2. After wait_for_url -> new_chat
        type(mock_page).url = PropertyMock(
            side_effect=[
                "https://accounts.google.com/signin",
                "https://aistudio.google.com/prompts/new_chat",
                "https://aistudio.google.com/prompts/new_chat",
                "https://aistudio.google.com/prompts/new_chat",
            ]
        )

        mock_page.wait_for_url = AsyncMock()
        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)

        mock_page.wait_for_url.assert_called()


@pytest.mark.asyncio
async def test_init_login_interactive_suppress_wait(
    mock_browser, mock_browser_context, mock_page, mock_expect
):
    with (
        patch.dict(
            "os.environ", {"LAUNCH_MODE": "debug", "SUPPRESS_LOGIN_WAIT": "true"}
        ),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.core.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch("builtins.input") as mock_input,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        type(mock_page).url = PropertyMock(
            side_effect=[
                "https://accounts.google.com/signin",
                "https://aistudio.google.com/prompts/new_chat",
                "https://aistudio.google.com/prompts/new_chat",
                "https://aistudio.google.com/prompts/new_chat",
            ]
        )

        mock_page.locator.return_value.first.inner_text = AsyncMock(
            return_value="Model"
        )

        await _initialize_page_logic(mock_browser)

        mock_input.assert_not_called()


@pytest.mark.asyncio
async def test_init_login_interactive_fail_still_login_page(
    mock_browser, mock_browser_context, mock_page
):
    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug"}),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch("builtins.input", return_value=""),
        patch("browser_utils.operations.save_error_snapshot", new_callable=AsyncMock),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        type(mock_page).url = PropertyMock(
            return_value="https://accounts.google.com/signin"
        )

        with pytest.raises(RuntimeError, match="手动登录尝试后仍在登录页面"):
            await _initialize_page_logic(mock_browser)


@pytest.mark.asyncio
async def test_init_login_wait_exception(mock_browser, mock_browser_context, mock_page):
    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug"}),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch("builtins.input", return_value=""),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        type(mock_page).url = PropertyMock(
            return_value="https://accounts.google.com/signin"
        )
        mock_page.wait_for_url.side_effect = Exception("Wait Timeout")

        with pytest.raises(RuntimeError):
            await _initialize_page_logic(mock_browser)

        mock_snapshot.assert_any_call("init_login_wait_fail")


# 4. Unexpected Page & Model Name Error


@pytest.mark.asyncio
async def test_init_unexpected_page_url(mock_browser, mock_browser_context, mock_page):
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page

        # Not login, but not target either
        type(mock_page).url = PropertyMock(return_value="https://google.com")

        with pytest.raises(RuntimeError):
            await _initialize_page_logic(mock_browser)

        mock_snapshot.assert_any_call("init_unexpected_page")


@pytest.mark.asyncio
async def test_init_model_name_error(mock_browser, mock_browser_context, mock_page):
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"

        mock_expect = MagicMock()
        mock_expect.return_value.to_be_visible = AsyncMock()

        # Override the locator to fail for model-name
        original_locator = mock_page.locator.side_effect

        def failing_locator_factory(selector):
            loc = original_locator()
            if '[data-test-id="model-name"]' in selector:
                loc.first.inner_text = AsyncMock(
                    side_effect=PlaywrightAsyncError("Locator Fail")
                )
            return loc

        mock_page.locator = MagicMock(side_effect=failing_locator_factory)

        with patch("browser_utils.initialization.core.expect_async", mock_expect):
            # The PlaywrightAsyncError is caught and re-raised as RuntimeError
            with pytest.raises(RuntimeError):
                await _initialize_page_logic(mock_browser)


@pytest.mark.asyncio
async def test_init_input_visible_timeout(
    mock_browser, mock_browser_context, mock_page
):
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        mock_browser_context.pages = []
        mock_browser_context.new_page.return_value = mock_page
        mock_page.url = "https://aistudio.google.com/prompts/new_chat"

        mock_expect = MagicMock()
        # expect_async raises error (timeout)
        mock_expect.return_value.to_be_visible.side_effect = Exception(
            "Timeout waiting for input"
        )

        with patch("browser_utils.initialization.core.expect_async", mock_expect):
            with pytest.raises(RuntimeError):
                await _initialize_page_logic(mock_browser)

            mock_snapshot.assert_any_call("init_fail_input_timeout")


# 5. Cancellation & Generic Errors


@pytest.mark.asyncio
async def test_init_cancelled(mock_browser, mock_browser_context):
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
    ):
        mock_browser.new_context.side_effect = asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await _initialize_page_logic(mock_browser)


@pytest.mark.asyncio
async def test_init_generic_exception_cleanup(mock_browser, mock_browser_context):
    with (
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch(
            "browser_utils.operations.save_error_snapshot", new_callable=AsyncMock
        ) as mock_snapshot,
    ):
        # Fail at setup_network_interception_and_scripts
        with patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            side_effect=Exception("Setup Fail"),
        ):
            with pytest.raises(RuntimeError, match="页面初始化意外错误"):
                await _initialize_page_logic(mock_browser)

            # Verify context was closed
            mock_browser_context.close.assert_called()
            mock_snapshot.assert_called_with("init_unexpected_error")


# 6. Close Page Logic Errors


@pytest.mark.asyncio
async def test_close_page_logic_errors():
    from api_utils.server_state import state

    original_page = state.page_instance

    try:
        mock_page = AsyncMock()
        # is_closed must be a MagicMock returning bool, not AsyncMock returning coroutine
        mock_page.is_closed = MagicMock(return_value=False)

        # 1. PlaywrightAsyncError
        mock_page.close.side_effect = PlaywrightAsyncError("PW Error")
        state.page_instance = mock_page
        await _close_page_logic()  # Should not raise

        # 2. TimeoutError
        mock_page.close.side_effect = asyncio.TimeoutError("Timeout")
        state.page_instance = mock_page
        await _close_page_logic()  # Should not raise

        # 3. Generic Exception
        mock_page.close.side_effect = Exception("Generic")
        state.page_instance = mock_page
        await _close_page_logic()  # Should not raise

        # 4. CancelledError
        mock_page.close.side_effect = asyncio.CancelledError()
        state.page_instance = mock_page
        with pytest.raises(asyncio.CancelledError):
            await _close_page_logic()
    finally:
        state.page_instance = original_page


# 7. Signal Camoufox Shutdown


@pytest.mark.asyncio
async def test_signal_camoufox_shutdown_no_env():
    with patch.dict("os.environ", {}, clear=True):
        await signal_camoufox_shutdown()
        # Should just return


@pytest.mark.asyncio
async def test_signal_camoufox_shutdown_no_browser():
    with (
        patch.dict("os.environ", {"CAMOUFOX_WS_ENDPOINT": "ws://test"}),
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        import server

        setattr(server, "browser_instance", None)
        await signal_camoufox_shutdown()
        # Should just return


@pytest.mark.asyncio
async def test_signal_camoufox_shutdown_success():
    with (
        patch.dict("os.environ", {"CAMOUFOX_WS_ENDPOINT": "ws://test"}),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch("asyncio.sleep", side_effect=AsyncMock()),
    ):
        import server

        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        setattr(server, "browser_instance", mock_browser)

        await signal_camoufox_shutdown()


@pytest.mark.asyncio
async def test_signal_camoufox_shutdown_exception():
    with (
        patch.dict("os.environ", {"CAMOUFOX_WS_ENDPOINT": "ws://test"}),
        patch.dict("sys.modules", {"server": MagicMock()}),
        patch("asyncio.sleep", side_effect=Exception("Sleep Fail")),
    ):
        import server

        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        setattr(server, "browser_instance", mock_browser)

        # Should catch exception and log error
        await signal_camoufox_shutdown()


# 8. Enable Temporary Chat Mode


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_already_active(mock_page):
    locator = MagicMock()
    locator.wait_for = AsyncMock()
    locator.get_attribute = AsyncMock(return_value="ms-button-active")
    mock_page.locator.return_value = locator

    await enable_temporary_chat_mode(mock_page)

    locator.click.assert_not_called()


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_activate_success(mock_page):
    locator = MagicMock()
    locator.wait_for = AsyncMock()
    locator.click = AsyncMock()
    # First inactive, then active
    locator.get_attribute = AsyncMock(side_effect=["", "ms-button-active"])
    # Use side_effect to override the factory
    mock_page.locator = MagicMock(return_value=locator)

    await enable_temporary_chat_mode(mock_page)

    locator.click.assert_called()


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_activate_fail(mock_page):
    locator = MagicMock()
    locator.wait_for = AsyncMock()
    locator.click = AsyncMock()
    # Always inactive
    locator.get_attribute = AsyncMock(return_value="")
    # Use side_effect to override the factory
    mock_page.locator = MagicMock(return_value=locator)

    await enable_temporary_chat_mode(mock_page)

    locator.click.assert_called()


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_exception(mock_page):
    mock_page.locator.side_effect = Exception("Locator Fail")

    # Should catch exception and log warning
    await enable_temporary_chat_mode(mock_page)


@pytest.mark.asyncio
async def test_enable_temporary_chat_mode_cancelled(mock_page):
    mock_page.locator.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await enable_temporary_chat_mode(mock_page)
