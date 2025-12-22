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
    Test scenario: result_future.wait throws HTTPException (status_code=499)
    Expected: Log client disconnect and re-throw exception (lines 71-76, 72-73)
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

    # Execute
    with pytest.raises(HTTPException) as excinfo:
        await chat_completions(
            request=request,
            http_request=http_request,
            logger=logger,
            request_queue=request_queue,
            server_state=server_state,
            worker_task=worker_task,
        )

    # Verify: status_code=499 (lines 71-76)
    assert excinfo.value.status_code == 499
    assert "Client disconnected" in str(excinfo.value.detail)

    # Verify: logger.info called twice (line 31 and line 73)
    assert logger.info.call_count == 2
    # Second call contains disconnect message (line 73)
    assert "Client disconnected" in logger.info.call_args[0][0]


@pytest.mark.asyncio
async def test_chat_completions_http_exception_non_499():
    """
    Test scenario: result_future.wait throws HTTPException (status_code != 499)
    Expected: Log HTTP exception warning and re-throw exception (lines 71-76, 74-75)
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

    # Execute
    with pytest.raises(HTTPException) as excinfo:
        await chat_completions(
            request=request,
            http_request=http_request,
            logger=logger,
            request_queue=request_queue,
            server_state=server_state,
            worker_task=worker_task,
        )

    # Verify: status_code=400 (lines 71-76)
    assert excinfo.value.status_code == 400
    assert "Bad request" in str(excinfo.value.detail)

    # Verify: logger.warning called (line 75)
    # logger.info will also be called once (line 31), but we only care about warning
    assert logger.warning.call_count >= 1
    # Last warning call contains HTTP exception message (line 75)
    assert "HTTP exception" in logger.warning.call_args[0][0]


@pytest.mark.asyncio
async def test_chat_completions_generic_exception():
    """
    Test scenario: result_future.wait throws non-HTTPException
    Expected: Log exception and convert to 500 error (lines 77-79)
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

    # Execute
    with pytest.raises(HTTPException) as excinfo:
        await chat_completions(
            request=request,
            http_request=http_request,
            logger=logger,
            request_queue=request_queue,
            server_state=server_state,
            worker_task=worker_task,
        )

    # Verify: Convert to 500 error (line 79)
    assert excinfo.value.status_code == 500
    assert "Internal server error" in str(excinfo.value.detail)
    assert "Unexpected error" in str(excinfo.value.detail)

    # Verify: logger.exception called (line 78)
    assert logger.exception.call_count >= 1
    # Last exception call contains error message while waiting for response (line 78)
    assert "Error waiting for Worker response" in logger.exception.call_args[0][0]
