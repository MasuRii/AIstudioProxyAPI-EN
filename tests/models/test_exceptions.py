"""
Tests for models/exceptions.py - Exception Hierarchy

Tests the comprehensive exception system including:
- HTTP status code assignment
- Rich error context
- to_http_exception() conversion
- Retry-After headers
- Error inheritance hierarchy
"""

import time

import pytest
from fastapi import HTTPException

from models.exceptions import (
    AIStudioError,
    # Base
    AIStudioProxyError,
    BrowserCrashedError,
    # Browser errors
    BrowserError,
    BrowserInitError,
    # Client errors
    ClientDisconnectedError,
    # Configuration errors
    ConfigurationError,
    EmptyResponseError,
    InvalidConfigError,
    InvalidModelError,
    InvalidParameterError,
    MissingConfigError,
    MissingParameterError,
    # Model errors
    ModelError,
    ModelListError,
    ModelSwitchError,
    PageNotReadyError,
    ProcessingTimeoutError,
    ProxyConnectionError,
    QueueFullError,
    QuotaExceededError,
    # Resource errors
    ResourceError,
    ResponseTimeoutError,
    SelectorNotFoundError,
    # Stream errors
    StreamError,
    StreamTimeoutError,
    # Timeout errors
    TimeoutError,
    # Upstream errors
    UpstreamError,
    # Validation errors
    ValidationError,
)

# ==================== BASE EXCEPTION TESTS ====================


def test_base_exception_basic():
    """Test basic AIStudioProxyError attributes."""
    error = AIStudioProxyError(message="Test error", req_id="test123", http_status=500)

    assert error.message == "Test error"
    assert error.req_id == "test123"
    assert error.http_status == 500
    assert error.retry_after is None
    assert isinstance(error.timestamp, float)
    assert str(error) == "[test123] Test error"


def test_base_exception_with_context():
    """Test AIStudioProxyError with custom context."""
    error = AIStudioProxyError(
        message="Error", req_id="abc", custom_field="value", another_field=123
    )

    assert error.context == {"custom_field": "value", "another_field": 123}


def test_base_exception_to_http():
    """Test conversion to HTTPException."""
    error = AIStudioProxyError(
        message="Server error", req_id="req1", http_status=503, retry_after=30
    )

    http_exc = error.to_http_exception()

    assert isinstance(http_exc, HTTPException)
    assert http_exc.status_code == 503
    assert "[req1] Server error" in http_exc.detail
    assert http_exc.headers == {"Retry-After": "30"}


def test_base_exception_repr():
    """Test __repr__ for debugging."""
    error = AIStudioProxyError(
        message="Test", req_id="id1", http_status=400, extra_data="value"
    )

    repr_str = repr(error)
    assert "AIStudioProxyError" in repr_str
    assert "message='Test'" in repr_str
    assert "req_id='id1'" in repr_str
    assert "http_status=400" in repr_str
    assert "extra_data" in repr_str


# ==================== BROWSER ERROR TESTS ====================


def test_browser_error_defaults():
    """Test BrowserError default status codes."""
    error = BrowserError("Page crashed")

    assert error.http_status == 503
    assert error.retry_after == 30


def test_page_not_ready_error():
    """Test PageNotReadyError with request ID."""
    error = PageNotReadyError("Page lost connection", req_id="req123")

    assert isinstance(error, BrowserError)
    assert error.message == "Page lost connection"
    assert error.http_status == 503


def test_browser_crashed_error():
    """Test BrowserCrashedError with default message."""
    error = BrowserCrashedError(req_id="req456")

    assert error.message == "Browser crashed unexpectedly"
    assert error.http_status == 503


def test_selector_not_found_error():
    """Test SelectorNotFoundError with selector context."""
    error = SelectorNotFoundError(selector="button#submit", req_id="req789")

    assert "button#submit" in error.message
    assert error.context["selector"] == "button#submit"


# ==================== MODEL ERROR TESTS ====================


def test_model_error_defaults():
    """Test ModelError default status code."""
    error = ModelError("Model issue")

    assert error.http_status == 422


def test_invalid_model_error_with_alternatives():
    """Test InvalidModelError with available models list."""
    error = InvalidModelError(
        model_id="gemini-invalid",
        available_models=["gemini-1.5-pro", "gemini-1.5-flash"],
        req_id="req1",
    )

    assert "gemini-invalid" in error.message
    assert "gemini-1.5-pro" in error.message
    assert error.context["model_id"] == "gemini-invalid"
    assert error.http_status == 422


def test_model_switch_error():
    """Test ModelSwitchError with source and target models."""
    error = ModelSwitchError(
        target_model="gemini-2.0", current_model="gemini-1.5-pro", req_id="req2"
    )

    assert "gemini-2.0" in error.message
    assert "gemini-1.5-pro" in error.message
    assert error.context["target_model"] == "gemini-2.0"


# ==================== CLIENT ERROR TESTS ====================


def test_client_disconnected_error_with_stage():
    """Test ClientDisconnectedError with processing stage."""
    error = ClientDisconnectedError(stage="model_switching", req_id="req3")

    assert error.stage == "model_switching"
    assert error.http_status == 499


def test_client_disconnected_error_no_stage():
    """Test ClientDisconnectedError without stage."""
    error = ClientDisconnectedError(req_id="req4")

    assert "Client disconnected" in error.message
    assert error.stage == ""


# ==================== VALIDATION ERROR TESTS ====================


def test_validation_error_defaults():
    """Test ValidationError default status code."""
    error = ValidationError("Invalid data")

    assert error.http_status == 400


def test_missing_parameter_error():
    """Test MissingParameterError with parameter name."""
    error = MissingParameterError(parameter="temperature", req_id="req5")

    assert "temperature" in error.message
    assert error.context["parameter"] == "temperature"


def test_invalid_parameter_error():
    """Test InvalidParameterError with value and reason."""
    error = InvalidParameterError(
        parameter="temperature",
        value=3.5,
        reason="must be between 0.0 and 2.0",
        req_id="req6",
    )

    assert "temperature" in error.message
    assert "3.5" in error.message
    assert "must be between 0.0 and 2.0" in error.message


# ==================== STREAM ERROR TESTS ====================


def test_stream_error_defaults():
    """Test StreamError default status code."""
    error = StreamError("Stream failed")

    assert error.http_status == 502


def test_proxy_connection_error():
    """Test ProxyConnectionError with proxy URL."""
    error = ProxyConnectionError(proxy_url="http://127.0.0.1:3120", req_id="req7")

    assert "127.0.0.1:3120" in error.message
    assert error.context["proxy_url"] == "http://127.0.0.1:3120"


def test_stream_timeout_error():
    """Test StreamTimeoutError with timeout duration."""
    error = StreamTimeoutError(timeout_seconds=30.0, req_id="req8")

    assert "30.0s" in error.message
    assert error.context["timeout_seconds"] == 30.0


# ==================== RESOURCE ERROR TESTS ====================


def test_resource_error_defaults():
    """Test ResourceError default status and retry."""
    error = ResourceError("Resource exhausted")

    assert error.http_status == 503
    assert error.retry_after == 60


def test_queue_full_error():
    """Test QueueFullError with queue size."""
    error = QueueFullError(queue_size=100, req_id="req9")

    assert "100" in error.message
    assert error.context["queue_size"] == 100


def test_browser_init_error():
    """Test BrowserInitError with custom message."""
    error = BrowserInitError(message="Playwright installation missing", req_id="req10")

    assert "Playwright installation missing" in error.message


# ==================== UPSTREAM ERROR TESTS ====================


def test_upstream_error_defaults():
    """Test UpstreamError default status and retry."""
    error = UpstreamError("Upstream issue")

    assert error.http_status == 502
    assert error.retry_after == 10


def test_ai_studio_error():
    """Test AIStudioError with AI Studio status code."""
    error = AIStudioError(
        error_message="Internal server error", status_code=500, req_id="req11"
    )

    assert "Internal server error" in error.message
    assert error.context["ai_studio_status"] == 500


def test_quota_exceeded_error():
    """Test QuotaExceededError with extended retry."""
    error = QuotaExceededError(req_id="req12")

    assert error.retry_after == 3600  # 1 hour
    assert "quota exceeded" in error.message.lower()


def test_empty_response_error():
    """Test EmptyResponseError default message."""
    error = EmptyResponseError(req_id="req13")

    assert "empty response" in error.message.lower()


# ==================== TIMEOUT ERROR TESTS ====================


def test_timeout_error_defaults():
    """Test TimeoutError default status code."""
    error = TimeoutError("Operation timeout")

    assert error.http_status == 504


def test_response_timeout_error():
    """Test ResponseTimeoutError with duration."""
    error = ResponseTimeoutError(timeout_seconds=300.0, req_id="req14")

    assert "300.0s" in error.message
    assert error.context["timeout_seconds"] == 300.0


def test_processing_timeout_error():
    """Test ProcessingTimeoutError without duration."""
    error = ProcessingTimeoutError(req_id="req15")

    assert "processing timeout" in error.message.lower()


# ==================== CONFIGURATION ERROR TESTS ====================


def test_configuration_error_defaults():
    """Test ConfigurationError default status code."""
    error = ConfigurationError("Config missing")

    assert error.http_status == 500


def test_missing_config_error():
    """Test MissingConfigError with config key."""
    error = MissingConfigError(config_key="API_KEY", req_id="req16")

    assert "API_KEY" in error.message
    assert error.context["config_key"] == "API_KEY"


def test_invalid_config_error():
    """Test InvalidConfigError with value and reason."""
    error = InvalidConfigError(
        config_key="PORT", value="invalid", reason="must be a number", req_id="req17"
    )

    assert "PORT" in error.message
    assert "invalid" in error.message
    assert "must be a number" in error.message


# ==================== INHERITANCE TESTS ====================


def test_error_hierarchy():
    """Test that exception hierarchy is correct."""
    # Browser errors inherit from BrowserError
    assert issubclass(PageNotReadyError, BrowserError)
    assert issubclass(SelectorNotFoundError, BrowserError)

    # All errors inherit from AIStudioProxyError
    assert issubclass(BrowserError, AIStudioProxyError)
    assert issubclass(ModelError, AIStudioProxyError)
    assert issubclass(ValidationError, AIStudioProxyError)
    assert issubclass(StreamError, AIStudioProxyError)

    # All errors inherit from Exception
    assert issubclass(AIStudioProxyError, Exception)


def test_error_catchable_by_base():
    """Test that specific errors can be caught by base class."""
    try:
        raise PageNotReadyError("Test", req_id="test")
    except BrowserError as e:
        assert isinstance(e, PageNotReadyError)
    except Exception:
        pytest.fail("Should have caught as BrowserError")


# ==================== HTTP EXCEPTION CONVERSION TESTS ====================


def test_to_http_exception_preserves_status():
    """Test that to_http_exception() uses correct HTTP status."""
    test_cases = [
        (BrowserError("Browser error"), 503),
        (ModelError("Model error"), 422),
        (ValidationError("Validation error"), 400),
        (StreamError("Stream error"), 502),
        (TimeoutError("Timeout error"), 504),
    ]

    for error, expected_status in test_cases:
        http_exc = error.to_http_exception()
        assert http_exc.status_code == expected_status


def test_to_http_exception_includes_retry_after():
    """Test that retry_after is included in headers."""
    error = ResourceError("Resource issue", retry_after=120)
    http_exc = error.to_http_exception()

    assert http_exc.headers == {"Retry-After": "120"}


def test_to_http_exception_without_retry():
    """Test that headers are None when no retry_after."""
    error = ValidationError("Bad request")
    http_exc = error.to_http_exception()

    # Should be None, not empty dict
    assert http_exc.headers is None


# ==================== CONTEXT PRESERVATION TESTS ====================


def test_context_preservation():
    """Test that custom context is preserved."""
    error = AIStudioProxyError(
        message="Error",
        req_id="test",
        custom_key="custom_value",
        another_key=42,
        nested={"a": 1, "b": 2},
    )

    assert error.context["custom_key"] == "custom_value"
    assert error.context["another_key"] == 42
    assert error.context["nested"] == {"a": 1, "b": 2}


def test_timestamp_is_recent():
    """Test that timestamp is set to current time."""
    before = time.time()
    error = AIStudioProxyError("Test")
    after = time.time()

    assert before <= error.timestamp <= after


# ==================== BACKWARD COMPATIBILITY TESTS ====================


def test_client_disconnected_error_backward_compat():
    """Test that ClientDisconnectedError works like old implementation."""
    # Old usage (just message)
    error = ClientDisconnectedError("test_stage", req_id="req1")

    assert isinstance(error, Exception)
    assert "test_stage" in error.message
    assert error.req_id == "req1"


# ==================== EDGE CASES ====================


def test_error_without_req_id():
    """Test errors work without req_id."""
    error = BrowserError("No request ID")

    assert error.req_id is None
    assert "No request ID" == error.message
    assert "[" not in str(error)  # Should not have [req_id] prefix


def test_error_with_empty_context():
    """Test error with no additional context."""
    error = AIStudioProxyError("Simple error")

    assert error.context == {}


def test_custom_http_status_override():
    """Test that custom http_status overrides default."""
    error = BrowserError("Custom status", http_status=418)  # I'm a teapot

    assert error.http_status == 418


def test_custom_retry_after_override():
    """Test that custom retry_after overrides default."""
    error = ResourceError("Custom retry", retry_after=5)

    assert error.retry_after == 5


def test_processing_timeout_error_with_duration():
    """Test ProcessingTimeoutError with timeout_seconds (covers line 427)."""
    error = ProcessingTimeoutError(timeout_seconds=30.0, req_id="req16")

    # Verify timeout is included in message (line 427)
    assert "30.0s" in error.message
    assert "processing timeout" in error.message.lower()
    assert error.context["timeout_seconds"] == 30.0


def test_model_list_error():
    """Test ModelListError initialization (covers line 196)."""
    error = ModelListError(message="Failed to parse models", req_id="req17")

    # Verify super().__init__ was called (line 196)
    assert error.message == "Failed to parse models"
    assert error.req_id == "req17"
    assert error.http_status == 422  # Inherits from ModelError
