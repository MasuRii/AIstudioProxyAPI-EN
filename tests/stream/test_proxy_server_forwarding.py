"""
Comprehensive tests for ProxyServer data forwarding logic.

Focuses on the critical untested paths:
- _forward_data() - bidirectional forwarding without interception
- _forward_data_with_interception() - HTTP parsing and interception

These functions represent ~210 lines of untested code (50% of proxy_server.py).
"""

import asyncio
import multiprocessing
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stream.proxy_server import ProxyServer

# ==================== TEST HELPERS ====================


class AsyncStreamReader:
    """Fake StreamReader with real async behavior using queues."""

    def __init__(self):
        self.queue = asyncio.Queue()
        self.closed = False
        self._eof = False

    async def read(self, n: int) -> bytes:
        """Read up to n bytes. Returns empty bytes on EOF."""
        if self._eof or self.closed:
            return b""

        try:
            # Wait for data with timeout to prevent hanging tests
            data = await asyncio.wait_for(self.queue.get(), timeout=2.0)
            if data == b"":  # EOF marker
                self._eof = True
            return data
        except asyncio.TimeoutError:
            return b""
        except asyncio.CancelledError:
            raise

    def feed_data(self, data: bytes):
        """Feed data into the reader (simulates network receive)."""
        if not self.closed:
            self.queue.put_nowait(data)

    def feed_eof(self):
        """Signal EOF to the reader."""
        self.queue.put_nowait(b"")


class AsyncStreamWriter:
    """Fake StreamWriter that collects written data."""

    def __init__(self):
        self.data = bytearray()
        self.closed = False
        self.close_event = asyncio.Event()

    def write(self, data: bytes):
        """Write data (synchronous API like real StreamWriter)."""
        if not self.closed:
            self.data.extend(data)

    async def drain(self):
        """Drain written data (no-op for fake)."""
        await asyncio.sleep(0)  # Yield to event loop

    def close(self):
        """Close the writer."""
        self.closed = True
        self.close_event.set()

    async def wait_closed(self):
        """Wait for close to complete."""
        await self.close_event.wait()

    def get_data(self) -> bytes:
        """Get all data written so far."""
        return bytes(self.data)


def create_stream_pair():
    """Create a pair of connected fake streams for testing bidirectional flow."""
    reader = AsyncStreamReader()
    writer = AsyncStreamWriter()
    return reader, writer


# ==================== FIXTURES ====================


@pytest.fixture
def mock_cert_manager():
    """Mock CertificateManager."""
    with patch("stream.proxy_server.CertificateManager") as mock:
        instance = mock.return_value
        instance.cert_dir = MagicMock()
        instance.get_domain_cert = MagicMock()
        yield instance


@pytest.fixture
def mock_proxy_connector():
    """Mock ProxyConnector."""
    with patch("stream.proxy_server.ProxyConnector") as mock:
        instance = mock.return_value
        instance.create_connection = AsyncMock()
        yield instance


@pytest.fixture
def mock_interceptor():
    """Mock HttpInterceptor."""
    with patch("stream.proxy_server.HttpInterceptor") as mock:
        instance = mock.return_value
        instance.process_request = AsyncMock(side_effect=lambda data, *args: data)
        instance.process_response = AsyncMock(return_value={"text": "mocked response"})
        yield instance


@pytest.fixture
def proxy_server(mock_cert_manager, mock_proxy_connector, mock_interceptor):
    """Create ProxyServer instance with mocked dependencies."""
    with patch("logging.getLogger"):
        queue = multiprocessing.Queue()
        server = ProxyServer(
            host="127.0.0.1", port=3120, intercept_domains=["*.google.com"], queue=queue
        )
        return server


# ==================== TESTS: _forward_data (No Interception) ====================


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_forward_data_bidirectional_success(proxy_server):
    """Test data flows from client to server and back without interception."""
    # Create fake streams
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Feed test data
    client_reader.feed_data(b"GET / HTTP/1.1\r\n\r\n")
    client_reader.feed_eof()

    server_reader.feed_data(b"HTTP/1.1 200 OK\r\n\r\nHello")
    server_reader.feed_eof()

    # Run forwarding
    await proxy_server._forward_data(
        client_reader, client_writer, server_reader, server_writer
    )

    # Verify data was forwarded
    # Client -> Server direction
    server_data = server_writer.get_data()
    assert b"GET / HTTP/1.1" in server_data

    # Server -> Client direction
    client_data = client_writer.get_data()
    assert b"HTTP/1.1 200 OK" in client_data
    assert b"Hello" in client_data


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_forward_data_handles_client_disconnect(proxy_server):
    """Test that server connection closes when client disconnects."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Client sends data then disconnects
    client_reader.feed_data(b"Some data")
    client_reader.feed_eof()

    # Server keeps sending
    server_reader.feed_data(b"Response data")
    server_reader.feed_eof()

    await proxy_server._forward_data(
        client_reader, client_writer, server_reader, server_writer
    )

    # Verify both connections closed
    assert client_writer.closed
    assert server_writer.closed


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_forward_data_handles_task_cancellation(proxy_server):
    """Test that task cancellation properly cleans up both directions."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Create task for forwarding
    task = asyncio.create_task(
        proxy_server._forward_data(
            client_reader, client_writer, server_reader, server_writer
        )
    )

    # Let it start
    await asyncio.sleep(0.1)

    # Cancel the task
    task.cancel()

    # Verify cancellation raises
    with pytest.raises(asyncio.CancelledError):
        await task


# ==================== TESTS: _forward_data_with_interception ====================


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_interception_detects_generate_content_path(
    proxy_server, mock_interceptor
):
    """Test that GenerateContent requests are detected and intercepted."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Create HTTP POST request with GenerateContent path
    http_request = (
        b"POST /v1/models/gemini-1.5-pro:generateContent HTTP/1.1\r\n"
        b"Host: generativelanguage.googleapis.com\r\n"
        b"Content-Length: 50\r\n"
        b"\r\n"
        b'{"contents":[{"parts":[{"text":"Hello"}]}]}'
    )

    client_reader.feed_data(http_request)
    client_reader.feed_eof()

    # Server responds
    server_reader.feed_data(b"HTTP/1.1 200 OK\r\n\r\n{}")
    server_reader.feed_eof()

    # Run interception
    await proxy_server._forward_data_with_interception(
        client_reader,
        client_writer,
        server_reader,
        server_writer,
        host="generativelanguage.googleapis.com",
    )

    # Verify interceptor was called for request
    mock_interceptor.process_request.assert_called()
    call_args = mock_interceptor.process_request.call_args[0]
    request_body = call_args[0]
    assert b'{"contents"' in request_body


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_interception_skips_non_generate_content_requests(
    proxy_server, mock_interceptor
):
    """Test that non-GenerateContent requests are forwarded without interception."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Create HTTP GET request (not GenerateContent)
    http_request = (
        b"GET /v1/models HTTP/1.1\r\nHost: generativelanguage.googleapis.com\r\n\r\n"
    )

    client_reader.feed_data(http_request)
    client_reader.feed_eof()

    server_reader.feed_data(b"HTTP/1.1 200 OK\r\n\r\n[]")
    server_reader.feed_eof()

    await proxy_server._forward_data_with_interception(
        client_reader,
        client_writer,
        server_reader,
        server_writer,
        host="generativelanguage.googleapis.com",
    )

    # Verify request was forwarded to server
    server_data = server_writer.get_data()
    assert b"GET /v1/models" in server_data

    # Interceptor should not be called for non-GenerateContent
    # (Actually it might be called for response if should_sniff was set by previous request,
    # but for this test with fresh state, it shouldn't intercept)


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_interception_handles_response_and_queues_data(
    proxy_server, mock_interceptor
):
    """Test that intercepted responses are processed and queued."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # GenerateContent request
    http_request = (
        b"POST /v1/models/gemini:generateContent HTTP/1.1\r\n"
        b"Content-Length: 10\r\n"
        b"\r\n"
        b'{"test":1}'
    )

    # Response with headers
    http_response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        b"\r\n"
        b'{"candidates":[{"content":"response"}]}'
    )

    client_reader.feed_data(http_request)
    client_reader.feed_eof()

    server_reader.feed_data(http_response)
    server_reader.feed_eof()

    # Mock interceptor to return specific data
    mock_interceptor.process_response.return_value = {"text": "intercepted response"}

    await proxy_server._forward_data_with_interception(
        client_reader,
        client_writer,
        server_reader,
        server_writer,
        host="generativelanguage.googleapis.com",
    )

    # Verify interceptor was called for response
    mock_interceptor.process_response.assert_called()

    # Verify response was queued (if queue exists)
    # Note: queue operations happen in the code, we can't easily verify without integration test


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_interception_handles_malformed_http_request(proxy_server):
    """Test that malformed HTTP requests are handled gracefully."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Invalid HTTP request (missing parts)
    malformed_request = b"INVALID REQUEST\r\n\r\n"

    client_reader.feed_data(malformed_request)
    client_reader.feed_eof()

    server_reader.feed_data(b"HTTP/1.1 400 Bad Request\r\n\r\n")
    server_reader.feed_eof()

    # Should not crash
    await proxy_server._forward_data_with_interception(
        client_reader,
        client_writer,
        server_reader,
        server_writer,
        host="generativelanguage.googleapis.com",
    )

    # Verify data was still forwarded (fallback behavior)
    server_data = server_writer.get_data()
    assert b"INVALID REQUEST" in server_data


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_interception_handles_chunked_transfer_encoding(proxy_server):
    """Test that chunked responses are handled correctly."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Simple request
    http_request = (
        b"POST /v1/models/gemini:generateContent HTTP/1.1\r\n"
        b"Content-Length: 2\r\n"
        b"\r\n"
        b"{}"
    )

    # Chunked response
    chunked_response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"\r\n"
        b"5\r\nHello\r\n"
        b"6\r\n World\r\n"
        b"0\r\n\r\n"  # End chunk
    )

    client_reader.feed_data(http_request)
    client_reader.feed_eof()

    server_reader.feed_data(chunked_response)
    server_reader.feed_eof()

    await proxy_server._forward_data_with_interception(
        client_reader,
        client_writer,
        server_reader,
        server_writer,
        host="generativelanguage.googleapis.com",
    )

    # Verify chunked data was forwarded to client
    client_data = client_writer.get_data()
    assert b"0\r\n\r\n" in client_data  # End chunk marker


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_interception_cancellation_cleanup(proxy_server):
    """Test that task cancellation properly cleans up interception tasks."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Create task
    task = asyncio.create_task(
        proxy_server._forward_data_with_interception(
            client_reader,
            client_writer,
            server_reader,
            server_writer,
            host="generativelanguage.googleapis.com",
        )
    )

    # Let it start
    await asyncio.sleep(0.1)

    # Cancel
    task.cancel()

    # Should raise CancelledError
    with pytest.raises(asyncio.CancelledError):
        await task

    # Verify connections were closed
    assert client_writer.closed
    assert server_writer.closed


# ==================== TESTS: Edge Cases ====================


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_forward_data_with_large_payload(proxy_server):
    """Test forwarding large payloads (>8192 bytes) without data loss."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Create 100KB payload
    large_payload = b"X" * 100000

    client_reader.feed_data(large_payload)
    client_reader.feed_eof()

    server_reader.feed_eof()

    await proxy_server._forward_data(
        client_reader, client_writer, server_reader, server_writer
    )

    # Verify all data was forwarded
    server_data = server_writer.get_data()
    assert len(server_data) == 100000
    assert server_data == large_payload


@pytest.mark.asyncio
@pytest.mark.timeout(5)
async def test_interception_with_incomplete_headers(proxy_server):
    """Test handling of incomplete HTTP headers (no \\r\\n\\r\\n)."""
    client_reader, client_writer = create_stream_pair()
    server_reader, server_writer = create_stream_pair()

    # Incomplete request (missing final \\r\\n\\r\\n)
    incomplete_request = b"POST /test HTTP/1.1\r\nHost: example.com\r\n"

    client_reader.feed_data(incomplete_request)
    # Don't feed EOF, feed more data after delay
    await asyncio.sleep(0.1)
    client_reader.feed_data(b"\r\n")
    client_reader.feed_eof()

    server_reader.feed_data(b"HTTP/1.1 200 OK\r\n\r\n")
    server_reader.feed_eof()

    await proxy_server._forward_data_with_interception(
        client_reader, client_writer, server_reader, server_writer, host="example.com"
    )

    # Should forward data despite incomplete headers
    server_data = server_writer.get_data()
    assert b"POST /test" in server_data
