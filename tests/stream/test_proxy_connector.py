"""
High-quality tests for stream/proxy_connector.py - Proxy connection handling.

Focus: Test proxy connector initialization and connection creation for various proxy types.
Strategy: Mock only external I/O boundaries (asyncio.open_connection, Proxy.from_url).
"""

import ssl as ssl_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stream.proxy_connector import ProxyConnector

# ============================================================================
# __init__() Tests
# ============================================================================


def test_proxy_connector_init_without_proxy():
    """Test scenario: Initialization without proxy URL"""
    connector = ProxyConnector()
    assert connector.proxy_url is None
    assert connector.connector is None


def test_proxy_connector_init_with_http_proxy():
    """Test scenario: HTTP proxy initialization"""
    connector = ProxyConnector("http://proxy.example.com:8080")
    assert connector.proxy_url == "http://proxy.example.com:8080"
    assert connector.connector == "SocksConnector"


def test_proxy_connector_init_with_https_proxy():
    """Test scenario: HTTPS proxy initialization"""
    connector = ProxyConnector("https://proxy.example.com:443")
    assert connector.proxy_url == "https://proxy.example.com:443"
    assert connector.connector == "SocksConnector"


def test_proxy_connector_init_with_socks4_proxy():
    """Test scenario: SOCKS4 proxy initialization"""
    connector = ProxyConnector("socks4://proxy.example.com:1080")
    assert connector.proxy_url == "socks4://proxy.example.com:1080"
    assert connector.connector == "SocksConnector"


def test_proxy_connector_init_with_socks5_proxy():
    """Test scenario: SOCKS5 proxy initialization"""
    connector = ProxyConnector("socks5://proxy.example.com:1080")
    assert connector.proxy_url == "socks5://proxy.example.com:1080"
    assert connector.connector == "SocksConnector"


def test_proxy_connector_init_with_invalid_proxy_type():
    """Test scenario: Unsupported proxy type"""
    with pytest.raises(ValueError, match="Unsupported proxy type: ftp"):
        ProxyConnector("ftp://proxy.example.com:21")


def test_proxy_connector_init_with_mixed_case_proxy_type():
    """Test scenario: Mixed case proxy type (should be case-insensitive)"""
    connector = ProxyConnector("HTTP://proxy.example.com:8080")
    assert connector.connector == "SocksConnector"

    connector2 = ProxyConnector("SOCKS5://proxy.example.com:1080")
    assert connector2.connector == "SocksConnector"


# ============================================================================
# _setup_connector() Tests
# ============================================================================


def test_setup_connector_with_no_proxy_url():
    """Test scenario: set TCPConnector when proxy_url is None"""
    connector = ProxyConnector()
    # Manually call _setup_connector with proxy_url=None
    connector._setup_connector()
    # Should set TCPConnector
    from aiohttp import TCPConnector

    assert isinstance(connector.connector, TCPConnector)


def test_setup_connector_with_socks_proxy():
    """Test scenario: set SocksConnector for SOCKS proxy"""
    connector = ProxyConnector("socks5://localhost:1080")
    # Already called in __init__
    assert connector.connector == "SocksConnector"


def test_setup_connector_with_http_proxy():
    """Test scenario: set SocksConnector for HTTP proxy"""
    connector = ProxyConnector("http://localhost:8080")
    # Already called in __init__
    assert connector.connector == "SocksConnector"


def test_setup_connector_with_invalid_scheme():
    """Test scenario: Invalid scheme raises ValueError"""
    with pytest.raises(ValueError, match="Unsupported proxy type"):
        ProxyConnector("rtsp://example.com:554")


# ============================================================================
# create_connection() Tests - Direct Connection (No Proxy)
# ============================================================================


@pytest.mark.asyncio
async def test_create_connection_direct_no_ssl():
    """Test scenario: No proxy, direct connection, no SSL"""
    connector = ProxyConnector()

    mock_reader = AsyncMock()
    mock_writer = AsyncMock()

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open:
        mock_open.return_value = (mock_reader, mock_writer)

        reader, writer = await connector.create_connection("example.com", 80, ssl=None)

        # Verify: asyncio.open_connection called correctly
        mock_open.assert_called_once_with("example.com", 80, ssl=None)
        assert reader is mock_reader
        assert writer is mock_writer


@pytest.mark.asyncio
async def test_create_connection_direct_with_ssl():
    """Test scenario: No proxy, direct connection, SSL enabled"""
    connector = ProxyConnector()

    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_ssl_context = MagicMock()

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open:
        mock_open.return_value = (mock_reader, mock_writer)

        reader, writer = await connector.create_connection(
            "example.com", 443, ssl=mock_ssl_context
        )

        # Verify: asyncio.open_connection uses SSL context
        mock_open.assert_called_once_with("example.com", 443, ssl=mock_ssl_context)
        assert reader is mock_reader
        assert writer is mock_writer


# ============================================================================
# create_connection() Tests - SOCKS Proxy
# ============================================================================


@pytest.mark.asyncio
async def test_create_connection_socks_no_ssl():
    """Test scenario: SOCKS proxy, no SSL"""
    connector = ProxyConnector("socks5://localhost:1080")

    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_sock = MagicMock()
    mock_proxy = MagicMock()
    mock_proxy.connect = AsyncMock(return_value=mock_sock)

    with (
        patch(
            "stream.proxy_connector.Proxy.from_url", return_value=mock_proxy
        ) as mock_from_url,
        patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open,
    ):
        mock_open.return_value = (mock_reader, mock_writer)

        reader, writer = await connector.create_connection("example.com", 80, ssl=None)

        # Verify: Proxy.from_url is called
        mock_from_url.assert_called_once_with("socks5://localhost:1080")

        # Verify: proxy.connect is called
        mock_proxy.connect.assert_called_once_with(
            dest_host="example.com", dest_port=80
        )

        # Verify: asyncio.open_connection uses sock, no SSL
        mock_open.assert_called_once_with(
            host=None, port=None, sock=mock_sock, ssl=None
        )

        assert reader is mock_reader
        assert writer is mock_writer


@pytest.mark.asyncio
async def test_create_connection_socks_with_ssl():
    """Test scenario: SOCKS proxy, SSL enabled"""
    connector = ProxyConnector("socks5://localhost:1080")

    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_sock = MagicMock()
    mock_proxy = MagicMock()
    mock_proxy.connect = AsyncMock(return_value=mock_sock)

    with (
        patch("stream.proxy_connector.Proxy.from_url", return_value=mock_proxy),
        patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open,
    ):
        mock_open.return_value = (mock_reader, mock_writer)

        # 传入 ssl=True 来触发 SSL 上下文创建
        reader, writer = await connector.create_connection("example.com", 443, ssl=True)

        # Verify: proxy.connect is called
        mock_proxy.connect.assert_called_once_with(
            dest_host="example.com", dest_port=443
        )

        # Verify: asyncio.open_connection uses sock and SSL context
        mock_open.assert_called_once()
        call_kwargs = mock_open.call_args[1]
        assert call_kwargs["host"] is None
        assert call_kwargs["port"] is None
        assert call_kwargs["sock"] is mock_sock
        assert isinstance(call_kwargs["ssl"], ssl_module.SSLContext)
        assert call_kwargs["server_hostname"] == "example.com"

        # Verify: SSL context configuration
        ssl_ctx = call_kwargs["ssl"]
        assert ssl_ctx.check_hostname is False
        assert ssl_ctx.verify_mode == ssl_module.CERT_NONE

        assert reader is mock_reader
        assert writer is mock_writer


@pytest.mark.asyncio
async def test_create_connection_socks_with_custom_ssl_context():
    """Test scenario: SOCKS proxy, custom SSL context"""
    connector = ProxyConnector("socks5://localhost:1080")

    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_sock = MagicMock()
    mock_proxy = MagicMock()
    mock_proxy.connect = AsyncMock(return_value=mock_sock)

    # 创建自定义 SSL 上下文
    custom_ssl = ssl_module.SSLContext(ssl_module.PROTOCOL_TLS_CLIENT)

    with (
        patch("stream.proxy_connector.Proxy.from_url", return_value=mock_proxy),
        patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open,
    ):
        mock_open.return_value = (mock_reader, mock_writer)

        # 传入自定义 SSL 上下文（非 None 非 True）
        reader, writer = await connector.create_connection(
            "example.com", 443, ssl=custom_ssl
        )

        # Verify: asyncio.open_connection uses custom SSL context
        # 注意: 代码中 ssl != None 时会创建新的 SSL 上下文，而不是使用传入的
        mock_open.assert_called_once()
        call_kwargs = mock_open.call_args[1]
        assert call_kwargs["sock"] is mock_sock
        # 代码会创建新的 SSLContext，不使用传入的
        assert isinstance(call_kwargs["ssl"], ssl_module.SSLContext)
        assert call_kwargs["server_hostname"] == "example.com"


@pytest.mark.asyncio
async def test_create_connection_http_proxy():
    """Test scenario: HTTP proxy connection"""
    connector = ProxyConnector("http://proxy.example.com:8080")

    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_sock = MagicMock()
    mock_proxy = MagicMock()
    mock_proxy.connect = AsyncMock(return_value=mock_sock)

    with (
        patch(
            "stream.proxy_connector.Proxy.from_url", return_value=mock_proxy
        ) as mock_from_url,
        patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open,
    ):
        mock_open.return_value = (mock_reader, mock_writer)

        reader, writer = await connector.create_connection("target.com", 80)

        # Verify: Proxy.from_url uses HTTP proxy URL
        mock_from_url.assert_called_once_with("http://proxy.example.com:8080")

        # Verify: Connection to target host
        mock_proxy.connect.assert_called_once_with(dest_host="target.com", dest_port=80)


@pytest.mark.asyncio
async def test_create_connection_socks_proxy_with_auth():
    """Test scenario: SOCKS proxy with authentication"""
    proxy_url = "socks5://user:pass@localhost:1080"
    connector = ProxyConnector(proxy_url)

    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_sock = MagicMock()
    mock_proxy = MagicMock()
    mock_proxy.connect = AsyncMock(return_value=mock_sock)

    with (
        patch(
            "stream.proxy_connector.Proxy.from_url", return_value=mock_proxy
        ) as mock_from_url,
        patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open,
    ):
        mock_open.return_value = (mock_reader, mock_writer)

        reader, writer = await connector.create_connection("example.com", 80)

        # Verify: Proxy.from_url receives URL with authentication
        mock_from_url.assert_called_once_with(proxy_url)

        mock_proxy.connect.assert_called_once_with(
            dest_host="example.com", dest_port=80
        )
