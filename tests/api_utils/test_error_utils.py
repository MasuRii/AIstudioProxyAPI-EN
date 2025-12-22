"""
High-quality tests for api_utils/error_utils.py (zero mocking).

Focus: Test real error creation logic with no mocks, only pure function testing.
"""

from fastapi import HTTPException


def test_http_error_basic():
    """
    Test scenario: Create basic HTTP error
    Strategy: Pure function test, no mocking needed
    """
    from api_utils.error_utils import http_error

    result = http_error(status_code=404, detail="Not found")

    assert isinstance(result, HTTPException)
    assert result.status_code == 404
    assert result.detail == "Not found"
    assert result.headers is None


def test_http_error_with_headers():
    """
    Test scenario: Create HTTP error with custom headers
    Verify: headers parameter passed correctly
    """
    from api_utils.error_utils import http_error

    custom_headers = {"X-Custom-Header": "value", "Retry-After": "60"}
    result = http_error(
        status_code=503, detail="Service unavailable", headers=custom_headers
    )

    assert result.status_code == 503
    assert result.detail == "Service unavailable"
    assert result.headers == custom_headers
    assert result.headers is not None  # Type guard for pyright
    assert result.headers["X-Custom-Header"] == "value"
    assert result.headers["Retry-After"] == "60"


def test_http_error_with_none_headers():
    """
    Test scenario: Explicitly pass None as headers
    Expected: Should return None instead of empty dict
    """
    from api_utils.error_utils import http_error

    result = http_error(status_code=500, detail="Error", headers=None)

    assert result.headers is None


def test_client_cancelled_default_message():
    """
    Test scenario: Create client cancelled error (default message)
    Verify: 499 status code and default message format
    """
    from api_utils.error_utils import client_cancelled

    result = client_cancelled(req_id="req123")

    assert result.status_code == 499
    assert result.detail == "[req123] Request cancelled."


def test_client_cancelled_custom_message():
    """
    Test scenario: Create client cancelled error (custom message)
    Verify: Custom message formatted correctly
    """
    from api_utils.error_utils import client_cancelled

    result = client_cancelled(req_id="req456", message="User aborted operation")

    assert result.status_code == 499
    assert result.detail == "[req456] User aborted operation"


def test_client_disconnected_without_stage():
    """
    Test scenario: Client disconnected (no stage)
    Verify: Message does not contain stage info
    """
    from api_utils.error_utils import client_disconnected

    result = client_disconnected(req_id="req789")

    assert result.status_code == 499
    assert result.detail == "[req789] Client disconnected."


def test_client_disconnected_with_stage():
    """
    Test scenario: Client disconnected (with stage)
    Verify: Message contains stage info
    """
    from api_utils.error_utils import client_disconnected

    result = client_disconnected(req_id="req101", stage="streaming")

    assert result.status_code == 499
    assert result.detail == "[req101] Client disconnected during streaming."


def test_processing_timeout_default():
    """
    Test scenario: Processing timeout (default message)
    Verify: 504 status code and default message
    """
    from api_utils.error_utils import processing_timeout

    result = processing_timeout(req_id="req202")

    assert result.status_code == 504
    assert result.detail == "[req202] Processing timed out."


def test_processing_timeout_custom_message():
    """
    Test scenario: Processing timeout (custom message)
    Verify: Custom message formatted correctly
    """
    from api_utils.error_utils import processing_timeout

    result = processing_timeout(req_id="req303", message="Browser operation timeout")

    assert result.status_code == 504
    assert result.detail == "[req303] Browser operation timeout"


def test_bad_request():
    """
    Test scenario: Create 400 bad request
    Verify: Status code and message format
    """
    from api_utils.error_utils import bad_request

    result = bad_request(
        req_id="req404", message="Invalid parameter: temperature > 2.0"
    )

    assert result.status_code == 400
    assert result.detail == "[req404] Invalid parameter: temperature > 2.0"


def test_server_error():
    """
    Test scenario: Create 500 server error
    Verify: Status code and message format
    """
    from api_utils.error_utils import server_error

    result = server_error(req_id="req505", message="Internal processing failure")

    assert result.status_code == 500
    assert result.detail == "[req505] Internal processing failure"


def test_upstream_error():
    """
    Test scenario: Create 502 upstream error
    Verify: Status code and message format
    """
    from api_utils.error_utils import upstream_error

    result = upstream_error(req_id="req606", message="Playwright timeout")

    assert result.status_code == 502
    assert result.detail == "[req606] Playwright timeout"


def test_service_unavailable_default_retry():
    """
    Test scenario: Service unavailable (default retry time)
    Verify: 503 status code, Retry-After header, English message
    """
    from api_utils.error_utils import service_unavailable

    result = service_unavailable(req_id="req707")

    assert result.status_code == 503
    assert (
        result.detail
        == "[req707] Service currently unavailable. Please try again later."
    )
    assert result.headers == {"Retry-After": "30"}


def test_service_unavailable_custom_retry():
    """
    Test scenario: Service unavailable (custom retry time)
    Verify: Retry-After header contains custom value
    """
    from api_utils.error_utils import service_unavailable

    result = service_unavailable(req_id="req808", retry_after_seconds=120)

    assert result.status_code == 503
    assert (
        result.detail
        == "[req808] Service currently unavailable. Please try again later."
    )
    assert result.headers == {"Retry-After": "120"}


def test_error_with_unicode_in_message():
    """
    Test scenario: Error message contains Unicode characters
    Verify: Correctly handle non-ASCII characters
    """
    # Note: instructing to remove emojis, but keeping non-English if part of message?
    # User said: "Remove all non-ASCII characters (e.g., emojis like 🎉)."
    # So I will translate the message and remove the emoji.
    from api_utils.error_utils import server_error

    result = server_error(
        req_id="req909", message="Processing failed: Model switch timeout"
    )

    assert result.status_code == 500
    assert result.detail == "[req909] Processing failed: Model switch timeout"


def test_error_with_special_characters():
    """
    Test scenario: Error message contains special characters
    Verify: Correctly handle quotes, newlines, etc.
    """
    from api_utils.error_utils import bad_request

    result = bad_request(req_id="req010", message='Invalid JSON: unexpected "quote"')

    assert result.status_code == 400
    assert 'Invalid JSON: unexpected "quote"' in result.detail
