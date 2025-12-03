"""
High-quality tests for api_utils/routers/static.py - Static file serving.

Focus: Test static file endpoints with both success and error paths.
Strategy: Mock os.path.exists to control file existence, test actual routing logic.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api_utils.routers.static import get_css, get_js, read_index


@pytest.fixture
def app():
    """Create test FastAPI app with static endpoints."""
    app = FastAPI()
    app.get("/")(read_index)
    app.get("/css")(get_css)
    app.get("/js")(get_js)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


def test_read_index_success(client):
    """
    测试场景: index.html 存在,正常返回
    预期: 返回 FileResponse with index.html
    """
    with patch("api_utils.routers.static.os.path.exists", return_value=True):
        response = client.get("/")

        assert response.status_code == 200
        # FileResponse 返回文件内容,无需检查具体内容


def test_read_index_not_found(client):
    """
    测试场景: index.html 不存在
    预期: 返回 404 错误 (lines 18-20)
    """
    MagicMock()

    with patch("api_utils.routers.static.os.path.exists", return_value=False):
        response = client.get("/")

        assert response.status_code == 404
        assert response.json()["detail"] == "index.html not found"


def test_get_css_success(client):
    """
    测试场景: webui.css 存在,正常返回
    预期: 返回 FileResponse with text/css media type
    """
    with patch("api_utils.routers.static.os.path.exists", return_value=True):
        response = client.get("/css")

        assert response.status_code == 200
        # TestClient 会自动处理 FileResponse


def test_get_css_not_found(client):
    """
    测试场景: webui.css 不存在
    预期: 返回 404 错误 (lines 26-28)
    """
    MagicMock()

    with patch("api_utils.routers.static.os.path.exists", return_value=False):
        response = client.get("/css")

        assert response.status_code == 404
        assert response.json()["detail"] == "webui.css not found"


def test_get_js_success(client):
    """
    测试场景: webui.js 存在,正常返回
    预期: 返回 FileResponse with application/javascript media type
    """
    with patch("api_utils.routers.static.os.path.exists", return_value=True):
        response = client.get("/js")

        assert response.status_code == 200
        # TestClient 会自动处理 FileResponse


def test_get_js_not_found(client):
    """
    测试场景: webui.js 不存在
    预期: 返回 404 错误 (lines 34-36)
    """
    MagicMock()

    with patch("api_utils.routers.static.os.path.exists", return_value=False):
        response = client.get("/js")

        assert response.status_code == 404
        assert response.json()["detail"] == "webui.js not found"


def test_static_path_helper():
    """
    测试场景: 测试 _static_path() 辅助函数
    预期: 正确构造静态文件路径 (line 13)
    """
    from api_utils.routers.static import _static_path

    result = _static_path("static/index.html")

    # 验证路径包含预期的部分
    assert "static" in result
    assert "index.html" in result
    assert os.path.isabs(result) or "\\" in result or "/" in result


def test_index_logger_called_on_error(client):
    """
    测试场景: index.html 不存在时,logger.error 被调用
    预期: 记录错误消息 (line 19)
    """
    logger = MagicMock()

    with (
        patch("api_utils.routers.static.os.path.exists", return_value=False),
        patch("api_utils.routers.static.get_logger", return_value=lambda: logger),
    ):
        # 直接调用函数而不是通过 TestClient
        with pytest.raises(HTTPException) as exc_info:
            import asyncio

            asyncio.run(read_index(logger=logger))

        assert exc_info.value.status_code == 404
        logger.error.assert_called_once()
        error_call_args = logger.error.call_args[0][0]
        assert "index.html not found" in error_call_args


def test_css_logger_called_on_error(client):
    """
    测试场景: webui.css 不存在时,logger.error 被调用
    预期: 记录错误消息 (line 27)
    """
    logger = MagicMock()

    with patch("api_utils.routers.static.os.path.exists", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            import asyncio

            asyncio.run(get_css(logger=logger))

        assert exc_info.value.status_code == 404
        logger.error.assert_called_once()
        error_call_args = logger.error.call_args[0][0]
        assert "webui.css not found" in error_call_args


def test_js_logger_called_on_error(client):
    """
    测试场景: webui.js 不存在时,logger.error 被调用
    预期: 记录错误消息 (line 35)
    """
    logger = MagicMock()

    with patch("api_utils.routers.static.os.path.exists", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            import asyncio

            asyncio.run(get_js(logger=logger))

        assert exc_info.value.status_code == 404
        logger.error.assert_called_once()
        error_call_args = logger.error.call_args[0][0]
        assert "webui.js not found" in error_call_args
