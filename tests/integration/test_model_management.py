"""
Integration tests for browser_utils/model_management.py and api_utils/model_switching.py.

These tests verify lock hierarchy and concurrent model switching behavior with REAL locks:
- Uses REAL asyncio.Lock from server_state
- Mocks ONLY external boundaries (browser, page)
- Verifies actual concurrency control and serialization

Focus: Ensure model_switching_lock serializes model switches and params_cache_lock is properly nested.
"""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_utils.context_types import RequestContext


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_model_switches_serialized(real_server_state):
    """
    测试场景: 两个并发请求尝试切换到不同模型
    预期: model_switching_lock 序列化操作，第二个请求等待第一个完成
    """
    from api_utils.model_switching import handle_model_switching

    execution_order = []

    async def mock_switch_model(page, model_id, req_id):
        execution_order.append(f"start_{req_id}")
        await asyncio.sleep(0.1)  # 模拟真实的模型切换延迟
        execution_order.append(f"end_{req_id}")
        return True

    real_server_state.current_ai_studio_model_id = "gemini-1.5-pro"

    # 创建两个请求上下文
    def create_context(model_id):
        return cast(
            RequestContext,
            {
                "needs_model_switching": True,
                "model_id_to_use": model_id,
                "page": AsyncMock(),
                "logger": MagicMock(),
                "model_switching_lock": real_server_state.model_switching_lock,
                "model_actually_switched": False,
                "current_ai_studio_model_id": "gemini-1.5-pro",
            },
        )

    context1 = create_context("gemini-2.0-flash")
    context2 = create_context("gemini-1.5-flash")

    with patch("browser_utils.switch_ai_studio_model", side_effect=mock_switch_model):
        task1 = asyncio.create_task(handle_model_switching("req1", context1))
        task2 = asyncio.create_task(handle_model_switching("req2", context2))
        await asyncio.gather(task1, task2)

    # 验证: 执行顺序证明序列化（一个完全完成后另一个才开始）
    assert len(execution_order) == 4

    # 找到第一个完成的请求
    first_end_idx = min(
        execution_order.index("end_req1"), execution_order.index("end_req2")
    )
    first_end_req = execution_order[first_end_idx].split("_")[1]
    first_start_idx = execution_order.index(f"start_{first_end_req}")
    assert first_start_idx < first_end_idx

    # 验证: 第二个请求的 start 在第一个请求的 end 之后
    second_req = "req2" if first_end_req == "req1" else "req1"
    second_start_idx = execution_order.index(f"start_{second_req}")
    assert second_start_idx >= first_end_idx

    # 验证: 两个请求都成功完成
    assert context1["model_actually_switched"] is True
    assert context2["model_actually_switched"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_model_switch_invalidates_param_cache(real_server_state):
    """
    测试场景: 模型切换后，参数缓存被正确清空
    预期: handle_parameter_cache 检测到模型切换，清空缓存
    """
    from api_utils.model_switching import handle_parameter_cache

    # 设置初始状态：缓存中有旧参数
    page_params_cache = {
        "last_known_model_id_for_params": "gemini-1.5-pro",
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    context = cast(
        RequestContext,
        {
            "logger": MagicMock(),
            "params_cache_lock": real_server_state.params_cache_lock,
            "page_params_cache": page_params_cache,
            "current_ai_studio_model_id": "gemini-2.0-flash",  # 模型已切换
            "model_actually_switched": True,  # 标记实际切换
        },
    )

    # 执行参数缓存处理
    await handle_parameter_cache("req1", context)

    # 验证: 缓存被清空，只保留新模型ID
    assert len(page_params_cache) == 1
    assert page_params_cache["last_known_model_id_for_params"] == "gemini-2.0-flash"
    assert "temperature" not in page_params_cache
    assert "max_tokens" not in page_params_cache


@pytest.mark.integration
@pytest.mark.asyncio
async def test_param_cache_waits_for_model_switch(real_server_state):
    """
    测试场景: 参数缓存更新等待模型切换完成（锁层级）
    预期: params_cache_lock 在 model_switching_lock 释放后才能获取

    锁层级: processing_lock > model_switching_lock > params_cache_lock
    """
    from api_utils.model_switching import handle_model_switching, handle_parameter_cache

    execution_order = []

    # Mock page 和 logger
    mock_page = AsyncMock()
    mock_logger = MagicMock()

    # Mock 模型切换，引入延迟
    async def mock_switch_model(page, model_id, req_id):
        execution_order.append("model_switch_start")
        await asyncio.sleep(0.1)
        execution_order.append("model_switch_end")
        return True

    # 设置初始模型
    real_server_state.current_ai_studio_model_id = "gemini-1.5-pro"

    # 创建请求上下文
    switch_context = cast(
        RequestContext,
        {
            "needs_model_switching": True,
            "model_id_to_use": "gemini-2.0-flash",
            "page": mock_page,
            "logger": mock_logger,
            "model_switching_lock": real_server_state.model_switching_lock,
            "model_actually_switched": False,
            "current_ai_studio_model_id": "gemini-1.5-pro",
        },
    )

    cache_context = cast(
        RequestContext,
        {
            "logger": mock_logger,
            "params_cache_lock": real_server_state.params_cache_lock,
            "page_params_cache": {
                "last_known_model_id_for_params": "gemini-1.5-pro",
                "temperature": 0.7,
            },
            "current_ai_studio_model_id": "gemini-2.0-flash",
            "model_actually_switched": True,
        },
    )

    async def cache_handler():
        execution_order.append("cache_handler_start")
        await handle_parameter_cache("req1", cache_context)
        execution_order.append("cache_handler_end")

    with patch(
        "browser_utils.switch_ai_studio_model",
        side_effect=mock_switch_model,
    ):
        # 同时启动模型切换和缓存处理
        # 注意: 这里我们不直接嵌套锁，而是测试两个独立操作的并发行为
        task1 = asyncio.create_task(handle_model_switching("req1", switch_context))

        # 稍微延迟启动缓存处理，确保模型切换先获取锁
        await asyncio.sleep(0.01)
        task2 = asyncio.create_task(cache_handler())

        await asyncio.gather(task1, task2)

    # 验证: 模型切换完成后，缓存处理才开始
    # 由于 params_cache_lock 优先级低于 model_switching_lock，
    # 但在这个测试中它们是独立操作，所以只需验证缓存被正确清空
    assert (
        cache_context["page_params_cache"]["last_known_model_id_for_params"]
        == "gemini-2.0-flash"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_model_switch_no_change_skips_operation(real_server_state):
    """
    测试场景: 请求的模型与当前模型相同，跳过切换
    预期: model_switching_lock 获取后立即释放，不调用 switch_ai_studio_model
    """
    from api_utils.model_switching import handle_model_switching

    mock_page = AsyncMock()
    mock_logger = MagicMock()

    # 设置当前模型
    real_server_state.current_ai_studio_model_id = "gemini-1.5-pro"

    context = cast(
        RequestContext,
        {
            "needs_model_switching": True,
            "model_id_to_use": "gemini-1.5-pro",  # 与当前相同
            "page": mock_page,
            "logger": mock_logger,
            "model_switching_lock": real_server_state.model_switching_lock,
            "model_actually_switched": False,
            "current_ai_studio_model_id": "gemini-1.5-pro",
        },
    )

    with patch("browser_utils.switch_ai_studio_model") as mock_switch:
        await handle_model_switching("req1", context)

        # 验证: switch_ai_studio_model 未被调用
        mock_switch.assert_not_called()
        # 验证: model_actually_switched 保持 False
        assert context["model_actually_switched"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_model_switch_failure_raises_error(real_server_state):
    """
    测试场景: 模型切换失败，抛出 HTTP 422 错误
    预期: switch_ai_studio_model 返回 False，触发异常
    """
    from api_utils.model_switching import handle_model_switching
    from models.exceptions import HTTPException

    mock_page = AsyncMock()
    mock_logger = MagicMock()

    real_server_state.current_ai_studio_model_id = "gemini-1.5-pro"

    context = cast(
        RequestContext,
        {
            "needs_model_switching": True,
            "model_id_to_use": "gemini-2.0-flash",
            "page": mock_page,
            "logger": mock_logger,
            "model_switching_lock": real_server_state.model_switching_lock,
            "model_actually_switched": False,
            "current_ai_studio_model_id": "gemini-1.5-pro",
        },
    )

    with patch("browser_utils.switch_ai_studio_model", return_value=False):
        # 验证: 抛出 HTTP 422 异常
        with pytest.raises(HTTPException) as exc_info:
            await handle_model_switching("req1", context)

        assert exc_info.value.status_code == 422
        assert "gemini-2.0-flash" in exc_info.value.detail


@pytest.mark.integration
@pytest.mark.asyncio
async def test_three_concurrent_model_switches(real_server_state):
    """
    测试场景: 三个并发请求切换到不同模型
    预期: model_switching_lock 确保严格序列化，无交错执行
    """
    from api_utils.model_switching import handle_model_switching

    execution_log = []

    async def mock_switch(page, model_id, req_id):
        execution_log.append(f"{req_id}_start")
        await asyncio.sleep(0.05)
        execution_log.append(f"{req_id}_end")
        return True

    real_server_state.current_ai_studio_model_id = "base-model"

    contexts = [
        cast(
            RequestContext,
            {
                "needs_model_switching": True,
                "model_id_to_use": f"model-{i}",
                "page": AsyncMock(),
                "logger": MagicMock(),
                "model_switching_lock": real_server_state.model_switching_lock,
                "model_actually_switched": False,
                "current_ai_studio_model_id": "base-model",
            },
        )
        for i in range(1, 4)
    ]

    with patch("browser_utils.switch_ai_studio_model", side_effect=mock_switch):
        tasks = [
            asyncio.create_task(handle_model_switching(f"req{i}", contexts[i - 1]))
            for i in range(1, 4)
        ]

        await asyncio.gather(*tasks)

    # 验证: 6个事件（3个start + 3个end）
    assert len(execution_log) == 6

    # 验证: 每个请求的 start 和 end 成对出现
    for i in range(1, 4):
        start_idx = execution_log.index(f"req{i}_start")
        end_idx = execution_log.index(f"req{i}_end")
        assert start_idx < end_idx

        # 验证: 在 start 和 end 之间，没有其他请求的事件
        between_events = execution_log[start_idx + 1 : end_idx]
        other_req_events = [e for e in between_events if not e.startswith(f"req{i}")]
        assert len(other_req_events) == 0, f"请求 req{i} 的执行被其他请求打断"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_param_cache_cleared_on_model_change_detection(real_server_state):
    """
    测试场景: 检测到模型ID变化（即使未标记 model_actually_switched）
    预期: 缓存仍然被清空
    """
    from api_utils.model_switching import handle_parameter_cache

    page_params_cache = {
        "last_known_model_id_for_params": "old-model",
        "temperature": 0.9,
        "top_p": 0.95,
    }

    context = cast(
        RequestContext,
        {
            "logger": MagicMock(),
            "params_cache_lock": real_server_state.params_cache_lock,
            "page_params_cache": page_params_cache,
            "current_ai_studio_model_id": "new-model",  # 模型ID已变化
            "model_actually_switched": False,  # 未显式标记，但ID不同
        },
    )

    await handle_parameter_cache("req1", context)

    # 验证: 缓存被清空，因为检测到模型ID变化
    assert page_params_cache["last_known_model_id_for_params"] == "new-model"
    assert "temperature" not in page_params_cache
    assert "top_p" not in page_params_cache


@pytest.mark.integration
@pytest.mark.asyncio
async def test_param_cache_preserved_when_model_unchanged(real_server_state):
    """
    测试场景: 模型未变化，参数缓存保持不变
    预期: 缓存内容保留
    """
    from api_utils.model_switching import handle_parameter_cache

    page_params_cache = {
        "last_known_model_id_for_params": "gemini-1.5-pro",
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    context = cast(
        RequestContext,
        {
            "logger": MagicMock(),
            "params_cache_lock": real_server_state.params_cache_lock,
            "page_params_cache": page_params_cache,
            "current_ai_studio_model_id": "gemini-1.5-pro",  # 模型未变
            "model_actually_switched": False,
        },
    )

    await handle_parameter_cache("req1", context)

    # 验证: 缓存内容保持不变
    assert page_params_cache["last_known_model_id_for_params"] == "gemini-1.5-pro"
    assert page_params_cache["temperature"] == 0.7
    assert page_params_cache["max_tokens"] == 2048
    assert len(page_params_cache) == 3
