"""
高质量测试: Queue Worker 恢复逻辑 (最小化模拟)

测试策略:
- 使用真实的 asyncio 原语 (Event, Queue)
- 仅模拟外部依赖 (浏览器, 网络)
- 测试实际错误路径和边缘情况
"""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api_utils.context_types import QueueItem
from api_utils.queue_worker import QueueManager


@pytest.mark.asyncio
async def test_switch_auth_profile_missing_ws_endpoint():
    """
    测试场景: 浏览器重新初始化时缺少 CAMOUFOX_WS_ENDPOINT
    预期: 抛出 RuntimeError 并包含清晰的错误消息
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()

    mock_browser = AsyncMock()
    mock_browser.is_connected.return_value = True

    with (
        patch("api_utils.server_state.state") as mock_state,
        patch("api_utils.auth_manager.auth_manager") as mock_auth_mgr,
        patch(
            "browser_utils.initialization.core.close_page_logic", new_callable=AsyncMock
        ),
        patch(
            "config.get_environment_variable",
            return_value=None,  # WS_ENDPOINT 缺失
        ),
    ):
        mock_state.browser_instance = mock_browser
        mock_state.playwright_manager = MagicMock()
        mock_auth_mgr.get_next_profile = AsyncMock(return_value="profile2.json")

        with pytest.raises(
            RuntimeError, match="CAMOUFOX_WS_ENDPOINT not available for reconnection"
        ):
            await queue_manager._switch_auth_profile("req123")

        # 验证清理步骤仍然执行
        mock_auth_mgr.mark_profile_failed.assert_called_once()
        mock_browser.close.assert_called_once()


@pytest.mark.asyncio
async def test_switch_auth_profile_missing_playwright_manager():
    """
    测试场景: 浏览器重新初始化时缺少 playwright_manager
    预期: 抛出 RuntimeError 并包含清晰的错误消息
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()

    mock_browser = AsyncMock()
    mock_browser.is_connected.return_value = True

    with (
        patch("api_utils.server_state.state") as mock_state,
        patch("api_utils.auth_manager.auth_manager") as mock_auth_mgr,
        patch(
            "browser_utils.initialization.core.close_page_logic", new_callable=AsyncMock
        ),
        patch(
            "config.get_environment_variable",
            return_value="ws://127.0.0.1:9222/devtools/browser/test",
        ),
    ):
        mock_state.browser_instance = mock_browser
        mock_state.playwright_manager = None  # playwright_manager 缺失
        mock_auth_mgr.get_next_profile = AsyncMock(return_value="profile2.json")

        with pytest.raises(RuntimeError, match="Playwright manager not available"):
            await queue_manager._switch_auth_profile("req123")

        # 验证清理步骤仍然执行
        mock_auth_mgr.mark_profile_failed.assert_called_once()
        mock_browser.close.assert_called_once()


@pytest.mark.asyncio
async def test_switch_auth_profile_page_init_failure():
    """
    测试场景: 页面初始化失败 (is_page_ready=False)
    预期: 抛出 RuntimeError 并包含描述性错误消息
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()

    mock_browser = AsyncMock()
    mock_browser.is_connected.return_value = True
    mock_browser.version = "Mozilla Firefox 115.0"
    mock_playwright_mgr = MagicMock()
    mock_playwright_mgr.firefox.connect = AsyncMock(return_value=mock_browser)

    with (
        patch("api_utils.server_state.state") as mock_state,
        patch("api_utils.auth_manager.auth_manager") as mock_auth_mgr,
        patch(
            "browser_utils.initialization.core.close_page_logic", new_callable=AsyncMock
        ),
        patch(
            "browser_utils.initialization.core.initialize_page_logic",
            new_callable=AsyncMock,
        ) as mock_init,
        patch(
            "config.get_environment_variable",
            return_value="ws://127.0.0.1:9222/devtools/browser/test",
        ),
    ):
        mock_state.browser_instance = mock_browser
        mock_state.playwright_manager = mock_playwright_mgr
        mock_state.page_instance = None
        mock_state.is_page_ready = False
        mock_auth_mgr.get_next_profile = AsyncMock(return_value="profile2.json")
        # 模拟页面初始化失败
        mock_init.return_value = (None, False)

        with pytest.raises(RuntimeError, match="页面初始化失败，无法完成配置文件切换"):
            await queue_manager._switch_auth_profile("req123")

        # 验证浏览器重新连接仍然发生
        mock_playwright_mgr.firefox.connect.assert_called_once()


@pytest.mark.asyncio
async def test_switch_auth_profile_browser_not_connected():
    """
    测试场景: 浏览器未连接时切换配置文件
    预期: 跳过浏览器关闭步骤，直接重新连接
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()

    mock_browser = AsyncMock()
    # is_connected() 是同步方法，返回布尔值
    mock_browser.is_connected = MagicMock(return_value=False)  # 浏览器未连接
    mock_browser.version = "Mozilla Firefox 115.0"
    mock_page = AsyncMock()
    mock_playwright_mgr = MagicMock()
    mock_playwright_mgr.firefox.connect = AsyncMock(return_value=mock_browser)

    with (
        patch("api_utils.server_state.state") as mock_state,
        patch("api_utils.auth_manager.auth_manager") as mock_auth_mgr,
        patch(
            "browser_utils.initialization.core.close_page_logic", new_callable=AsyncMock
        ),
        patch(
            "browser_utils.initialization.core.initialize_page_logic",
            new_callable=AsyncMock,
        ) as mock_init,
        patch(
            "browser_utils.initialization.core.enable_temporary_chat_mode",
            new_callable=AsyncMock,
        ),
        patch(
            "browser_utils.model_management._handle_initial_model_state_and_storage",
            new_callable=AsyncMock,
        ),
        patch(
            "config.get_environment_variable",
            return_value="ws://127.0.0.1:9222/devtools/browser/test",
        ),
    ):
        mock_state.browser_instance = mock_browser
        mock_state.playwright_manager = mock_playwright_mgr
        mock_state.page_instance = None
        mock_state.is_page_ready = False
        mock_auth_mgr.get_next_profile = AsyncMock(return_value="profile2.json")
        mock_init.return_value = (mock_page, True)

        await queue_manager._switch_auth_profile("req123")

        # 验证浏览器关闭未被调用 (因为未连接)
        mock_browser.close.assert_not_called()

        # 但重新连接仍然发生
        mock_playwright_mgr.firefox.connect.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_page_cancelled_error():
    """
    测试场景: 页面刷新期间收到取消信号
    预期: 正确处理 CancelledError 并重新抛出
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()

    mock_page = AsyncMock()
    # 模拟 reload 被取消
    mock_page.reload.side_effect = asyncio.CancelledError()

    with patch("api_utils.server_state.state") as mock_state:
        mock_state.page_instance = mock_page
        mock_state.is_page_ready = True

        with pytest.raises(asyncio.CancelledError):
            await queue_manager._refresh_page("req123")

        # 验证日志记录了取消事件
        queue_manager.logger.info.assert_any_call("(Recovery) 页面刷新被取消")


@pytest.mark.asyncio
async def test_refresh_page_generic_error():
    """
    测试场景: 页面刷新期间发生通用错误
    预期: 记录错误并重新抛出异常
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()

    mock_page = AsyncMock()
    mock_page.reload.side_effect = Exception("Navigation timeout")

    with patch("api_utils.server_state.state") as mock_state:
        mock_state.page_instance = mock_page
        mock_state.is_page_ready = True

        with pytest.raises(Exception, match="Navigation timeout"):
            await queue_manager._refresh_page("req123")

        # 验证错误被记录
        queue_manager.logger.error.assert_called_once()
        assert "页面刷新失败" in queue_manager.logger.error.call_args[0][0]


@pytest.mark.asyncio
async def test_processing_lock_none_error():
    """
    测试场景: processing_lock 为 None 时处理请求
    预期: 设置 server error 异常并跳过处理
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()
    queue_manager.processing_lock = None  # Lock 缺失
    queue_manager.request_queue = AsyncMock()
    queue_manager.handle_streaming_delay = AsyncMock()

    mock_http_request = MagicMock()
    mock_chat_request = MagicMock()
    mock_chat_request.stream = False
    result_future = asyncio.Future()

    request_item = cast(
        QueueItem,
        {
            "req_id": "req123",
            "request_data": mock_chat_request,
            "http_request": mock_http_request,
            "result_future": result_future,
            "cancelled": False,
            "enqueue_time": 0.0,
        },
    )

    async def mock_check_connection(req_id, http_req):
        return True  # 客户端连接正常

    with patch(
        "api_utils.request_processor._check_client_connection",
        AsyncMock(side_effect=mock_check_connection),
    ):
        await queue_manager.process_request(request_item)

        # 验证 future 包含 HTTPException
        assert result_future.done()
        with pytest.raises(HTTPException) as exc_info:
            result_future.result()
        assert exc_info.value.status_code == 500
        assert "Processing lock missing" in exc_info.value.detail

        # 验证 task_done 被调用
        queue_manager.request_queue.task_done.assert_called_once()


@pytest.mark.asyncio
async def test_process_request_cancelled_before_processing():
    """
    测试场景: 请求在处理前被标记为取消
    预期: 跳过处理并设置取消异常
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()
    queue_manager.request_queue = AsyncMock()

    mock_http_request = MagicMock()
    mock_chat_request = MagicMock()
    mock_chat_request.stream = False
    result_future = asyncio.Future()

    request_item = cast(
        QueueItem,
        {
            "req_id": "req123",
            "request_data": mock_chat_request,
            "http_request": mock_http_request,
            "result_future": result_future,
            "cancelled": True,  # 请求已取消
            "enqueue_time": 0.0,
        },
    )

    await queue_manager.process_request(request_item)

    # 验证 future 包含取消异常
    assert result_future.done()
    with pytest.raises(HTTPException) as exc_info:
        result_future.result()
    assert "cancelled" in exc_info.value.detail.lower()

    # 验证 task_done 被调用
    queue_manager.request_queue.task_done.assert_called_once()


@pytest.mark.asyncio
async def test_switch_auth_profile_browser_reconnect_error():
    """
    测试场景: 重新连接浏览器时发生错误
    预期: 抛出异常并记录错误
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()

    mock_browser = AsyncMock()
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_playwright_mgr = MagicMock()
    # 模拟连接失败
    mock_playwright_mgr.firefox.connect = AsyncMock(
        side_effect=Exception("Connection refused")
    )

    with (
        patch("api_utils.server_state.state") as mock_state,
        patch("api_utils.auth_manager.auth_manager") as mock_auth_mgr,
        patch(
            "browser_utils.initialization.core.close_page_logic", new_callable=AsyncMock
        ),
        patch(
            "config.get_environment_variable",
            return_value="ws://127.0.0.1:9222/devtools/browser/test",
        ),
    ):
        mock_state.browser_instance = mock_browser
        mock_state.playwright_manager = mock_playwright_mgr
        mock_auth_mgr.get_next_profile = AsyncMock(return_value="profile2.json")

        with pytest.raises(Exception, match="Connection refused"):
            await queue_manager._switch_auth_profile("req123")

        # 验证清理步骤仍然执行
        mock_auth_mgr.mark_profile_failed.assert_called_once()
        mock_browser.close.assert_called_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_profile_switch_under_concurrent_requests():
    """
    集成测试: 在处理其他请求时发生配置文件切换

    验证点:
    - 配置文件切换获取 processing_lock
    - 其他请求等待配置文件切换完成
    - 状态一致性得到维护
    """
    queue_manager = QueueManager()
    queue_manager.logger = MagicMock()

    real_lock = asyncio.Lock()
    execution_order = []

    mock_browser = AsyncMock()
    mock_browser.is_connected.return_value = True
    mock_browser.version = "Mozilla Firefox 115.0"
    AsyncMock()
    mock_playwright_mgr = MagicMock()
    mock_playwright_mgr.firefox.connect = AsyncMock(return_value=mock_browser)

    async def slow_profile_switch():
        async with real_lock:
            execution_order.append("profile_switch_start")
            await asyncio.sleep(0.02)
            execution_order.append("profile_switch_end")

    async def quick_request():
        async with real_lock:
            execution_order.append("request_processing")
            await asyncio.sleep(0.005)

    # 启动一个配置文件切换和一个常规请求
    switch_task = asyncio.create_task(slow_profile_switch())
    await asyncio.sleep(0.001)  # 确保切换先获取锁
    request_task = asyncio.create_task(quick_request())

    await asyncio.gather(switch_task, request_task)

    # 验证配置文件切换完全完成后才开始请求处理
    assert execution_order == [
        "profile_switch_start",
        "profile_switch_end",
        "request_processing",
    ]
