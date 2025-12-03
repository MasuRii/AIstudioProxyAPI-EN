import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api_utils.routers.chat import chat_completions
from models import ChatCompletionRequest, Message


@pytest.mark.asyncio
async def test_chat_completions_success():
    request = ChatCompletionRequest(
        messages=[Message(role="user", content="hello")], model="gpt-4"
    )
    http_request = MagicMock()
    logger = MagicMock()
    request_queue = asyncio.Queue()
    server_state = {
        "is_initializing": False,
        "is_playwright_ready": True,
        "is_page_ready": True,
        "is_browser_connected": True,
    }
    worker_task = MagicMock()
    worker_task.done.return_value = False

    # Simulate worker processing
    async def process_queue():
        item = await request_queue.get()
        item["result_future"].set_result({"response": "ok"})

    asyncio.create_task(process_queue())

    response = await chat_completions(
        request=request,
        http_request=http_request,
        logger=logger,
        request_queue=request_queue,
        server_state=server_state,
        worker_task=worker_task,
    )

    assert response == {"response": "ok"}


@pytest.mark.asyncio
async def test_chat_completions_service_unavailable():
    request = ChatCompletionRequest(
        messages=[Message(role="user", content="hello")], model="gpt-4"
    )
    http_request = MagicMock()
    logger = MagicMock()
    request_queue = asyncio.Queue()
    server_state = {
        "is_initializing": True,  # Service unavailable
        "is_playwright_ready": True,
        "is_page_ready": True,
        "is_browser_connected": True,
    }
    worker_task = MagicMock()
    worker_task.done.return_value = False

    with pytest.raises(HTTPException) as excinfo:
        await chat_completions(
            request=request,
            http_request=http_request,
            logger=logger,
            request_queue=request_queue,
            server_state=server_state,
            worker_task=worker_task,
        )
    assert excinfo.value.status_code == 503


@pytest.mark.asyncio
async def test_chat_completions_timeout():
    # Mock asyncio.wait_for to raise TimeoutError immediately
    async def mock_wait_for(fut, timeout):
        raise asyncio.TimeoutError()

    request = ChatCompletionRequest(
        messages=[Message(role="user", content="hello")], model="gpt-4"
    )
    http_request = MagicMock()
    logger = MagicMock()
    request_queue = asyncio.Queue()
    server_state = {
        "is_initializing": False,
        "is_playwright_ready": True,
        "is_page_ready": True,
        "is_browser_connected": True,
    }
    worker_task = MagicMock()
    worker_task.done.return_value = False

    with patch("asyncio.wait_for", new=mock_wait_for):
        with pytest.raises(HTTPException) as excinfo:
            await chat_completions(
                request=request,
                http_request=http_request,
                logger=logger,
                request_queue=request_queue,
                server_state=server_state,
                worker_task=worker_task,
            )
    assert excinfo.value.status_code == 504


@pytest.mark.asyncio
async def test_chat_completions_cancelled():
    request = ChatCompletionRequest(
        messages=[Message(role="user", content="hello")], model="gpt-4"
    )
    http_request = MagicMock()
    logger = MagicMock()
    request_queue = asyncio.Queue()
    server_state = {
        "is_initializing": False,
        "is_playwright_ready": True,
        "is_page_ready": True,
        "is_browser_connected": True,
    }
    worker_task = MagicMock()
    worker_task.done.return_value = False

    # Simulate cancellation
    async def cancel_request():
        item = await request_queue.get()
        item["result_future"].cancel()

    asyncio.create_task(cancel_request())

    with pytest.raises(asyncio.CancelledError):
        await chat_completions(
            request=request,
            http_request=http_request,
            logger=logger,
            request_queue=request_queue,
            server_state=server_state,
            worker_task=worker_task,
        )


"""
Extended tests for api_utils/routers/chat.py - Exception handling coverage.

Focus: Cover lines 71-79 (HTTPException and generic Exception handlers).
Strategy: Mock result_future to raise exceptions when awaited.
"""


@pytest.mark.asyncio
async def test_chat_completions_http_exception_499():
    """
    测试场景: result_future.wait 抛出 HTTPException (status_code=499)
    预期: 记录客户端断开日志,重新抛出异常 (lines 71-76, 72-73)
    """
    request = ChatCompletionRequest(
        messages=[Message(role="user", content="hello")], model="gpt-4"
    )
    http_request = MagicMock()
    logger = MagicMock()
    request_queue = asyncio.Queue()
    server_state = {
        "is_initializing": False,
        "is_playwright_ready": True,
        "is_page_ready": True,
        "is_browser_connected": True,
    }
    worker_task = MagicMock()
    worker_task.done.return_value = False

    # Simulate worker raising HTTPException with 499
    async def process_queue():
        item = await request_queue.get()
        item["result_future"].set_exception(
            HTTPException(status_code=499, detail="Client disconnected")
        )

    asyncio.create_task(process_queue())

    # 执行
    with pytest.raises(HTTPException) as excinfo:
        await chat_completions(
            request=request,
            http_request=http_request,
            logger=logger,
            request_queue=request_queue,
            server_state=server_state,
            worker_task=worker_task,
        )

    # 验证: status_code=499 (lines 71-76)
    assert excinfo.value.status_code == 499
    assert "Client disconnected" in str(excinfo.value.detail)

    # 验证: logger.info 被调用两次 (line 31 和 line 73)
    assert logger.info.call_count == 2
    # 第二次调用包含断开连接消息 (line 73)
    assert "客户端断开连接" in logger.info.call_args[0][0]


@pytest.mark.asyncio
async def test_chat_completions_http_exception_non_499():
    """
    测试场景: result_future.wait 抛出 HTTPException (status_code != 499)
    预期: 记录 HTTP 异常警告,重新抛出异常 (lines 71-76, 74-75)
    """
    request = ChatCompletionRequest(
        messages=[Message(role="user", content="hello")], model="gpt-4"
    )
    http_request = MagicMock()
    logger = MagicMock()
    request_queue = asyncio.Queue()
    server_state = {
        "is_initializing": False,
        "is_playwright_ready": True,
        "is_page_ready": True,
        "is_browser_connected": True,
    }
    worker_task = MagicMock()
    worker_task.done.return_value = False

    # Simulate worker raising HTTPException with 400
    async def process_queue():
        item = await request_queue.get()
        item["result_future"].set_exception(
            HTTPException(status_code=400, detail="Bad request")
        )

    asyncio.create_task(process_queue())

    # 执行
    with pytest.raises(HTTPException) as excinfo:
        await chat_completions(
            request=request,
            http_request=http_request,
            logger=logger,
            request_queue=request_queue,
            server_state=server_state,
            worker_task=worker_task,
        )

    # 验证: status_code=400 (lines 71-76)
    assert excinfo.value.status_code == 400
    assert "Bad request" in str(excinfo.value.detail)

    # 验证: logger.warning 被调用 (line 75)
    # logger.info 也会被调用一次 (line 31), 但我们只关注 warning
    assert logger.warning.call_count >= 1
    # 最后一次 warning 调用包含 HTTP 异常消息 (line 75)
    assert "HTTP异常" in logger.warning.call_args[0][0]


@pytest.mark.asyncio
async def test_chat_completions_generic_exception():
    """
    测试场景: result_future.wait 抛出 非 HTTPException 的异常
    预期: 记录异常,转换为 500 错误 (lines 77-79)
    """
    request = ChatCompletionRequest(
        messages=[Message(role="user", content="hello")], model="gpt-4"
    )
    http_request = MagicMock()
    logger = MagicMock()
    request_queue = asyncio.Queue()
    server_state = {
        "is_initializing": False,
        "is_playwright_ready": True,
        "is_page_ready": True,
        "is_browser_connected": True,
    }
    worker_task = MagicMock()
    worker_task.done.return_value = False

    # Simulate worker raising generic Exception
    async def process_queue():
        item = await request_queue.get()
        item["result_future"].set_exception(ValueError("Unexpected error"))

    asyncio.create_task(process_queue())

    # 执行
    with pytest.raises(HTTPException) as excinfo:
        await chat_completions(
            request=request,
            http_request=http_request,
            logger=logger,
            request_queue=request_queue,
            server_state=server_state,
            worker_task=worker_task,
        )

    # 验证: 转换为 500 错误 (line 79)
    assert excinfo.value.status_code == 500
    assert "服务器内部错误" in str(excinfo.value.detail)
    assert "Unexpected error" in str(excinfo.value.detail)

    # 验证: logger.exception 被调用 (line 78)
    assert logger.exception.call_count >= 1
    # 最后一次 exception 调用包含等待响应错误消息 (line 78)
    assert "等待Worker响应时出错" in logger.exception.call_args[0][0]
