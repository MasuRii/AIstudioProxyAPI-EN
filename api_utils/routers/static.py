import logging
import os

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse

from ..dependencies import get_logger

_BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")


def _static_path(name: str) -> str:
    return os.path.join(_BASE_DIR, name)


async def read_index(logger: logging.Logger = Depends(get_logger)):
    index_html_path = _static_path("static/index.html")
    if not os.path.exists(index_html_path):
        logger.error(f"index.html not found at {index_html_path}")
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_html_path)


async def get_css(logger: logging.Logger = Depends(get_logger)):
    css_path = _static_path("static/css/webui.css")
    if not os.path.exists(css_path):
        logger.error(f"webui.css not found at {css_path}")
        raise HTTPException(status_code=404, detail="webui.css not found")
    return FileResponse(css_path, media_type="text/css")


async def get_js(logger: logging.Logger = Depends(get_logger)):
    js_path = _static_path("static/js/webui.js")
    if not os.path.exists(js_path):
        logger.error(f"webui.js not found at {js_path}")
        raise HTTPException(status_code=404, detail="webui.js not found")
    return FileResponse(js_path, media_type="application/javascript")
