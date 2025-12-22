"""
Integration tests for browser_utils/initialization/core.py.

These tests verify real browser initialization logic with minimal mocking:
- Uses REAL temp files for auth (no os.path.exists mocking)
- Uses REAL file I/O (storage state selection logic executes)
- Mocks ONLY external I/O (browser.new_context, page.goto, page.locator)

Focus: Test that storage state selection, page discovery, and readiness checks
work correctly with real files and real logic.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_storage_state_explicit_exists(temp_auth_file):
    """
    测试场景: 显式传入存在的认证文件路径
    策略: 使用真实临时文件，验证文件路径被正确使用
    """
    from browser_utils.initialization.core import initialize_page_logic

    # 验证文件确实存在（真实文件 I/O）
    assert temp_auth_file.exists()
    assert os.path.exists(str(temp_auth_file))

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_page)

    # Mock 页面状态
    mock_page.url = "https://aistudio.google.com/prompts/new_chat"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()

    # Create locator mock with count() support
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)  # Element exists
    mock_locator.first = MagicMock()
    mock_locator.first.inner_text = AsyncMock(return_value="Gemini 1.5 Pro")
    mock_page.locator = MagicMock(return_value=mock_locator)

    # Mock expect_async
    mock_expect = MagicMock()
    mock_expect.return_value.to_be_visible = AsyncMock()

    with (
        patch("browser_utils.initialization.core.expect_async", mock_expect),
        patch("playwright.async_api.expect", mock_expect),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.auth.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        from api_utils.server_state import state

        state.PLAYWRIGHT_PROXY_SETTINGS = None

        # 调用真实逻辑，传入真实文件路径
        await initialize_page_logic(
            mock_browser, storage_state_path=str(temp_auth_file)
        )

        # 验证: new_context 被调用时包含了真实文件路径
        call_args = mock_browser.new_context.call_args
        assert call_args is not None
        assert "storage_state" in call_args[1]
        assert call_args[1]["storage_state"] == str(temp_auth_file)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_storage_state_explicit_missing(temp_auth_file_missing):
    """
    测试场景: 显式传入不存在的认证文件路径
    策略: 使用真实文件系统检查，验证 RuntimeError 被抛出
    """
    from browser_utils.initialization.core import initialize_page_logic

    # 验证文件确实不存在（真实文件 I/O）
    assert not temp_auth_file_missing.exists()
    assert not os.path.exists(str(temp_auth_file_missing))

    mock_browser = AsyncMock()

    with patch.dict("sys.modules", {"server": MagicMock()}):
        # 预期: 抛出 RuntimeError，因为文件不存在
        with pytest.raises(RuntimeError, match="指定的认证文件不存在"):
            await initialize_page_logic(
                mock_browser, storage_state_path=str(temp_auth_file_missing)
            )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_headless_auth_exists(temp_auth_file):
    """
    测试场景: 无头模式下，ACTIVE_AUTH_JSON_PATH 指向存在的文件
    策略: 使用真实文件，验证无头模式正确加载认证
    """
    from browser_utils.initialization.core import initialize_page_logic

    assert temp_auth_file.exists()

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_page.url = "https://aistudio.google.com/prompts/new_chat"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()

    # Create locator mock with count() support
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)  # Element exists
    mock_locator.first = MagicMock()
    mock_locator.first.inner_text = AsyncMock(return_value="Gemini 2.0 Flash")
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_expect = MagicMock()
    mock_expect.return_value.to_be_visible = AsyncMock()

    with (
        patch.dict(
            "os.environ",
            {"LAUNCH_MODE": "headless", "ACTIVE_AUTH_JSON_PATH": str(temp_auth_file)},
        ),
        patch("browser_utils.initialization.core.expect_async", mock_expect),
        patch("playwright.async_api.expect", mock_expect),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.auth.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        from api_utils.server_state import state

        state.PLAYWRIGHT_PROXY_SETTINGS = None

        await initialize_page_logic(mock_browser)

        # 验证: storage_state 参数使用了真实文件路径
        call_args = mock_browser.new_context.call_args
        assert call_args[1]["storage_state"] == str(temp_auth_file)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_debug_auth_exists(temp_auth_file):
    """
    测试场景: 调试模式下，ACTIVE_AUTH_JSON_PATH 指向存在的文件
    策略: 使用真实文件，验证调试模式正确加载认证
    """
    from browser_utils.initialization.core import initialize_page_logic

    assert temp_auth_file.exists()

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_page.url = "https://aistudio.google.com/prompts/new_chat"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()

    # Create locator mock with count() support
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)  # Element exists
    mock_locator.first = MagicMock()
    mock_locator.first.inner_text = AsyncMock(return_value="Model")
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_expect = MagicMock()
    mock_expect.return_value.to_be_visible = AsyncMock()

    with (
        patch.dict(
            "os.environ",
            {"LAUNCH_MODE": "debug", "ACTIVE_AUTH_JSON_PATH": str(temp_auth_file)},
        ),
        patch("browser_utils.initialization.core.expect_async", mock_expect),
        patch("playwright.async_api.expect", mock_expect),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.auth.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        from api_utils.server_state import state

        state.PLAYWRIGHT_PROXY_SETTINGS = None

        await initialize_page_logic(mock_browser)

        call_args = mock_browser.new_context.call_args
        assert call_args[1]["storage_state"] == str(temp_auth_file)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_debug_auth_missing_falls_back(temp_auth_file_missing):
    """
    测试场景: 调试模式下，ACTIVE_AUTH_JSON_PATH 指向不存在的文件
    策略: 使用真实文件系统，验证调试模式回退到不使用认证
    """
    from browser_utils.initialization.core import initialize_page_logic

    assert not temp_auth_file_missing.exists()

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_page.url = "https://aistudio.google.com/prompts/new_chat"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()

    # Create locator mock with count() support
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)  # Element exists
    mock_locator.first = MagicMock()
    mock_locator.first.inner_text = AsyncMock(return_value="Model")
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_expect = MagicMock()
    mock_expect.return_value.to_be_visible = AsyncMock()

    with (
        patch.dict(
            "os.environ",
            {
                "LAUNCH_MODE": "debug",
                "ACTIVE_AUTH_JSON_PATH": str(temp_auth_file_missing),
            },
        ),
        patch("browser_utils.initialization.core.expect_async", mock_expect),
        patch("playwright.async_api.expect", mock_expect),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.auth.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        from api_utils.server_state import state

        state.PLAYWRIGHT_PROXY_SETTINGS = None

        await initialize_page_logic(mock_browser)

        # 验证: 调试模式下文件不存在时，不使用 storage_state
        call_args = mock_browser.new_context.call_args
        assert "storage_state" not in call_args[1]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_proxy_settings_applied():
    """
    测试场景: 验证代理设置被正确传递到浏览器上下文
    策略: Mock browser I/O，验证 proxy 参数
    """
    from browser_utils.initialization.core import initialize_page_logic

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_page.url = "https://aistudio.google.com/prompts/new_chat"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()

    # Create locator mock with count() support
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)  # Element exists
    mock_locator.first = MagicMock()
    mock_locator.first.inner_text = AsyncMock(return_value="Model")
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_expect = MagicMock()
    mock_expect.return_value.to_be_visible = AsyncMock()

    proxy_config = {"server": "http://127.0.0.1:8080"}

    # Create mock server with proper proxy settings
    mock_server = MagicMock()
    mock_server.PLAYWRIGHT_PROXY_SETTINGS = proxy_config

    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug"}),
        patch("browser_utils.initialization.core.expect_async", mock_expect),
        patch("playwright.async_api.expect", mock_expect),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.auth.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch.dict("sys.modules", {"server": mock_server}),
    ):
        await initialize_page_logic(mock_browser)

        # 验证: proxy 参数被正确传递
        call_args = mock_browser.new_context.call_args
        assert call_args[1]["proxy"] == proxy_config


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_page_discovery_existing_page():
    """
    测试场景: 浏览器上下文中已有页面，发现并复用
    策略: Mock browser I/O，验证页面发现逻辑
    """
    from browser_utils.initialization.core import initialize_page_logic

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)

    # 上下文中已有一个页面
    mock_page.url = "https://aistudio.google.com/prompts/new_chat"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()

    # Create locator mock with count() support
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)  # Element exists
    mock_locator.first = MagicMock()
    mock_locator.first.inner_text = AsyncMock(return_value="Model")
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_context.pages = [mock_page]

    mock_expect = MagicMock()
    mock_expect.return_value.to_be_visible = AsyncMock()

    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug"}),
        patch("browser_utils.initialization.core.expect_async", mock_expect),
        patch("playwright.async_api.expect", mock_expect),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.auth.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        from api_utils.server_state import state

        state.PLAYWRIGHT_PROXY_SETTINGS = None

        page, _ = await initialize_page_logic(mock_browser)

        # 验证: 返回的是现有页面，而不是新创建的
        assert page is mock_page
        # 验证: new_page 不应该被调用
        mock_context.new_page.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_login_url_transition():
    """
    测试场景: 页面从登录 URL 过渡到 AI Studio URL
    策略: Mock page.url 属性返回不同的值，验证 URL 检测逻辑
    """
    from unittest.mock import PropertyMock

    from browser_utils.initialization.core import initialize_page_logic

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_page)

    # 模拟 URL 过渡: login -> new_chat
    type(mock_page).url = PropertyMock(
        side_effect=[
            "https://accounts.google.com/signin",  # goto 后的 URL
            "https://aistudio.google.com/prompts/new_chat",  # wait_for_url 后
            "https://aistudio.google.com/prompts/new_chat",  # 最终检查
            "https://aistudio.google.com/prompts/new_chat",  # 模型名提取
        ]
    )

    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()
    mock_page.wait_for_url = AsyncMock()

    # Create locator mock with count() support
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)  # Element exists
    mock_locator.first = MagicMock()
    mock_locator.first.inner_text = AsyncMock(return_value="Model")
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_expect = MagicMock()
    mock_expect.return_value.to_be_visible = AsyncMock()

    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug", "SUPPRESS_LOGIN_WAIT": "0"}),
        patch("browser_utils.initialization.core.expect_async", mock_expect),
        patch("playwright.async_api.expect", mock_expect),
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
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        from api_utils.server_state import state

        state.PLAYWRIGHT_PROXY_SETTINGS = None

        await initialize_page_logic(mock_browser)

        # 验证: wait_for_url 被调用，等待从登录页过渡
        mock_page.wait_for_url.assert_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_model_name_extraction():
    """
    测试场景: 从页面中提取模型名称
    策略: Mock page.locator，验证模型名提取逻辑
    """
    from browser_utils.initialization.core import initialize_page_logic

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_page.url = "https://aistudio.google.com/prompts/new_chat"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()

    # Mock 模型名选择器
    model_name = "Gemini 1.5 Pro Experimental"
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)  # Element exists
    mock_locator.first = MagicMock()
    mock_locator.first.inner_text = AsyncMock(return_value=model_name)
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_expect = MagicMock()
    mock_expect.return_value.to_be_visible = AsyncMock()

    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug"}),
        patch("browser_utils.initialization.core.expect_async", mock_expect),
        patch("playwright.async_api.expect", mock_expect),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.auth.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        from api_utils.server_state import state

        state.PLAYWRIGHT_PROXY_SETTINGS = None
        state.current_ai_studio_model_id = None

        _, is_new_page = await initialize_page_logic(mock_browser)

        # 验证: locator 被调用以提取模型名
        mock_page.locator.assert_called()
        # 验证: 模型名被设置到 server.current_ai_studio_model_id
        # (这个断言可能需要检查实际的赋值逻辑)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_init_page_readiness_verification():
    """
    测试场景: 验证页面就绪状态（输入框可见）
    策略: Mock expect_async，验证页面就绪检查逻辑
    """
    from browser_utils.initialization.core import initialize_page_logic

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_page.url = "https://aistudio.google.com/prompts/new_chat"
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.goto = AsyncMock()

    # Create locator mock with count() support
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)  # Element exists
    mock_locator.first = MagicMock()
    mock_locator.first.inner_text = AsyncMock(return_value="Model")
    mock_page.locator = MagicMock(return_value=mock_locator)

    # Mock expect_async 来验证页面就绪检查
    mock_expect = MagicMock()
    mock_assertion = MagicMock()
    mock_assertion.to_be_visible = AsyncMock()
    mock_expect.return_value = mock_assertion

    with (
        patch.dict("os.environ", {"LAUNCH_MODE": "debug"}),
        patch("browser_utils.initialization.core.expect_async", mock_expect),
        patch("playwright.async_api.expect", mock_expect),
        patch(
            "browser_utils.initialization.core.setup_network_interception_and_scripts",
            new_callable=AsyncMock,
        ),
        patch("browser_utils.initialization.core.setup_debug_listeners"),
        patch(
            "browser_utils.initialization.auth.wait_for_model_list_and_handle_auth_save",
            new_callable=AsyncMock,
        ),
        patch.dict("sys.modules", {"server": MagicMock()}),
    ):
        from api_utils.server_state import state

        state.PLAYWRIGHT_PROXY_SETTINGS = None

        await initialize_page_logic(mock_browser)

        # 验证: expect_async 被调用以检查输入框可见性
        mock_expect.assert_called()
        # 验证: to_be_visible 被等待
        mock_assertion.to_be_visible.assert_called()
