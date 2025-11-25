from fastapi import HTTPException
from playwright.async_api import Page as AsyncPage
from playwright.async_api import expect as expect_async, Error as PlaywrightAsyncError
import asyncio

from config import RESPONSE_CONTAINER_SELECTOR, RESPONSE_TEXT_SELECTOR


async def locate_response_elements(page: AsyncPage, req_id: str, logger, check_client_disconnected) -> None:
    """定位响应容器与文本元素，包含超时与错误处理。"""
    logger.info(f"[{req_id}] Locating response elements...")
    response_container = page.locator(RESPONSE_CONTAINER_SELECTOR).last
    response_element = response_container.locator(RESPONSE_TEXT_SELECTOR)

    try:
        await expect_async(response_container).to_be_attached(timeout=20000)
        check_client_disconnected("After Response Container Attached: ")
        await expect_async(response_element).to_be_attached(timeout=90000)
        logger.info(f"[{req_id}] Response elements located.")
    except (PlaywrightAsyncError, asyncio.TimeoutError) as locate_err:
        from .error_utils import upstream_error
        raise upstream_error(req_id, f"Failed to locate AI Studio response elements: {locate_err}")
    except Exception as locate_exc:
        from .error_utils import server_error
        raise server_error(req_id, f"Unexpected error while locating response elements: {locate_exc}")
