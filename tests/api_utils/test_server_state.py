"""
High-quality tests for api_utils/server_state.py - Server state management.

Focus: Test ServerState class methods and module-level __getattr__.
Strategy: Test clear_debug_logs and backward compatibility __getattr__.
"""

import pytest

from api_utils import server_state
from api_utils.server_state import ServerState, state


@pytest.fixture
def fresh_state():
    """Provide a fresh ServerState instance for each test."""
    test_state = ServerState()
    yield test_state
    test_state.reset()


def test_clear_debug_logs(fresh_state):
    """
    测试场景: 清除调试日志
    预期: console_logs 和 network_log 被重置 (lines 96-97)
    """
    # Setup: 填充一些日志数据
    fresh_state.console_logs = [
        {"level": "info", "message": "test1"},
        {"level": "error", "message": "test2"},
    ]
    fresh_state.network_log = {
        "requests": [{"url": "http://example.com", "method": "GET"}],
        "responses": [{"status": 200, "body": "OK"}],
    }

    # 执行: 清除日志
    fresh_state.clear_debug_logs()

    # 验证: 日志被清空 (lines 96-97)
    assert fresh_state.console_logs == []
    assert fresh_state.network_log == {"requests": [], "responses": []}


def test_module_getattr_success():
    """
    测试场景: 使用 __getattr__ 访问状态属性
    预期: 返回 state 的属性值 (line 135)
    """
    # 使用 __getattr__ 访问 logger
    logger_via_getattr = server_state.logger

    # 验证: 返回 state.logger (line 135 触发 getattr)
    assert logger_via_getattr is state.logger


def test_module_getattr_missing_attribute():
    """
    测试场景: 使用 __getattr__ 访问不存在的属性
    预期: 抛出 AttributeError (line 136)
    """
    with pytest.raises(AttributeError) as exc_info:
        _ = server_state.nonexistent_attribute

    # 验证: 错误消息
    assert "has no attribute 'nonexistent_attribute'" in str(exc_info.value)


def test_state_reset():
    """
    测试场景: 重置状态
    预期: 所有属性恢复到初始值
    """
    # 修改一些状态
    state.is_page_ready = True
    state.current_ai_studio_model_id = "test-model"
    state.console_logs = [{"test": "data"}]

    # 重置
    state.reset()

    # 验证: 恢复初始值
    assert state.is_page_ready is False
    assert state.current_ai_studio_model_id is None
    assert state.console_logs == []


def test_state_singleton():
    """
    测试场景: 验证 state 是单例
    预期: 导入的 state 是同一个实例
    """
    from api_utils.server_state import state as state2

    # 验证: 是同一个实例
    assert state is state2
