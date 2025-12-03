import logging
import time
from asyncio import Lock, Queue

from fastapi import Depends
from fastapi.responses import JSONResponse

from logging_utils import set_request_id

from ..dependencies import get_logger, get_processing_lock, get_request_queue
from ..error_utils import client_cancelled


async def cancel_queued_request(
    req_id: str, request_queue: Queue, logger: logging.Logger
) -> bool:
    set_request_id(req_id)
    items_to_requeue = []
    found = False
    try:
        while not request_queue.empty():
            item = request_queue.get_nowait()
            if item.get("req_id") == req_id:
                logger.info("在队列中找到请求，标记为已取消。")
                item["cancelled"] = True
                if (future := item.get("result_future")) and not future.done():
                    future.set_exception(client_cancelled(req_id))
                found = True
            items_to_requeue.append(item)
    finally:
        for item in items_to_requeue:
            await request_queue.put(item)
    return found


async def cancel_request(
    req_id: str,
    logger: logging.Logger = Depends(get_logger),
    request_queue: Queue = Depends(get_request_queue),
):
    set_request_id(req_id)
    logger.info("收到取消请求。")
    if await cancel_queued_request(req_id, request_queue, logger):
        return JSONResponse(
            content={
                "success": True,
                "message": f"Request {req_id} marked as cancelled.",
            }
        )
    else:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": f"Request {req_id} not found in queue.",
            },
        )


async def get_queue_status(
    request_queue: Queue = Depends(get_request_queue),
    processing_lock: Lock = Depends(get_processing_lock),
):
    # Extract all items temporarily to inspect queue contents
    queue_items = []
    try:
        while not request_queue.empty():
            item = request_queue.get_nowait()
            queue_items.append(item)
    except Exception:
        pass
    finally:
        # Put all items back in original order
        for item in queue_items:
            await request_queue.put(item)

    queue_length = len(queue_items)

    return JSONResponse(
        content={
            "queue_length": queue_length,
            "is_processing_locked": processing_lock.locked(),
            "items": sorted(
                [
                    {
                        "req_id": item.get("req_id", "unknown"),
                        "enqueue_time": item.get("enqueue_time", 0),
                        "wait_time_seconds": round(
                            time.time() - item.get("enqueue_time", 0), 2
                        ),
                        "is_streaming": item.get("request_data").stream,
                        "cancelled": item.get("cancelled", False),
                    }
                    for item in queue_items
                ],
                key=lambda x: x.get("enqueue_time", 0),
            ),
        }
    )
