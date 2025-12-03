"""
High-quality tests for api_utils/error_utils.py (zero mocking).

Focus: Test real error creation logic with no mocks, only pure function testing.
"""

from fastapi import HTTPException


def test_http_error_basic():
    """
    测试场景: 创建基本的 HTTP 错误
    策略: 纯函数测试，无需模拟
    """
    from api_utils.error_utils import http_error

    result = http_error(status_code=404, detail="Not found")

    assert isinstance(result, HTTPException)
    assert result.status_code == 404
    assert result.detail == "Not found"
    assert result.headers is None


def test_http_error_with_headers():
    """
    测试场景: 创建带自定义头的 HTTP 错误
    验证: headers 参数被正确传递
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
    测试场景: 显式传递 None 作为 headers
    预期: 应该返回 None 而不是空字典
    """
    from api_utils.error_utils import http_error

    result = http_error(status_code=500, detail="Error", headers=None)

    assert result.headers is None


def test_client_cancelled_default_message():
    """
    测试场景: 创建客户端取消错误（默认消息）
    验证: 499 状态码和默认消息格式
    """
    from api_utils.error_utils import client_cancelled

    result = client_cancelled(req_id="req123")

    assert result.status_code == 499
    assert result.detail == "[req123] Request cancelled."


def test_client_cancelled_custom_message():
    """
    测试场景: 创建客户端取消错误（自定义消息）
    验证: 自定义消息被正确格式化
    """
    from api_utils.error_utils import client_cancelled

    result = client_cancelled(req_id="req456", message="User aborted operation")

    assert result.status_code == 499
    assert result.detail == "[req456] User aborted operation"


def test_client_disconnected_without_stage():
    """
    测试场景: 客户端断开连接（无 stage）
    验证: 消息不包含 stage 信息
    """
    from api_utils.error_utils import client_disconnected

    result = client_disconnected(req_id="req789")

    assert result.status_code == 499
    assert result.detail == "[req789] Client disconnected."


def test_client_disconnected_with_stage():
    """
    测试场景: 客户端断开连接（有 stage）
    验证: 消息包含 stage 信息
    """
    from api_utils.error_utils import client_disconnected

    result = client_disconnected(req_id="req101", stage="streaming")

    assert result.status_code == 499
    assert result.detail == "[req101] Client disconnected during streaming."


def test_processing_timeout_default():
    """
    测试场景: 处理超时（默认消息）
    验证: 504 状态码和默认消息
    """
    from api_utils.error_utils import processing_timeout

    result = processing_timeout(req_id="req202")

    assert result.status_code == 504
    assert result.detail == "[req202] Processing timed out."


def test_processing_timeout_custom_message():
    """
    测试场景: 处理超时（自定义消息）
    验证: 自定义消息被正确格式化
    """
    from api_utils.error_utils import processing_timeout

    result = processing_timeout(req_id="req303", message="Browser operation timeout")

    assert result.status_code == 504
    assert result.detail == "[req303] Browser operation timeout"


def test_bad_request():
    """
    测试场景: 创建 400 错误请求
    验证: 状态码和消息格式
    """
    from api_utils.error_utils import bad_request

    result = bad_request(
        req_id="req404", message="Invalid parameter: temperature > 2.0"
    )

    assert result.status_code == 400
    assert result.detail == "[req404] Invalid parameter: temperature > 2.0"


def test_server_error():
    """
    测试场景: 创建 500 服务器错误
    验证: 状态码和消息格式
    """
    from api_utils.error_utils import server_error

    result = server_error(req_id="req505", message="Internal processing failure")

    assert result.status_code == 500
    assert result.detail == "[req505] Internal processing failure"


def test_upstream_error():
    """
    测试场景: 创建 502 上游错误
    验证: 状态码和消息格式
    """
    from api_utils.error_utils import upstream_error

    result = upstream_error(req_id="req606", message="Playwright timeout")

    assert result.status_code == 502
    assert result.detail == "[req606] Playwright timeout"


def test_service_unavailable_default_retry():
    """
    测试场景: 服务不可用（默认重试时间）
    验证: 503 状态码、Retry-After 头、中文消息
    """
    from api_utils.error_utils import service_unavailable

    result = service_unavailable(req_id="req707")

    assert result.status_code == 503
    assert result.detail == "[req707] 服务当前不可用。请稍后重试。"
    assert result.headers == {"Retry-After": "30"}


def test_service_unavailable_custom_retry():
    """
    测试场景: 服务不可用（自定义重试时间）
    验证: Retry-After 头包含自定义值
    """
    from api_utils.error_utils import service_unavailable

    result = service_unavailable(req_id="req808", retry_after_seconds=120)

    assert result.status_code == 503
    assert result.detail == "[req808] 服务当前不可用。请稍后重试。"
    assert result.headers == {"Retry-After": "120"}


def test_error_with_unicode_in_message():
    """
    测试场景: 错误消息包含 Unicode 字符
    验证: 正确处理非 ASCII 字符
    """
    from api_utils.error_utils import server_error

    result = server_error(req_id="req909", message="处理失败：模型切换超时 😢")

    assert result.status_code == 500
    assert result.detail == "[req909] 处理失败：模型切换超时 😢"


def test_error_with_special_characters():
    """
    测试场景: 错误消息包含特殊字符
    验证: 正确处理引号、换行等特殊字符
    """
    from api_utils.error_utils import bad_request

    result = bad_request(req_id="req010", message='Invalid JSON: unexpected "quote"')

    assert result.status_code == 400
    assert 'Invalid JSON: unexpected "quote"' in result.detail
