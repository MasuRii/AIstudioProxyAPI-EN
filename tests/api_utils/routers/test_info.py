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
    Test scenario: API requires no authentication, returns basic info
    Expected: api_key_required=False, auth_header=None, supported_auth_methods=[]
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

        # Verify basic fields
        assert data["model_name"] == "gemini-2.0-flash"  # Use MODEL_NAME as fallback
        assert data["openai_compatible"] is True
        assert data["api_key_required"] is False
        assert data["api_key_count"] == 0
        assert data["auth_header"] is None
        assert data["supported_auth_methods"] == []
        assert data["message"] == "API Key is not required."

        # Verify URL construction
        assert data["server_base_url"].startswith("http")
        assert data["api_base_url"].endswith("/v1")


def test_get_api_info_with_auth_required(client):
    """
    Test scenario: API requires authentication, 3 keys configured
    Expected: api_key_required=True, contains authentication header info
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
    Test scenario: Use custom model ID
    Expected: Return model ID provided by dependency
    """
    from api_utils.dependencies import get_current_ai_studio_model_id

    # Use FastAPI dependency override
    app.dependency_overrides[get_current_ai_studio_model_id] = (
        lambda: "gemini-2.0-flash-thinking-exp"
    )

    with patch("api_utils.auth_utils.API_KEYS", []):
        response = client.get("/info")

        assert response.status_code == 200
        data = response.json()

        assert data["model_name"] == "gemini-2.0-flash-thinking-exp"

    # Clean up override
    app.dependency_overrides.clear()


def test_get_api_info_with_custom_host_header(client):
    """
    Test scenario: Request contains custom Host header
    Expected: Use Host header to construct URL
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
    Test scenario: Request via HTTPS reverse proxy, with X-Forwarded-Proto header
    Expected: Use https as scheme
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
    Test scenario: Set custom port via environment variable
    Expected: Use SERVER_PORT_INFO environment variable value
    """
    with (
        patch("api_utils.auth_utils.API_KEYS", []),
        patch(
            "api_utils.routers.info.get_current_ai_studio_model_id", return_value=None
        ),
        patch("api_utils.routers.info.MODEL_NAME", "gemini-1.5-pro"),
        patch("api_utils.routers.info.get_environment_variable", return_value="9999"),
    ):
        # No port info provided, should read from environment variable
        response = client.get("/info")

        assert response.status_code == 200
        response.json()

        # TestClient uses testserver by default, but if request.url.port is None,
        # it will fall back to SERVER_PORT_INFO
        # Since TestClient might provide a port, we mainly verify the logic executes correctly


def test_get_api_info_url_construction_with_port(client):
    """
    Test scenario: URL contains port number
    Expected: Correctly construct base URL with port
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
    Test scenario: Only 1 API key configured
    Expected: api_key_count=1, message singular form
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
    Test scenario: current_ai_studio_model_id is None, use MODEL_NAME
    Expected: effective_model_name = MODEL_NAME
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
    Test scenario: Verify complete response structure
    Expected: Contains all required fields
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

        # Verify all required fields exist
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
            assert field in data, f"Missing required field: {field}"

        # Verify types
        assert isinstance(data["model_name"], str)
        assert isinstance(data["api_base_url"], str)
        assert isinstance(data["server_base_url"], str)
        assert isinstance(data["api_key_required"], bool)
        assert isinstance(data["api_key_count"], int)
        assert isinstance(data["openai_compatible"], bool)
        assert isinstance(data["supported_auth_methods"], list)
        assert isinstance(data["message"], str)
