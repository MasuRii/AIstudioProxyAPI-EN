import base64
import json
import queue
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from api_utils.utils_ext.files import (
    _extension_for_mime,
    extract_data_url_to_local,
    save_blob_to_local,
)
from api_utils.utils_ext.helper import use_helper_get_response
from api_utils.utils_ext.stream import clear_stream_queue, use_stream_response
from api_utils.utils_ext.tokens import calculate_usage_stats, estimate_tokens
from api_utils.utils_ext.validation import validate_chat_request
from models import Message

# --- tokens.py tests ---


def test_estimate_tokens():
    """Test token estimation for empty, English, and mixed text."""
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0  # type: ignore[arg-type]

    # English: 1 char = 0.25 tokens -> 4 chars = 1 token
    assert estimate_tokens("abcd") == 1

    # Mixed/Other: logic is approx chars / 1.5
    assert estimate_tokens("hello") == 1


def test_calculate_usage_stats():
    """Test token usage statistics calculation for messages and responses."""
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    response = "response"
    reasoning = "reasoning"

    stats = calculate_usage_stats(messages, response, reasoning)

    assert "prompt_tokens" in stats
    assert "completion_tokens" in stats
    assert "total_tokens" in stats
    assert stats["total_tokens"] == stats["prompt_tokens"] + stats["completion_tokens"]


# --- validation.py tests ---


def test_validate_chat_request_valid():
    """Test validation passes with valid system and user messages."""
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="user"),
    ]
    result = validate_chat_request(messages, "req1")
    assert result["error"] is None


def test_validate_chat_request_empty():
    """Test validation raises error for empty message array."""
    with pytest.raises(ValueError):
        validate_chat_request([], "req1")


def test_validate_chat_request_only_system():
    """Test validation raises error when all messages are system messages."""
    messages = [Message(role="system", content="sys")]
    with pytest.raises(ValueError):
        validate_chat_request(messages, "req1")


# --- files.py tests ---


def test_extension_for_mime():
    """Test file extension detection from MIME types."""
    assert _extension_for_mime("image/png") == ".png"
    assert _extension_for_mime("application/unknown") == ".unknown"
    assert _extension_for_mime("plain") == ".bin"
    assert _extension_for_mime(None) == ".bin"  # type: ignore[arg-type]


def test_extract_data_url_to_local_success():
    """Test successful extraction of data URL to local file."""
    data = b"hello world"
    b64_data = base64.b64encode(data).decode()
    data_url = f"data:text/plain;base64,{b64_data}"

    with (
        patch("server.logger"),
        patch("config.UPLOAD_FILES_DIR", "/tmp/uploads"),
        patch("os.makedirs"),
        patch("os.path.exists", return_value=False),
        patch("builtins.open", mock_open()) as mock_file,
    ):
        path = extract_data_url_to_local(data_url, "req1")

        assert path is not None
        assert path.endswith(".txt")
        mock_file().write.assert_called_with(data)


def test_extract_data_url_to_local_invalid_format():
    """Test data URL extraction fails gracefully with invalid format."""
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        assert extract_data_url_to_local("invalid-url") is None
        mock_logger.error.assert_called()


def test_extract_data_url_to_local_bad_b64():
    """Test data URL extraction handles base64 decode errors."""
    import binascii

    with (
        patch("logging.getLogger") as mock_get_logger,
        patch("base64.b64decode", side_effect=binascii.Error("Invalid")),
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        assert extract_data_url_to_local("data:text/plain;base64,!!!") is None
        mock_logger.error.assert_called()


def test_extract_data_url_to_local_exists():
    """Test data URL extraction when file already exists."""
    data_url = "data:text/plain;base64,AAAA"
    with (
        patch("server.logger"),
        patch("config.UPLOAD_FILES_DIR", "/tmp/uploads"),
        patch("os.makedirs"),
        patch("os.path.exists", return_value=True),
    ):
        path = extract_data_url_to_local(data_url)
        assert path is not None


def test_save_blob_to_local():
    """Test saving blob data to local file with various extensions."""
    data = b"test"
    with (
        patch("server.logger"),
        patch("config.UPLOAD_FILES_DIR", "/tmp/uploads"),
        patch("os.makedirs"),
        patch("os.path.exists", return_value=False),
        patch("builtins.open", mock_open()),
    ):
        # Test with mime
        path = save_blob_to_local(data, mime_type="image/png")
        assert path is not None
        assert path.endswith(".png")

        # Test with ext
        path = save_blob_to_local(data, fmt_ext=".jpg")
        assert path is not None
        assert path.endswith(".jpg")

        # Test fallback
        path = save_blob_to_local(data)
        assert path is not None
        assert path.endswith(".bin")


# --- helper.py tests ---


@pytest.mark.asyncio
async def test_use_helper_get_response_success():
    with patch("server.logger"), patch("aiohttp.ClientSession") as MockSession:

        async def mock_iter_chunked(n):
            yield b"chunk1"
            yield b"chunk2"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.content.iter_chunked = MagicMock(side_effect=mock_iter_chunked)

        # session.get is NOT awaited, it returns a context manager immediately.
        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        # ClientSession() returns a context manager.
        MockSession.return_value.__aenter__.return_value = mock_session

        chunks = []
        async for chunk in use_helper_get_response("http://helper", "sap"):
            chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2"]


@pytest.mark.asyncio
async def test_use_helper_get_response_error():
    with (
        patch("server.logger") as mock_logger,
        patch("aiohttp.ClientSession") as MockSession,
    ):
        mock_resp = AsyncMock()
        mock_resp.status = 500

        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        MockSession.return_value.__aenter__.return_value = mock_session

        chunks = []
        async for chunk in use_helper_get_response("http://helper", "sap"):
            chunks.append(chunk)

        assert len(chunks) == 0
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_use_helper_get_response_exception():
    with (
        patch("server.logger") as mock_logger,
        patch("aiohttp.ClientSession", side_effect=Exception("Network Error")),
    ):
        chunks = []
        async for chunk in use_helper_get_response("http://helper", "sap"):
            chunks.append(chunk)

        assert len(chunks) == 0
        mock_logger.error.assert_called()


# --- stream.py tests ---


@pytest.mark.asyncio
async def test_use_stream_response_success():
    # Setup queue data
    q_data = [
        json.dumps({"body": "chunk1", "done": False}),
        json.dumps({"body": "chunk2", "done": True}),
    ]

    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = q_data + [queue.Empty()]

    with patch("server.STREAM_QUEUE", mock_queue), patch("server.logger"):
        chunks = []
        async for chunk in use_stream_response("req1", enable_silence_detection=True):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0]["body"] == "chunk1"
        assert chunks[1]["done"] is True


@pytest.mark.asyncio
async def test_use_stream_response_queue_none():
    with patch("server.STREAM_QUEUE", None), patch("server.logger") as mock_logger:
        chunks = []
        async for chunk in use_stream_response("req1", enable_silence_detection=True):
            chunks.append(chunk)

        assert len(chunks) == 0
        mock_logger.warning.assert_called_with(
            "[req1] STREAM_QUEUE is None, cannot use stream response"
        )


@pytest.mark.asyncio
async def test_use_stream_response_timeout():
    # Simulate queue empty until timeout
    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = queue.Empty

    with (
        patch("server.STREAM_QUEUE", mock_queue),
        patch("server.logger"),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        chunks = []
        async for chunk in use_stream_response("req1", enable_silence_detection=True):
            chunks.append(chunk)

        # Should yield timeout error
        assert len(chunks) == 1
        assert chunks[0]["reason"] == "internal_timeout"
        assert chunks[0]["done"] is True
        # Should have slept
        assert mock_sleep.call_count >= 1


@pytest.mark.asyncio
async def test_use_stream_response_mixed_types():
    # Test non-JSON string and dictionary data
    q_data = [
        "not-json",  # Should trigger JSONDecodeError path
        {"body": "dict-body", "done": False},  # Dictionary directly
        json.dumps({"body": "final", "done": True}),
    ]

    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = q_data

    with patch("server.STREAM_QUEUE", mock_queue), patch("server.logger"):
        chunks = []
        async for chunk in use_stream_response("req1", enable_silence_detection=True):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0] == "not-json"
        assert chunks[1]["body"] == "dict-body"
        assert chunks[2]["done"] is True


@pytest.mark.asyncio
async def test_use_stream_response_ignore_stale_done():
    # First item is done=True with no content (stale), should be ignored
    # Second item is real content
    # Third item is real done
    q_data = [
        json.dumps({"done": True, "body": "", "reason": ""}),
        json.dumps({"body": "real content", "done": False}),
        json.dumps({"done": True, "body": "", "reason": ""}),
    ]

    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = q_data

    with patch("server.STREAM_QUEUE", mock_queue), patch("server.logger"):
        chunks = []
        async for chunk in use_stream_response("req1", enable_silence_detection=True):
            chunks.append(chunk)

        # Should contain 2 items: real content and final done. Stale done ignored.
        assert len(chunks) == 2
        assert chunks[0]["body"] == "real content"
        assert chunks[1]["done"] is True


@pytest.mark.asyncio
async def test_clear_stream_queue():
    mock_queue = MagicMock()
    # 2 items then Empty
    mock_queue.get_nowait.side_effect = ["item1", "item2", queue.Empty]

    with (
        patch("server.STREAM_QUEUE", mock_queue),
        patch("server.logger") as mock_logger,
        patch("asyncio.to_thread", side_effect=mock_queue.get_nowait),
    ):
        await clear_stream_queue()

        # Should have called get_nowait 3 times via to_thread
        # Verify debug log for queue cleared
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Stream queue cleared" in c for c in info_calls)


@pytest.mark.asyncio
async def test_clear_stream_queue_none():
    with patch("server.STREAM_QUEUE", None), patch("server.logger"):
        await clear_stream_queue()
        # Should do nothing and not log anything related to clearing


"""
Extended tests for api_utils/utils_ext/stream.py - Edge case coverage.

Focus: Cover uncovered error paths, exception handling, and edge cases.
Strategy: Test None signal, error detection, dict stale data, exceptions.
"""

from models.exceptions import QuotaExceededError, UpstreamError


@pytest.mark.asyncio
async def test_use_stream_response_none_signal():
    """
    Test scenario: Received None as stream end signal
    Expected: End normally, return nothing (lines 28-30)
    """
    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = [None]  # None is end signal

    with patch("server.STREAM_QUEUE", mock_queue), patch("server.logger"):
        chunks = []
        async for chunk in use_stream_response("req1", enable_silence_detection=True):
            chunks.append(chunk)

        assert len(chunks) == 0  # None signal produces no output


@pytest.mark.asyncio
async def test_use_stream_response_quota_exceeded_error():
    """
    Test scenario: Received quota error signal (status 429)
    Expected: Throw QuotaExceededError (lines 44-65)
    """
    error_data = json.dumps(
        {"error": True, "status": 429, "message": "Quota exceeded for this project"}
    )

    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = [error_data]

    with patch("server.STREAM_QUEUE", mock_queue), patch("server.logger"):
        with pytest.raises(QuotaExceededError) as exc_info:
            async for chunk in use_stream_response(
                "req1", enable_silence_detection=True
            ):
                pass

        assert "AI Studio quota exceeded" in str(exc_info.value)
        assert exc_info.value.req_id == "req1"


@pytest.mark.asyncio
async def test_use_stream_response_quota_error_by_message():
    """
    Test scenario: Error message contains "quota" keyword
    Expected: Throw QuotaExceededError (lines 58-65)
    """
    error_data = json.dumps(
        {"error": True, "status": 500, "message": "Your project quota has been reached"}
    )

    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = [error_data]

    with patch("server.STREAM_QUEUE", mock_queue), patch("server.logger"):
        with pytest.raises(QuotaExceededError):
            async for chunk in use_stream_response(
                "req1", enable_silence_detection=True
            ):
                pass


@pytest.mark.asyncio
async def test_use_stream_response_upstream_error():
    """
    Test scenario: Received non-quota upstream error (status 500)
    Expected: Throw UpstreamError (lines 66-74)
    """
    error_data = json.dumps(
        {"error": True, "status": 500, "message": "Internal server error"}
    )

    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = [error_data]

    with patch("server.STREAM_QUEUE", mock_queue), patch("server.logger"):
        with pytest.raises(UpstreamError) as exc_info:
            async for chunk in use_stream_response(
                "req1", enable_silence_detection=True
            ):
                pass

        assert "AI Studio error" in str(exc_info.value)
        # status_code is stored in context dict, not direct attribute
        assert exc_info.value.context.get("status_code") == 500


@pytest.mark.asyncio
async def test_use_stream_response_dict_with_stale_done():
    """
    Test scenario: Dictionary format data, first is stale done (no content)
    Expected: Yields stale done, continues instead of breaking (lines 116-129)
    Note: Dict format ALWAYS yields first (line 109), then checks stale.
    """
    q_data = [
        {"done": True, "body": "", "reason": ""},  # Stale done (dict format)
        {"body": "real content", "done": False},  # Real data
        {"done": True, "body": "final", "reason": ""},  # Real done
    ]

    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = q_data

    with (
        patch("server.STREAM_QUEUE", mock_queue),
        patch("server.logger"),
    ):
        chunks = []
        async for chunk in use_stream_response("req1", enable_silence_detection=True):
            chunks.append(chunk)

        # Dict always yields first, so all 3 chunks yielded
        # But stale detection prevents breaking on first done
        assert len(chunks) == 3
        assert chunks[0]["done"] is True  # Stale done yielded
        assert chunks[1]["body"] == "real content"
        assert chunks[2]["done"] is True  # Real done


@pytest.mark.asyncio
async def test_use_stream_response_timeout_after_data():
    """
    Test scenario: Timeout after receiving partial data
    Expected: Log warning and return timeout signal (line 144)
    """
    q_data = [
        json.dumps({"body": "some data", "done": False}),
    ] + [queue.Empty] * 1000  # Receive data first, then empty

    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = q_data

    with (
        patch("server.STREAM_QUEUE", mock_queue),
        patch("server.logger"),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        chunks = []
        async for chunk in use_stream_response("req1", enable_silence_detection=True):
            chunks.append(chunk)

        # Should have data chunk + timeout chunk
        assert len(chunks) == 2
        assert chunks[0]["body"] == "some data"
        assert chunks[1]["reason"] == "internal_timeout"


@pytest.mark.asyncio
async def test_use_stream_response_generic_exception():
    """
    Test scenario: Exception during processing
    Expected: Log error and re-throw (lines 156-158)
    """
    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = RuntimeError("Unexpected error")

    with (
        patch("server.STREAM_QUEUE", mock_queue),
        patch("server.logger") as mock_logger,
    ):
        with pytest.raises(RuntimeError, match="Unexpected error"):
            async for chunk in use_stream_response(
                "req1", enable_silence_detection=True
            ):
                pass

        # Verify error was logged (line 157)
        error_calls = [
            c
            for c in mock_logger.error.call_args_list
            if "Error in stream generator" in str(c)
        ]
        assert len(error_calls) > 0


@pytest.mark.asyncio
async def test_clear_stream_queue_exception_during_clear():
    """
    Test scenario: Exception while clearing queue
    Expected: Log error and stop clearing (lines 189-194)
    """
    mock_queue = MagicMock()
    # Get 2 items, then raise exception
    mock_queue.get_nowait.side_effect = ["item1", "item2", RuntimeError("Queue error")]

    with (
        patch("server.STREAM_QUEUE", mock_queue),
        patch("server.logger"),
    ):
        await clear_stream_queue()

        # Should have gotten 2 items before exception
        assert mock_queue.get_nowait.call_count == 3


@pytest.mark.asyncio
async def test_clear_stream_queue_empty_queue():
    """
    Test scenario: Clear an empty queue
    Expected: Log info message
    """
    mock_queue = MagicMock()
    mock_queue.get_nowait.side_effect = queue.Empty  # Immediately empty

    with (
        patch("server.STREAM_QUEUE", mock_queue),
        patch("server.logger"),
        patch("asyncio.to_thread", side_effect=queue.Empty),
    ):
        await clear_stream_queue()


"""
Extended tests for api_utils/utils_ext/files.py - Final coverage completion.

Focus: Cover lines 78-80 (IOError in extract_data_url_to_local),
       107-108 (file exists in save_blob_to_local),
       114-116 (IOError in save_blob_to_local).
Strategy: Mock file operations to trigger error paths.
"""


def test_extract_data_url_to_local_write_failure():
    """
    Test scenario: IOError during file write
    Expected: Log error, return None (lines 78-80)
    """
    data = b"test data"
    b64_data = base64.b64encode(data).decode()
    data_url = f"data:text/plain;base64,{b64_data}"

    with (
        patch("logging.getLogger") as mock_get_logger,
        patch("config.UPLOAD_FILES_DIR", "/tmp/uploads"),
        patch("os.makedirs"),
        patch("os.path.exists", return_value=False),
        patch("builtins.open", side_effect=IOError("Disk full")),
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        # Execute
        result = extract_data_url_to_local(data_url, "req1")

        # Verify: Return None (line 80)
        assert result is None

        # Verify: logger.error called (line 79)
        mock_logger.error.assert_called()


def test_save_blob_to_local_file_exists():
    """
    Test scenario: File already exists, skip saving
    Expected: Log message, return file path (lines 106-108)
    """
    data = b"binary data"

    with (
        patch("logging.getLogger") as mock_get_logger,
        patch("config.UPLOAD_FILES_DIR", "/tmp/uploads"),
        patch("os.makedirs"),
        patch("os.path.exists", return_value=True),  # File exists
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        # Execute
        result = save_blob_to_local(data, mime_type="image/png", req_id="req1")

        # Verify: Return path (line 108)
        assert result is not None
        assert result.endswith(".png")

        # Verify: logger.info called (line 107)
        mock_logger.info.assert_called()


def test_save_blob_to_local_write_failure():
    """
    Test scenario: IOError during binary file write
    Expected: Log error, return None (lines 114-116)
    """
    data = b"test binary"

    with (
        patch("logging.getLogger") as mock_get_logger,
        patch("config.UPLOAD_FILES_DIR", "/tmp/uploads"),
        patch("os.makedirs"),
        patch("os.path.exists", return_value=False),
        patch("builtins.open", side_effect=IOError("Permission denied")),
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        # Execute
        result = save_blob_to_local(data, mime_type="application/pdf")

        # Verify: Return None (line 116)
        assert result is None

        # Verify: logger.error called (line 115)
        mock_logger.error.assert_called()
