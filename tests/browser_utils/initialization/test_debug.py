"""
Tests for browser_utils/initialization/debug.py
Target coverage: >80% (from baseline 10%)
"""

from unittest.mock import Mock, PropertyMock, patch

import pytest

from browser_utils.initialization.debug import setup_debug_listeners


@pytest.fixture
def mock_page():
    """Create mock page"""
    page = Mock()
    page.on = Mock()
    return page


@pytest.fixture
def mock_console_message():
    """Create mock console message"""
    msg = Mock()
    msg.type = "log"
    msg.text = "test message"
    msg.location = {"url": "https://example.com/page.js", "lineNumber": 42}
    return msg


@pytest.fixture
def mock_request():
    """Create mock network request"""
    req = Mock()
    req.url = "https://example.com/api/data"
    req.method = "GET"
    req.resource_type = "xhr"
    return req


@pytest.fixture
def mock_response():
    """Create mock network response"""
    resp = Mock()
    resp.url = "https://example.com/api/data"
    resp.status = 200
    resp.status_text = "OK"
    return resp


def test_listeners_attached(mock_page, mock_server_module):
    """Test all listeners attached"""
    setup_debug_listeners(mock_page)

    assert mock_page.on.call_count == 3

    listener_names = [call_args[0][0] for call_args in mock_page.on.call_args_list]
    assert "console" in listener_names
    assert "request" in listener_names
    assert "response" in listener_names


def test_console_handler_log(mock_page, mock_server_module, mock_console_message):
    """Test console log captured"""
    setup_debug_listeners(mock_page)

    # Extract console handler
    console_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "console":
            console_handler = call_args[0][1]
            break

    assert console_handler is not None

    # Trigger handler (datetime is imported inside the handler, no need to mock)
    console_handler(mock_console_message)

    # Verify log captured
    assert len(mock_server_module.console_logs) == 1
    log_entry = mock_server_module.console_logs[0]
    assert log_entry["type"] == "log"
    assert log_entry["text"] == "test message"
    assert "timestamp" in log_entry
    assert "location" in log_entry


def test_console_handler_error(mock_page, mock_server_module):
    """Test console error captured"""
    setup_debug_listeners(mock_page)

    console_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "console":
            console_handler = call_args[0][1]
            break

    error_msg = Mock()
    error_msg.type = "error"
    error_msg.text = "Critical error"
    error_msg.location = {"url": "test.js", "lineNumber": 1}

    assert console_handler is not None
    console_handler(error_msg)

    assert len(mock_server_module.console_logs) == 1
    assert mock_server_module.console_logs[0]["type"] == "error"


def test_request_handler_xhr(mock_page, mock_server_module, mock_request):
    """Test XHR request captured"""
    setup_debug_listeners(mock_page)

    request_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "request":
            request_handler = call_args[0][1]
            break

    assert request_handler is not None
    request_handler(mock_request)

    assert len(mock_server_module.network_log["requests"]) == 1
    req_entry = mock_server_module.network_log["requests"][0]
    assert req_entry["url"] == "https://example.com/api/data"
    assert req_entry["method"] == "GET"
    assert "timestamp" in req_entry


def test_request_handler_image_filtered(mock_page, mock_server_module):
    """Test image request filtered out"""
    setup_debug_listeners(mock_page)

    request_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "request":
            request_handler = call_args[0][1]
            break

    image_req = Mock()
    image_req.url = "https://example.com/logo.png"
    image_req.method = "GET"
    image_req.resource_type = "image"

    assert request_handler is not None
    request_handler(image_req)

    assert len(mock_server_module.network_log["requests"]) == 0


def test_request_handler_css_filtered(mock_page, mock_server_module):
    """Test CSS request filtered out"""
    setup_debug_listeners(mock_page)

    request_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "request":
            request_handler = call_args[0][1]
            break

    css_req = Mock()
    css_req.url = "https://example.com/styles.css"
    css_req.method = "GET"
    css_req.resource_type = "stylesheet"

    assert request_handler is not None
    request_handler(css_req)

    assert len(mock_server_module.network_log["requests"]) == 0


def test_response_handler_success(mock_page, mock_server_module, mock_response):
    """Test successful response captured"""
    setup_debug_listeners(mock_page)

    response_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "response":
            response_handler = call_args[0][1]
            break

    assert response_handler is not None
    response_handler(mock_response)

    assert len(mock_server_module.network_log["responses"]) == 1
    resp_entry = mock_server_module.network_log["responses"][0]
    assert resp_entry["status"] == 200
    assert resp_entry["url"] == "https://example.com/api/data"
    assert "timestamp" in resp_entry


def test_response_handler_error_status(mock_page, mock_server_module):
    """Test error response captured"""
    setup_debug_listeners(mock_page)

    response_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "response":
            response_handler = call_args[0][1]
            break

    error_resp = Mock()
    error_resp.url = "https://example.com/api/error"
    error_resp.status = 404
    error_resp.status_text = "Not Found"

    assert response_handler is not None
    response_handler(error_resp)

    assert len(mock_server_module.network_log["responses"]) == 1
    assert mock_server_module.network_log["responses"][0]["status"] == 404


def test_console_handler_exception_caught(mock_page, mock_server_module):
    """Test exception in console handler caught"""
    setup_debug_listeners(mock_page)

    console_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "console":
            console_handler = call_args[0][1]
            break

    bad_msg = Mock()
    # Use PropertyMock to raise exception when .text is accessed as property
    type(bad_msg).text = PropertyMock(side_effect=RuntimeError("Extraction failed"))

    assert console_handler is not None
    with patch("browser_utils.initialization.debug.logger") as mock_logger:
        # Should not raise
        console_handler(bad_msg)

        # Verify error logged
        assert mock_logger.error.called


def test_request_handler_exception_caught(mock_page, mock_server_module):
    """Test exception in request handler caught"""
    setup_debug_listeners(mock_page)

    request_handler = None
    for call_args in mock_page.on.call_args_list:
        if call_args[0][0] == "request":
            request_handler = call_args[0][1]
            break

    bad_req = Mock()
    bad_req.url = Mock(side_effect=RuntimeError("URL access failed"))

    assert request_handler is not None
    with patch("browser_utils.initialization.debug.logger") as mock_logger:
        request_handler(bad_req)
        assert mock_logger.error.called
