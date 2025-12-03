import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stream.proxy_server import ProxyServer


class TestProxyServer:
    @pytest.fixture
    def mock_cert_manager(self):
        with patch("stream.proxy_server.CertificateManager") as mock:
            instance = mock.return_value
            # Mock cert dir path
            instance.cert_dir = MagicMock()
            instance.cert_dir.__truediv__.return_value = "path/to/cert"
            yield instance

    @pytest.fixture
    def mock_connector(self):
        with patch("stream.proxy_server.ProxyConnector") as mock:
            instance = mock.return_value
            # Make create_connection async and return tuple (reader, writer)
            instance.create_connection = AsyncMock()
            instance.create_connection.return_value = (AsyncMock(), MagicMock())
            yield instance

    @pytest.fixture
    def mock_interceptor(self):
        with patch("stream.proxy_server.HttpInterceptor") as mock:
            yield mock.return_value

    @pytest.fixture
    def mock_path(self):
        with patch("stream.proxy_server.Path") as mock:
            yield mock

    @pytest.fixture
    def server(self, mock_cert_manager, mock_connector, mock_interceptor, mock_path):
        return ProxyServer(intercept_domains=["example.com", "*.google.com"])

    def test_should_intercept(self, server):
        """Test domain interception matching (exact, wildcard, subdomain logic)."""
        # Exact match
        assert server.should_intercept("example.com")
        # No match
        assert not server.should_intercept("other.com")
        # Wildcard match
        assert server.should_intercept("mail.google.com")
        # Wildcard logic: d[1:] is ".google.com". "google.com" ends with ".google.com"?
        # "google.com" does NOT end with ".google.com".
        # So it matches subdomains only.
        assert not server.should_intercept("google.com")

    @pytest.fixture
    def mock_writer(self):
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()
        writer.close = MagicMock()
        return writer

    @pytest.mark.asyncio
    async def test_handle_client_connect_intercept(self, server, mock_writer):
        # Setup mocks
        reader = AsyncMock()
        writer = mock_writer

        # Mock request line
        reader.readline.return_value = b"CONNECT example.com:443 HTTP/1.1"

        # Mock _handle_connect to verify it's called
        with patch.object(
            server, "_handle_connect", new_callable=AsyncMock
        ) as mock_handle_connect:
            await server.handle_client(reader, writer)

            mock_handle_connect.assert_called_once_with(
                reader, writer, "example.com:443"
            )

    @pytest.mark.asyncio
    async def test_handle_client_not_connect(self, server, mock_writer):
        reader = AsyncMock()
        writer = mock_writer

        # Non-CONNECT method
        reader.readline.return_value = b"GET http://example.com/ HTTP/1.1"

        await server.handle_client(reader, writer)

        # Verify writer closed
        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_handle_client_empty_request(self, server, mock_writer):
        reader = AsyncMock()
        writer = mock_writer

        # Empty request line
        reader.readline.return_value = b""

        await server.handle_client(reader, writer)

        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_handle_connect_no_intercept(
        self, server, mock_connector, mock_writer
    ):
        # intercept_domains does not include example.org
        reader = AsyncMock()
        writer = mock_writer

        # Mock _forward_data
        with patch.object(
            server, "_forward_data", new_callable=AsyncMock
        ) as mock_forward:
            await server._handle_connect(reader, writer, "example.org:443")

            # Verify 200 OK sent
            writer.write.assert_called_with(
                b"HTTP/1.1 200 Connection Established\r\n\r\n"
            )

            # Verify connection to upstream (no SSL)
            mock_connector.create_connection.assert_called_with(
                "example.org", 443, ssl=None
            )

            # Verify forward called
            mock_forward.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_connect_intercept_flow(
        self, server, mock_cert_manager, mock_connector, mock_writer
    ):
        # Target example.com (in intercept list)
        reader = AsyncMock()
        writer = mock_writer

        # Mock transport for TLS upgrade
        transport = MagicMock()
        writer.transport = transport
        transport.get_protocol.return_value = MagicMock()

        # Mock loop.start_tls
        loop = MagicMock()
        loop.start_tls = AsyncMock(return_value="new_transport")

        # Mock asyncio.StreamWriter to return a mock
        mock_client_writer = MagicMock()
        mock_client_writer.wait_closed = AsyncMock()
        mock_client_writer.close = MagicMock()

        with (
            patch("asyncio.get_running_loop", return_value=loop),
            patch.object(
                server, "_forward_data_with_interception", new_callable=AsyncMock
            ) as mock_forward_intercept,
            patch("ssl.create_default_context"),
            patch("asyncio.StreamWriter", return_value=mock_client_writer),
        ):
            await server._handle_connect(reader, writer, "example.com:443")

            # Verify cert generation
            mock_cert_manager.get_domain_cert.assert_called_with("example.com")

            # Verify TLS upgrade
            loop.start_tls.assert_called()

            # Verify upstream connection with SSL
            mock_connector.create_connection.assert_called()
            args, kwargs = mock_connector.create_connection.call_args
            assert kwargs["ssl"] is not None

            # Verify interception forwarder called
            mock_forward_intercept.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_data_basic(self, server, mock_writer):
        # Test _forward_data simple flow
        c_reader = AsyncMock()
        c_writer = mock_writer
        s_reader = AsyncMock()

        s_writer = MagicMock()
        s_writer.drain = AsyncMock()
        s_writer.wait_closed = AsyncMock()
        s_writer.close = MagicMock()

        # Mock read to return data then EOF
        c_reader.read.side_effect = [b"data1", b""]

        # s_reader is slow so it will be cancelled when c_reader finishes
        async def slow_read(*args, **kwargs):
            await asyncio.sleep(0.1)
            return b""

        s_reader.read.side_effect = slow_read

        await server._forward_data(c_reader, c_writer, s_reader, s_writer)

        # Verify writes
        # client_to_server task reads c_reader and writes to s_writer
        s_writer.write.assert_called_with(b"data1")

        # server_to_client task reads s_reader (slow) and writes to c_writer
        # Since it's slow, it might not have written anything before cancellation
        # c_writer.write.assert_called_with(b"data2")

        # Verify closes
        c_writer.close.assert_called()
        s_writer.close.assert_called()

    def test_should_intercept_wildcard(self, server):
        """Test wildcard domain interception (matches subdomains only)."""
        server.intercept_domains = ["*.example.com"]
        assert server.should_intercept("sub.example.com") is True
        assert server.should_intercept("example.com") is False
        assert server.should_intercept("other.com") is False

    @pytest.mark.asyncio
    async def test_handle_client_cancellation(self, server, mock_writer):
        mock_reader = AsyncMock()
        mock_reader.readline.side_effect = asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await server.handle_client(mock_reader, mock_writer)

    @pytest.mark.asyncio
    async def test_forward_data_cancellation(self, server, mock_writer):
        # Test cancellation for basic forward data
        c_reader = AsyncMock()
        c_writer = mock_writer
        s_reader = AsyncMock()

        s_writer = MagicMock()
        s_writer.drain = AsyncMock()
        s_writer.wait_closed = AsyncMock()
        s_writer.close = MagicMock()

        # Define slow read
        async def slow_read(*args, **kwargs):
            await asyncio.sleep(2)
            return b""

        c_reader.read.side_effect = slow_read
        s_reader.read.side_effect = slow_read

        task = asyncio.create_task(
            server._forward_data(c_reader, c_writer, s_reader, s_writer)
        )

        await asyncio.sleep(0.1)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_handle_client_close_error(self, server, mock_writer):
        # Test error during writer.wait_closed
        mock_reader = AsyncMock()
        mock_reader.readline.return_value = b""  # Empty request triggers close

        mock_writer.wait_closed.side_effect = Exception("Close error")

        await server.handle_client(mock_reader, mock_writer)

        # Should not raise exception
        mock_writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_server_start_queue_ready(self, server):
        mock_queue = MagicMock()
        server.queue = mock_queue

        # Mock asyncio.start_server to return a mock server
        mock_server = AsyncMock()
        mock_server.sockets = [MagicMock()]
        mock_server.sockets[0].getsockname.return_value = ("127.0.0.1", 8080)

        # We need to mock serve_forever to stop immediately or throw exception to exit
        mock_server.serve_forever.side_effect = asyncio.CancelledError()

        with patch("asyncio.start_server", return_value=mock_server):
            try:
                await server.start()
            except asyncio.CancelledError:
                pass

        mock_queue.put.assert_called_with("READY")

    @pytest.mark.asyncio
    async def test_forward_data_with_interception_flow(self, server, mock_writer):
        # Setup mocks for interception flow
        client_reader = AsyncMock()
        client_writer = mock_writer
        server_reader = AsyncMock()
        server_writer = MagicMock()
        server_writer.drain = AsyncMock()
        server_writer.wait_closed = AsyncMock()
        server_writer.close = MagicMock()

        # Mock client sending a request to be intercepted
        request_data = (
            b"POST /generateContent HTTP/1.1\r\nHost: example.com\r\n\r\nBody"
        )
        client_reader.read.side_effect = [request_data, b""]

        # Mock server sending a response
        response_data = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{}"
        server_reader.read.side_effect = [response_data, b""]

        # Mock interceptor
        server.interceptor.process_request = AsyncMock(return_value=b"Body")
        server.interceptor.process_response = AsyncMock(return_value={"data": "test"})

        # Mock queue
        server.queue = MagicMock()

        await server._forward_data_with_interception(
            client_reader, client_writer, server_reader, server_writer, "example.com"
        )

        # Verify interception occurred
        server.interceptor.process_request.assert_called()
        server.interceptor.process_response.assert_called()
        server.queue.put.assert_called()

    @pytest.mark.asyncio
    async def test_forward_data_with_interception_flow_slow_cancellation(
        self, server, mock_writer
    ):
        # Test cancellation of pending task when one side finishes first
        client_reader = AsyncMock()
        client_writer = mock_writer
        server_reader = AsyncMock()
        server_writer = MagicMock()
        server_writer.drain = AsyncMock()
        server_writer.wait_closed = AsyncMock()
        server_writer.close = MagicMock()

        # Client sends request fast
        request_data = (
            b"POST /generateContent HTTP/1.1\r\nHost: example.com\r\n\r\nBody"
        )
        client_reader.read.side_effect = [request_data, b""]

        # Server is slow
        async def slow_read(*args, **kwargs):
            await asyncio.sleep(0.1)
            return b""

        server_reader.read.side_effect = slow_read

        server.interceptor.process_request = AsyncMock(return_value=b"Body")
        server.queue = MagicMock()

        await server._forward_data_with_interception(
            client_reader, client_writer, server_reader, server_writer, "example.com"
        )

        # This should complete without error, and server reader task should be cancelled internally
        server.interceptor.process_request.assert_called()

    @pytest.mark.asyncio
    async def test_forward_data_with_interception_no_sniff(self, server, mock_writer):
        # Path does not contain GenerateContent
        client_reader = AsyncMock()
        client_writer = mock_writer
        server_reader = AsyncMock()
        server_writer = MagicMock()
        server_writer.drain = AsyncMock()
        server_writer.wait_closed = AsyncMock()
        server_writer.close = MagicMock()

        # Capture written data because mock stores reference to mutable bytearray
        written_data = []

        def capture_write(data):
            written_data.append(bytes(data))

        server_writer.write.side_effect = capture_write

        request_data = b"POST /other/path HTTP/1.1\r\nHost: example.com\r\n\r\nBody"
        client_reader.read.side_effect = [request_data, b""]
        server_reader.read.side_effect = [
            b"",
            b"",
        ]  # No response needed for this test part

        server.interceptor.process_request = AsyncMock()

        await server._forward_data_with_interception(
            client_reader, client_writer, server_reader, server_writer, "example.com"
        )

        # Should not call process_request
        server.interceptor.process_request.assert_not_called()
        # Should write original buffer
        assert b"".join(written_data) == request_data

    @pytest.mark.asyncio
    async def test_forward_data_with_interception_cancellation(
        self, server, mock_writer
    ):
        client_reader = AsyncMock()
        client_writer = mock_writer
        server_reader = AsyncMock()
        server_writer = MagicMock()
        server_writer.drain = AsyncMock()
        server_writer.wait_closed = AsyncMock()
        server_writer.close = MagicMock()

        # Slow read to allow cancellation
        async def slow_read(*args, **kwargs):
            await asyncio.sleep(2)
            return b""

        client_reader.read.side_effect = slow_read
        server_reader.read.side_effect = slow_read

        task = asyncio.create_task(
            server._forward_data_with_interception(
                client_reader,
                client_writer,
                server_reader,
                server_writer,
                "example.com",
            )
        )

        await asyncio.sleep(0.1)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_start_server_queue_error(self, server):
        mock_queue = MagicMock()
        server.queue = mock_queue
        mock_queue.put.side_effect = Exception("Queue error")

        mock_server = AsyncMock()
        mock_server.sockets = [MagicMock()]
        mock_server.sockets[0].getsockname.return_value = ("127.0.0.1", 8080)
        mock_server.serve_forever.side_effect = asyncio.CancelledError()

        with patch("asyncio.start_server", return_value=mock_server):
            try:
                await server.start()
            except asyncio.CancelledError:
                pass

        # Should log error but not crash before serve_forever
        # If it crashed, serve_forever wouldn't be called (but we mocked it to raise CancelledError)
        # We can check if logger.error was called
        # But we didn't mock logger in fixture explicitly, it uses real logger or default.
        # Let's check if queue.put was called.
        mock_queue.put.assert_called_with("READY")
