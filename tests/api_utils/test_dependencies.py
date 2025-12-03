"""
High-quality tests for api_utils/dependencies.py - FastAPI dependency injection.

Focus: Test all 12 dependency getter functions.
Strategy: Mock server module globals, verify each function returns correct object.
"""

from asyncio import Event, Lock, Queue
from unittest.mock import MagicMock, patch

from api_utils.dependencies import (
    get_current_ai_studio_model_id,
    get_excluded_model_ids,
    get_log_ws_manager,
    get_logger,
    get_model_list_fetch_event,
    get_page_instance,
    get_parsed_model_list,
    get_processing_lock,
    get_request_queue,
    get_server_state,
    get_worker_task,
)


def test_get_logger():
    """
    测试场景: 获取 logger 依赖
    预期: 返回 server.logger 对象 (lines 10-13)
    """
    mock_logger = MagicMock()

    with patch("server.logger", mock_logger):
        result = get_logger()

        # 验证: 返回 server.logger
        assert result is mock_logger


def test_get_log_ws_manager():
    """
    测试场景: 获取 WebSocket 管理器依赖
    预期: 返回 server.log_ws_manager 对象 (lines 16-19)
    """
    mock_ws_manager = MagicMock()

    with patch("server.log_ws_manager", mock_ws_manager):
        result = get_log_ws_manager()

        # 验证: 返回 server.log_ws_manager
        assert result is mock_ws_manager


def test_get_request_queue():
    """
    测试场景: 获取请求队列依赖
    预期: 返回 server.request_queue 对象 (lines 22-25)
    """
    mock_queue = MagicMock(spec=Queue)

    with patch("server.request_queue", mock_queue):
        result = get_request_queue()

        # 验证: 返回 server.request_queue
        assert result is mock_queue


def test_get_processing_lock():
    """
    测试场景: 获取处理锁依赖
    预期: 返回 server.processing_lock 对象 (lines 28-31)
    """
    mock_lock = MagicMock(spec=Lock)

    with patch("server.processing_lock", mock_lock):
        result = get_processing_lock()

        # 验证: 返回 server.processing_lock
        assert result is mock_lock


def test_get_worker_task():
    """
    测试场景: 获取工作任务依赖
    预期: 返回 server.worker_task 对象 (lines 34-37)
    """
    mock_task = MagicMock()

    with patch("server.worker_task", mock_task):
        result = get_worker_task()

        # 验证: 返回 server.worker_task
        assert result is mock_task


def test_get_server_state():
    """
    测试场景: 获取服务器状态依赖
    预期: 返回包含4个布尔标志的字典 (lines 40-54)
    """
    with (
        patch("server.is_initializing", True, create=True),
        patch("server.is_playwright_ready", False, create=True),
        patch("server.is_browser_connected", True, create=True),
        patch("server.is_page_ready", False, create=True),
    ):
        result = get_server_state()

        # 验证: 返回字典包含所有4个标志 (lines 49-54)
        assert isinstance(result, dict)
        assert result["is_initializing"] is True
        assert result["is_playwright_ready"] is False
        assert result["is_browser_connected"] is True
        assert result["is_page_ready"] is False


def test_get_server_state_immutable_snapshot():
    """
    测试场景: 验证 get_server_state 返回不可变快照
    预期: 返回新字典,不是原始引用 (line 49 dict())
    """
    with (
        patch("server.is_initializing", False, create=True),
        patch("server.is_playwright_ready", True, create=True),
        patch("server.is_browser_connected", False, create=True),
        patch("server.is_page_ready", True, create=True),
    ):
        result1 = get_server_state()
        result2 = get_server_state()

        # 验证: 每次调用返回新字典
        assert result1 is not result2
        # 验证: 值相同
        assert result1 == result2


def test_get_page_instance():
    """
    测试场景: 获取页面实例依赖
    预期: 返回 server.page_instance 对象 (lines 57-60)
    """
    mock_page = MagicMock()

    with patch("server.page_instance", mock_page):
        result = get_page_instance()

        # 验证: 返回 server.page_instance
        assert result is mock_page


def test_get_model_list_fetch_event():
    """
    测试场景: 获取模型列表获取事件依赖
    预期: 返回 server.model_list_fetch_event 对象 (lines 63-66)
    """
    mock_event = MagicMock(spec=Event)

    with patch("server.model_list_fetch_event", mock_event):
        result = get_model_list_fetch_event()

        # 验证: 返回 server.model_list_fetch_event
        assert result is mock_event


def test_get_parsed_model_list():
    """
    测试场景: 获取解析的模型列表依赖
    预期: 返回 server.parsed_model_list 对象 (lines 69-72)
    """
    mock_model_list = [
        {"id": "gemini-1.5-pro", "object": "model"},
        {"id": "gemini-2.0-flash", "object": "model"},
    ]

    with patch("server.parsed_model_list", mock_model_list):
        result = get_parsed_model_list()

        # 验证: 返回 server.parsed_model_list
        assert result is mock_model_list
        assert len(result) == 2


def test_get_excluded_model_ids():
    """
    测试场景: 获取排除的模型ID集合依赖
    预期: 返回 server.excluded_model_ids 对象 (lines 75-78)
    """
    mock_excluded_ids = {"model-1", "model-2", "model-3"}

    with patch("server.excluded_model_ids", mock_excluded_ids, create=True):
        result = get_excluded_model_ids()

        # 验证: 返回 server.excluded_model_ids
        assert result is mock_excluded_ids
        assert len(result) == 3


def test_get_current_ai_studio_model_id():
    """
    测试场景: 获取当前AI Studio模型ID依赖
    预期: 返回 server.current_ai_studio_model_id 对象 (lines 81-84)
    """
    mock_model_id = "gemini-1.5-pro"

    with patch("server.current_ai_studio_model_id", mock_model_id):
        result = get_current_ai_studio_model_id()

        # 验证: 返回 server.current_ai_studio_model_id
        assert result == "gemini-1.5-pro"


def test_get_current_ai_studio_model_id_none():
    """
    测试场景: 当前模型ID为None (初始状态)
    预期: 返回None
    """
    with patch("server.current_ai_studio_model_id", None):
        result = get_current_ai_studio_model_id()

        # 验证: 返回None
        assert result is None
