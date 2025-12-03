import asyncio
import logging
import random
import time
from asyncio import Future, Queue
from typing import Any

from fastapi import Depends, HTTPException, Request
from ..dependencies import get_logger, get_request_queue, get_server_state, get_worker_task, ensure_request_lock
from config import RESPONSE_COMPLETION_TIMEOUT
from config.global_state import GlobalState
from models import ChatCompletionRequest
import asyncio
from fastapi.responses import JSONResponse

from config import RESPONSE_COMPLETION_TIMEOUT, get_environment_variable
from logging_utils import set_request_id, set_source
from models import ChatCompletionRequest

from ..dependencies import (
    get_logger,
    get_request_queue,
    get_server_state,
    get_worker_task,
)
from ..error_utils import service_unavailable


async def chat_completions(
    request: ChatCompletionRequest,
    http_request: Request,
    logger: logging.Logger = Depends(get_logger),
    request_queue: Queue = Depends(get_request_queue),
    server_state: dict = Depends(get_server_state),
    worker_task = Depends(get_worker_task),
    _lock: None = Depends(ensure_request_lock)
) -> JSONResponse:
    req_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=7))

    # 设置日志上下文 (Grid Logger)
    set_request_id(req_id)
    set_source("API")

    logger.info(f"收到 /v1/chat/completions 请求 (Stream={request.stream})")

    launch_mode = get_environment_variable("LAUNCH_MODE", "unknown")
    browser_page_critical = launch_mode != "direct_debug_no_browser"

    is_service_unavailable = (
        server_state["is_initializing"]
        or not server_state["is_playwright_ready"]
        or (
            browser_page_critical
            and (
                not server_state["is_page_ready"]
                or not server_state["is_browser_connected"]
            )
        )
        or not worker_task
        or worker_task.done()
    )

    if is_service_unavailable:
        raise service_unavailable(req_id)

    result_future = Future()
    queue_item = {
        "req_id": req_id,
        "request_data": request,
        "http_request": http_request,
        "result_future": result_future,
        "enqueue_time": time.time(),
        "cancelled": False,
    }
    await request_queue.put(queue_item)

    try:
        timeout_seconds = RESPONSE_COMPLETION_TIMEOUT / 1000 + 120
        return await asyncio.wait_for(result_future, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"[{req_id}] 请求处理超时。")
    except asyncio.CancelledError:
        logger.info(f"请求被客户端取消: {req_id}")
        raise
    except HTTPException as http_exc:
        if http_exc.status_code == 499:
            logger.info(f"客户端断开连接: {http_exc.detail}")
        else:
            logger.warning(f"HTTP异常: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.exception("等待Worker响应时出错")
        raise HTTPException(status_code=500, detail=f"[{req_id}] 服务器内部错误: {e}")
