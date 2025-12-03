from asyncio import Queue
from typing import Any, Dict

from fastapi import Depends
from fastapi.responses import JSONResponse

from config import get_environment_variable

from ..dependencies import get_request_queue, get_server_state, get_worker_task


async def health_check(
    server_state: Dict[str, Any] = Depends(get_server_state),
    worker_task=Depends(get_worker_task),
    request_queue: Queue = Depends(get_request_queue),
) -> JSONResponse:
    is_worker_running = bool(worker_task and not worker_task.done())
    launch_mode = get_environment_variable("LAUNCH_MODE", "unknown")
    browser_page_critical = launch_mode != "direct_debug_no_browser"

    core_ready_conditions = [
        not server_state["is_initializing"],
        server_state["is_playwright_ready"],
    ]
    if browser_page_critical:
        core_ready_conditions.extend(
            [server_state["is_browser_connected"], server_state["is_page_ready"]]
        )

    is_core_ready = all(core_ready_conditions)
    status_val = "OK" if is_core_ready and is_worker_running else "Error"
    q_size = request_queue.qsize() if request_queue else -1

    status_message_parts = []
    if server_state["is_initializing"]:
        status_message_parts.append("初始化进行中")
    if not server_state["is_playwright_ready"]:
        status_message_parts.append("Playwright 未就绪")
    if browser_page_critical:
        if not server_state["is_browser_connected"]:
            status_message_parts.append("浏览器未连接")
        if not server_state["is_page_ready"]:
            status_message_parts.append("页面未就绪")
    if not is_worker_running:
        status_message_parts.append("Worker 未运行")

    status = {
        "status": status_val,
        "message": "",
        "details": {
            **server_state,
            "workerRunning": is_worker_running,
            "queueLength": q_size,
            "launchMode": launch_mode,
            "browserAndPageCritical": browser_page_critical,
        },
    }

    if status_val == "OK":
        status["message"] = f"服务运行中;队列长度: {q_size}。"
        return JSONResponse(content=status, status_code=200)
    else:
        status["message"] = (
            f"服务不可用;问题: {(', '.join(status_message_parts) or '未知原因')}. 队列长度: {q_size}."
        )
        return JSONResponse(content=status, status_code=503)
