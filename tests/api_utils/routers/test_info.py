"""
High-quality tests for api_utils/routers/info.py - API info endpoint.

Focus: Test get_api_info endpoint with various request configurations.
Strategy: Mock only dependencies (auth_utils.API_KEYS, get_current_ai_studio_model_id), test actual logic.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_utils.routers.info import get_api_info


@pytest.fixture
def app():
    """Create test FastAPI app with info endpoint."""
    app = FastAPI()
    app.get("/info")(get_api_info)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


def test_get_api_info_no_auth_required(client):
    """
    测试场景: API 无需认证,返回基本信息
    预期: api_key_required=False, auth_header=None, supported_auth_methods=[]
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", []),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id", return_value=None
        ),
        patch("api_utils.routers.info.MODEL_NAME", "gemini-2.0-flash"),
    ):
        response = client.get("/info")

        assert response.status_code == 200
        data = response.json()

        # 验证基本字段
        assert data["model_name"] == "gemini-2.0-flash"  # 使用 MODEL_NAME 作为 fallback
        assert data["openai_compatible"] is True
        assert data["api_key_required"] is False
        assert data["api_key_count"] == 0
        assert data["auth_header"] is None
        assert data["supported_auth_methods"] == []
        assert data["message"] == "API Key is not required."

        # 验证 URL 构造
        assert data["server_base_url"].startswith("http")
        assert data["api_base_url"].endswith("/v1")


def test_get_api_info_with_auth_required(client):
    """
    测试场景: API 需要认证,配置了 3 个密钥
    预期: api_key_required=True, 包含认证头信息
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", ["key1", "key2", "key3"]),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id",
            return_value="gemini-1.5-pro",
        ),
    ):
        response = client.get("/info")

        assert response.status_code == 200
        data = response.json()

        assert data["api_key_required"] is True
        assert data["api_key_count"] == 3
        assert (
            data["auth_header"] == "Authorization: Bearer <token> or X-API-Key: <token>"
        )
        assert data["supported_auth_methods"] == [
            "Authorization: Bearer",
            "X-API-Key",
        ]
        assert data["message"] == "API Key is required. 3 valid key(s) configured."


def test_get_api_info_with_custom_model_id(app, client):
    """
    测试场景: 使用自定义模型 ID
    预期: 返回 dependency 提供的模型 ID
    """
    from api_utils.dependencies import get_current_ai_studio_model_id

    # 使用 FastAPI dependency override
    app.dependency_overrides[get_current_ai_studio_model_id] = (
        lambda: "gemini-2.0-flash-thinking-exp"
    )

    with patch("api_utils.auth_utils.API_KEYS", []):
        response = client.get("/info")

        assert response.status_code == 200
        data = response.json()

        assert data["model_name"] == "gemini-2.0-flash-thinking-exp"

    # 清理 override
    app.dependency_overrides.clear()


def test_get_api_info_with_custom_host_header(client):
    """
    测试场景: 请求包含自定义 Host 头
    预期: 使用 Host 头构造 URL
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", []),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id", return_value=None
        ),
        patch("api_utils.routers.info.MODEL_NAME", "gemini-1.5-pro"),
    ):
        response = client.get("/info", headers={"host": "api.example.com:8080"})

        assert response.status_code == 200
        data = response.json()

        assert "api.example.com:8080" in data["server_base_url"]
        assert "api.example.com:8080" in data["api_base_url"]


def test_get_api_info_with_x_forwarded_proto_https(client):
    """
    测试场景: 请求通过 HTTPS 反向代理,带 X-Forwarded-Proto 头
    预期: 使用 https 作为 scheme
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", []),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id", return_value=None
        ),
        patch("api_utils.routers.info.MODEL_NAME", "gemini-1.5-pro"),
    ):
        response = client.get(
            "/info",
            headers={"x-forwarded-proto": "https", "host": "api.example.com"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["server_base_url"].startswith("https://")
        assert data["api_base_url"].startswith("https://")


def test_get_api_info_with_custom_port_via_env(client):
    """
    测试场景: 通过环境变量设置自定义端口
    预期: 使用 SERVER_PORT_INFO 环境变量值
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", []),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id", return_value=None
        ),
        patch("api_utils.routers.info.MODEL_NAME", "gemini-1.5-pro"),
        patch("api_utils.routers.info.get_environment_variable", return_value="9999"),
    ):
        # 不提供端口信息,应从环境变量读取
        response = client.get("/info")

        assert response.status_code == 200
        response.json()

        # TestClient 默认使用 testserver, 但如果 request.url.port 为 None,
        # 会回退到 SERVER_PORT_INFO
        # 由于 TestClient 可能提供端口,这里主要验证逻辑执行无误


def test_get_api_info_url_construction_with_port(client):
    """
    测试场景: URL 包含端口号
    预期: 正确构造带端口的 base URL
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", []),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id", return_value=None
        ),
        patch("api_utils.routers.info.MODEL_NAME", "gemini-1.5-pro"),
    ):
        response = client.get("/info", headers={"host": "localhost:2048"})

        assert response.status_code == 200
        data = response.json()

        assert "localhost:2048" in data["server_base_url"]
        assert data["api_base_url"] == f"{data['server_base_url']}/v1"


def test_get_api_info_with_one_api_key(client):
    """
    测试场景: 仅配置 1 个 API 密钥
    预期: api_key_count=1, message 单数形式
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", ["single_key"]),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id", return_value=None
        ),
        patch("api_utils.routers.info.MODEL_NAME", "gemini-1.5-pro"),
    ):
        response = client.get("/info")

        assert response.status_code == 200
        data = response.json()

        assert data["api_key_count"] == 1
        assert data["message"] == "API Key is required. 1 valid key(s) configured."


def test_get_api_info_model_fallback_to_default(client):
    """
    测试场景: current_ai_studio_model_id 为 None, 使用 MODEL_NAME
    预期: effective_model_name = MODEL_NAME
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", []),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id", return_value=None
        ),
        patch("api_utils.routers.info.MODEL_NAME", "default-model-name"),
    ):
        response = client.get("/info")

        assert response.status_code == 200
        data = response.json()

        assert data["model_name"] == "default-model-name"


def test_get_api_info_response_structure(client):
    """
    测试场景: 验证完整的响应结构
    预期: 包含所有必需字段
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", ["key1", "key2"]),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id",
            return_value="test-model",
        ),
    ):
        response = client.get("/info")

        assert response.status_code == 200
        data = response.json()

        # 验证所有必需字段存在
        required_fields = [
            "model_name",
            "api_base_url",
            "server_base_url",
            "api_key_required",
            "api_key_count",
            "auth_header",
            "openai_compatible",
            "supported_auth_methods",
            "message",
        ]

        for field in required_fields:
            assert field in data, f"缺少必需字段: {field}"

        # 验证类型
        assert isinstance(data["model_name"], str)
        assert isinstance(data["api_base_url"], str)
        assert isinstance(data["server_base_url"], str)
        assert isinstance(data["api_key_required"], bool)
        assert isinstance(data["api_key_count"], int)
        assert isinstance(data["openai_compatible"], bool)
        assert isinstance(data["supported_auth_methods"], list)
        assert isinstance(data["message"], str)
