import argparse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stream.main import builtin, main, parse_args
from stream.proxy_server import ProxyServer


@pytest.fixture
def proxy_server():
    return ProxyServer(
        host="127.0.0.1", port=8080, intercept_domains=["*.example.com", "api.test.com"]
    )


def test_should_intercept(proxy_server):
    """Test domain interception matching (exact, wildcard, and non-matching cases)."""
    # Exact match
    assert proxy_server.should_intercept("api.test.com") is True

    # Wildcard match
    assert proxy_server.should_intercept("sub.example.com") is True
    assert proxy_server.should_intercept("deep.sub.example.com") is True

    # No match
    assert proxy_server.should_intercept("other.com") is False
    assert proxy_server.should_intercept("example.org") is False

    # Edge case: wildcard logic check
    # "*.example.com" -> suffix ".example.com"
    # "example.com" does not end with ".example.com"
    assert proxy_server.should_intercept("example.com") is False


@pytest.mark.asyncio
async def test_handle_client_connect(proxy_server):
    reader = AsyncMock()
    writer = AsyncMock()

    reader.readline.return_value = b"CONNECT api.test.com:443 HTTP/1.1\r\n"

    with patch.object(proxy_server, "_handle_connect", AsyncMock()) as mock_handle:
        await proxy_server.handle_client(reader, writer)
        mock_handle.assert_called_once()
        args = mock_handle.call_args[0]
        assert args[2] == "api.test.com:443"

    writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_handle_client_empty(proxy_server):
    reader = AsyncMock()
    writer = AsyncMock()
    reader.readline.return_value = b""

    await proxy_server.handle_client(reader, writer)
    writer.close.assert_called()


@pytest.mark.asyncio
async def test_handle_client_exception(proxy_server):
    reader = AsyncMock()
    writer = AsyncMock()
    reader.readline.side_effect = Exception("Read error")

    # Should log error but not raise (unless CancelledError)
    await proxy_server.handle_client(reader, writer)

    writer.close.assert_called()


@pytest.mark.asyncio
async def test_handle_connect_intercept(proxy_server):
    reader = AsyncMock()
    writer = AsyncMock()
    target = "api.test.com:443"

    # Mock cert manager
    proxy_server.cert_manager.get_domain_cert = MagicMock(
        return_value=("cert_path", "key_path")
    )

    # Mock loop and start_tls
    mock_loop = MagicMock()
    mock_transport = MagicMock()
    mock_loop.start_tls = AsyncMock(return_value=mock_transport)

    # Mock ssl context
    mock_ssl_ctx = MagicMock()

    with (
        patch("asyncio.get_running_loop", return_value=mock_loop),
        patch("ssl.create_default_context", return_value=mock_ssl_ctx),
        patch.object(
            proxy_server.proxy_connector, "create_connection", AsyncMock()
        ) as mock_create_conn,
        patch.object(
            proxy_server, "_forward_data_with_interception", AsyncMock()
        ) as mock_forward,
        patch("asyncio.StreamWriter", MagicMock()),
    ):
        mock_create_conn.return_value = (AsyncMock(), AsyncMock())

        await proxy_server._handle_connect(reader, writer, target)

        proxy_server.cert_manager.get_domain_cert.assert_called_with("api.test.com")
        mock_ssl_ctx.load_cert_chain.assert_called()
        writer.write.assert_called()
        mock_create_conn.assert_called()
        mock_forward.assert_called()


@pytest.mark.asyncio
async def test_handle_connect_no_intercept(proxy_server):
    reader = AsyncMock()
    writer = AsyncMock()
    target = "other.com:443"

    with (
        patch.object(
            proxy_server.proxy_connector, "create_connection", AsyncMock()
        ) as mock_create_conn,
        patch.object(proxy_server, "_forward_data", AsyncMock()) as mock_forward,
        patch("asyncio.gather", AsyncMock()),
    ):
        mock_create_conn.return_value = (AsyncMock(), AsyncMock())

        await proxy_server._handle_connect(reader, writer, target)

        # Should call proxy_connector.create_connection
        mock_create_conn.assert_called_with("other.com", 443, ssl=None)
        # _forward_data is called once with 4 arguments
        assert mock_forward.call_count == 1


def test_parse_args():
    """Test command-line argument parsing for proxy configuration."""
    with patch("argparse.ArgumentParser.parse_args") as mock_parse:
        mock_parse.return_value = argparse.Namespace(
            host="1.2.3.4", port=9999, domains=["*.test.com"], proxy=None
        )
        args = parse_args()
        assert args.host == "1.2.3.4"
        assert args.port == 9999


@pytest.mark.asyncio
async def test_main():
    with (
        patch("stream.main.parse_args") as mock_parse,
        patch("stream.main.ProxyServer") as mock_cls,
        patch("pathlib.Path.mkdir", MagicMock()),
    ):
        mock_parse.return_value = argparse.Namespace(
            host="127.0.0.1", port=3120, domains=["*.google.com"], proxy=None
        )

        mock_instance = AsyncMock()
        mock_cls.return_value = mock_instance

        await main()

        mock_cls.assert_called_once()
        mock_instance.start.assert_called_once()


@pytest.mark.asyncio
async def test_builtin():
    with (
        patch("stream.main.ProxyServer") as mock_cls,
        patch("pathlib.Path.mkdir", MagicMock()),
    ):
        mock_instance = AsyncMock()
        mock_cls.return_value = mock_instance

        await builtin(port=1234)

        mock_cls.assert_called_once()
        assert mock_cls.call_args[1]["port"] == 1234
        mock_instance.start.assert_called_once()
