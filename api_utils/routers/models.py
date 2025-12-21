import asyncio
import logging
import time
from asyncio import Event
from typing import Any, Dict, List, Set

from fastapi import Depends
from playwright.async_api import Page as AsyncPage

from config import DEFAULT_FALLBACK_MODEL_ID

from ..dependencies import (
    get_excluded_model_ids,
    get_logger,
    get_model_list_fetch_event,
    get_page_instance,
    get_parsed_model_list,
    ensure_request_lock,
)


async def list_models(
    logger: logging.Logger = Depends(get_logger),
    model_list_fetch_event: Event = Depends(get_model_list_fetch_event),
    page_instance: AsyncPage = Depends(get_page_instance),
    parsed_model_list: List[Dict[str, Any]] = Depends(get_parsed_model_list),
    excluded_model_ids: Set[str] = Depends(get_excluded_model_ids),
    _lock: None = Depends(ensure_request_lock),
):
    logger.debug("[API] Received /v1/models request.")

    if (
        not model_list_fetch_event.is_set()
        and page_instance
        and not page_instance.is_closed()
    ):
        logger.info(
            "/v1/models: Model list event not set, attempting to refresh page..."
        )
        try:
            await page_instance.reload(wait_until="domcontentloaded", timeout=20000)
            await asyncio.wait_for(model_list_fetch_event.wait(), timeout=10.0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"/v1/models: Error refreshing or waiting for model list: {e}")
        finally:
            if not model_list_fetch_event.is_set():
                model_list_fetch_event.set()

    if parsed_model_list:
        final_model_list = [
            m
            for m in parsed_model_list
            if isinstance(m, dict) and m.get("id") not in excluded_model_ids
        ]
        return {"object": "list", "data": final_model_list}
    else:
        logger.warning("Model list is empty, returning default fallback model.")
        return {
            "object": "list",
            "data": [
                {
                    "id": DEFAULT_FALLBACK_MODEL_ID,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "camoufox-proxy-fallback",
                }
            ],
        }
