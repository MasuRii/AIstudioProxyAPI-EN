"""
High-quality tests for stream/utils.py - Pure function tests (zero mocking).

Focus: Comprehensive edge case coverage for URL parsing, endpoint detection, and logger setup.
Strategy: Test all boundary conditions, special characters, protocol variations, IPv6, etc.
"""

import logging

from stream.utils import is_generate_content_endpoint, parse_proxy_url, setup_logger

# ============================================================================
# is_generate_content_endpoint() Tests
# ============================================================================


def test_is_generate_content_endpoint_exact_match():
    """测试场景: URL 包含 GenerateContent"""
    assert is_generate_content_endpoint("https://example.com/GenerateContent")
    assert is_generate_content_endpoint("GenerateContent")
    assert is_generate_content_endpoint("/api/GenerateContent")


def test_is_generate_content_endpoint_with_query_string():
    """测试场景: URL 包含 GenerateContent 和查询字符串"""
    assert is_generate_content_endpoint("https://example.com/GenerateContent?key=value")
    assert is_generate_content_endpoint("GenerateContent?alt=sse")


def test_is_generate_content_endpoint_with_fragment():
    """测试场景: URL 包含 GenerateContent 和片段标识符"""
    assert is_generate_content_endpoint("https://example.com/GenerateContent#section")


def test_is_generate_content_endpoint_in_middle_of_path():
    """测试场景: GenerateContent 在路径中间"""
    assert is_generate_content_endpoint("/api/v1/GenerateContent/stream")
    assert is_generate_content_endpoint("https://example.com/GenerateContent/v2")


def test_is_generate_content_endpoint_case_sensitive():
    """测试场景: 大小写敏感性（当前实现是大小写敏感的）"""
    # 当前实现: "GenerateContent" in url (大小写敏感)
    assert is_generate_content_endpoint("GenerateContent")
    assert not is_generate_content_endpoint("generatecontent")
    assert not is_generate_content_endpoint("GENERATECONTENT")
    assert not is_generate_content_endpoint("generateContent")


def test_is_generate_content_endpoint_false_cases():
    """测试场景: 不包含 GenerateContent 的 URL"""
    assert not is_generate_content_endpoint("https://example.com/OtherEndpoint")
    assert not is_generate_content_endpoint("/api/v1/chat/completions")
    assert not is_generate_content_endpoint("")
    assert not is_generate_content_endpoint("/")
    assert not is_generate_content_endpoint("https://example.com/")


def test_is_generate_content_endpoint_partial_match():
    """测试场景: 部分匹配（子串）"""
    # 只要包含 "GenerateContent" 子串就返回 True
    assert is_generate_content_endpoint("MyGenerateContent")
    assert is_generate_content_endpoint("GenerateContentHandler")
    assert is_generate_content_endpoint("PreGenerateContentPost")


# ============================================================================
# parse_proxy_url() Tests
# ============================================================================


def test_parse_proxy_url_none_input():
    """测试场景: 输入为 None"""
    assert parse_proxy_url(None) == (None, None, None, None, None)


def test_parse_proxy_url_empty_string():
    """测试场景: 输入为空字符串"""
    assert parse_proxy_url("") == (None, None, None, None, None)


def test_parse_proxy_url_http_with_auth():
    """测试场景: HTTP 代理带认证"""
    scheme, host, port, user, password = parse_proxy_url(
        "http://user:pass@example.com:8080"
    )
    assert scheme == "http"
    assert host == "example.com"
    assert port == 8080
    assert user == "user"
    assert password == "pass"


def test_parse_proxy_url_https_with_auth():
    """测试场景: HTTPS 代理带认证"""
    scheme, host, port, user, password = parse_proxy_url(
        "https://admin:secret123@proxy.example.com:3128"
    )
    assert scheme == "https"
    assert host == "proxy.example.com"
    assert port == 3128
    assert user == "admin"
    assert password == "secret123"


def test_parse_proxy_url_socks5_with_auth():
    """测试场景: SOCKS5 代理带认证"""
    scheme, host, port, user, password = parse_proxy_url(
        "socks5://user:pass@socks.example.com:1080"
    )
    assert scheme == "socks5"
    assert host == "socks.example.com"
    assert port == 1080
    assert user == "user"
    assert password == "pass"


def test_parse_proxy_url_http_without_auth():
    """测试场景: HTTP 代理无认证"""
    scheme, host, port, user, password = parse_proxy_url("http://example.com:8080")
    assert scheme == "http"
    assert host == "example.com"
    assert port == 8080
    assert user is None
    assert password is None


def test_parse_proxy_url_https_without_auth():
    """测试场景: HTTPS 代理无认证"""
    scheme, host, port, user, password = parse_proxy_url("https://proxy.com:443")
    assert scheme == "https"
    assert host == "proxy.com"
    assert port == 443
    assert user is None
    assert password is None


def test_parse_proxy_url_no_port():
    """测试场景: 无端口号（使用默认端口）"""
    scheme, host, port, user, password = parse_proxy_url("http://example.com")
    assert scheme == "http"
    assert host == "example.com"
    assert port is None  # urlparse 不提供默认端口
    assert user is None
    assert password is None


def test_parse_proxy_url_localhost():
    """测试场景: localhost 代理"""
    scheme, host, port, user, password = parse_proxy_url("http://localhost:7890")
    assert scheme == "http"
    assert host == "localhost"
    assert port == 7890


def test_parse_proxy_url_ipv4():
    """测试场景: IPv4 地址"""
    scheme, host, port, user, password = parse_proxy_url("http://127.0.0.1:8888")
    assert scheme == "http"
    assert host == "127.0.0.1"
    assert port == 8888


def test_parse_proxy_url_ipv6():
    """测试场景: IPv6 地址"""
    scheme, host, port, user, password = parse_proxy_url("http://[2001:db8::1]:8080")
    assert scheme == "http"
    assert host == "2001:db8::1"
    assert port == 8080


def test_parse_proxy_url_username_only():
    """测试场景: 仅用户名无密码"""
    scheme, host, port, user, password = parse_proxy_url("http://user@example.com:8080")
    assert scheme == "http"
    assert host == "example.com"
    assert port == 8080
    assert user == "user"
    assert password is None


def test_parse_proxy_url_password_with_special_chars():
    """测试场景: 密码包含特殊字符（URL 编码）"""
    # 注意: urlparse 不会自动解码，保持原始编码
    scheme, host, port, user, password = parse_proxy_url(
        "http://user:p%40ss%3Aw0rd@example.com:8080"
    )
    assert scheme == "http"
    assert user == "user"
    assert password == "p%40ss%3Aw0rd"  # urlparse 不自动解码


def test_parse_proxy_url_complex_url():
    """测试场景: 复杂 URL 带路径（虽然代理 URL 通常不带路径）"""
    # 注意: 代理配置通常只是 scheme://host:port，但 urlparse 可以处理更复杂的情况
    scheme, host, port, user, password = parse_proxy_url(
        "http://user:pass@example.com:8080/path/to/proxy"
    )
    assert scheme == "http"
    assert host == "example.com"
    assert port == 8080
    assert user == "user"
    assert password == "pass"


# ============================================================================
# setup_logger() Tests
# ============================================================================


def test_setup_logger_basic(tmp_path):
    """测试场景: 基本 logger 设置（带日志文件）"""
    log_file = tmp_path / "test.log"
    logger = setup_logger("test_logger", str(log_file))

    assert logger.name == "test_logger"
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 2  # Console + File

    logger.info("Test message")

    # 验证文件内容
    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Test message" in content


def test_setup_logger_without_log_file():
    """测试场景: 无日志文件（仅控制台输出）"""
    logger = setup_logger("console_only_logger")

    assert logger.name == "console_only_logger"
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1  # 仅 Console handler

    # 清理 handler
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def test_setup_logger_custom_level_debug(tmp_path):
    """测试场景: 自定义日志级别（DEBUG）"""
    log_file = tmp_path / "debug.log"
    logger = setup_logger("debug_logger", str(log_file), level=logging.DEBUG)

    assert logger.level == logging.DEBUG

    logger.debug("Debug message")

    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Debug message" in content

    # 清理
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def test_setup_logger_custom_level_warning(tmp_path):
    """测试场景: 自定义日志级别（WARNING）"""
    log_file = tmp_path / "warning.log"
    logger = setup_logger("warning_logger", str(log_file), level=logging.WARNING)

    assert logger.level == logging.WARNING

    # INFO 消息不应被记录
    logger.info("Info message")
    logger.warning("Warning message")

    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Info message" not in content
        assert "Warning message" in content

    # 清理
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def test_setup_logger_multiple_calls_same_name():
    """测试场景: 多次调用 setup_logger 使用相同名称"""
    logger1 = setup_logger("duplicate_logger")
    logger2 = setup_logger("duplicate_logger")

    # 由于 logging.getLogger() 返回同一实例，handler 会累积
    # 第一次调用: 1 个 handler
    # 第二次调用: 再添加 1 个 handler -> 总共 2 个
    assert logger1 is logger2  # 同一 logger 对象
    assert len(logger2.handlers) == 2  # 累积的 handler

    # 清理
    for handler in logger2.handlers[:]:
        handler.close()
        logger2.removeHandler(handler)


def test_setup_logger_different_names():
    """测试场景: 不同名称的 logger 互不影响"""
    logger1 = setup_logger("logger_a")
    logger2 = setup_logger("logger_b")

    assert logger1.name == "logger_a"
    assert logger2.name == "logger_b"
    assert logger1 is not logger2
    assert len(logger1.handlers) == 1
    assert len(logger2.handlers) == 1

    # 清理
    for logger in [logger1, logger2]:
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)


def test_setup_logger_log_file_creation(tmp_path):
    """测试场景: 验证日志文件被正确创建"""
    log_file = tmp_path / "created.log"
    assert not log_file.exists()

    logger = setup_logger("file_creator", str(log_file))
    logger.info("First log")

    # 日志文件应被创建
    assert log_file.exists()
    assert log_file.is_file()

    # 清理
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def test_setup_logger_nested_directory(tmp_path):
    """测试场景: 日志文件在嵌套目录中"""
    nested_dir = tmp_path / "logs" / "stream"
    nested_dir.mkdir(parents=True)
    log_file = nested_dir / "nested.log"

    logger = setup_logger("nested_logger", str(log_file))
    logger.info("Nested log message")

    assert log_file.exists()
    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Nested log message" in content

    # 清理
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def test_setup_logger_handler_formatters():
    """测试场景: 验证 handler 的 formatter 配置"""
    logger = setup_logger("formatter_test")

    console_handler = logger.handlers[0]
    assert console_handler.formatter is not None

    # ColoredFormatter 应有 use_color 属性（基于 stream/utils.py 实现）
    # 注意: ColoredFormatter 可能未定义 use_color 属性，这取决于实现
    # 这里仅验证 formatter 存在

    # 清理
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
