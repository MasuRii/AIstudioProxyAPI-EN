"""
Tests for stream/main.py - Entry point coverage.

Focus: Cover missing lines (66, 79-85, 110, 123-129).
Strategy: Test exception handlers, upstream proxy logging, default port assignment.
"""

import asyncio
import runpy
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_main_module_as_main():
    """
    测试场景: 以 __main__ 模式执行模块
    预期: 覆盖 line 129 (if __name__ == "__main__")
    """
    # Mock ProxyServer to avoid actually starting the proxy
    with (
        patch("stream.main.ProxyServer") as mock_proxy_class,
        patch("stream.main.parse_args") as mock_parse,
        patch("stream.main.asyncio.run") as mock_asyncio_run,
    ):
        mock_proxy = AsyncMock()
        mock_proxy.start = AsyncMock()
        mock_proxy_class.return_value = mock_proxy

        # Provide test arguments
        mock_args = MagicMock()
        mock_args.host = "127.0.0.1"
        mock_args.port = 3120
        mock_args.domains = ["*.google.com"]
        mock_args.proxy = None
        mock_parse.return_value = mock_args

        # Temporarily replace sys.argv to avoid argument parsing errors
        original_argv = sys.argv
        try:
            sys.argv = ["stream.main"]

            # Execute module as __main__ (covers line 129)
            runpy.run_module("stream.main", run_name="__main__")

            # Verify asyncio.run was called with main() (line 129)
            mock_asyncio_run.assert_called_once()
        finally:
            sys.argv = original_argv


@pytest.mark.asyncio
async def test_main_with_upstream_proxy_logging():
    """
    测试场景: main() 函数使用上游代理时的日志输出
    预期: 覆盖 line 66 (if args.proxy: logger.info(...))
    """
    with (
        patch("stream.main.parse_args") as mock_parse,
        patch("stream.main.ProxyServer") as mock_proxy_class,
        patch("stream.main.logging.getLogger") as mock_get_logger,
    ):
        # Mock logger to capture log calls
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Mock arguments with upstream proxy
        mock_args = MagicMock()
        mock_args.host = "127.0.0.1"
        mock_args.port = 3120
        mock_args.domains = ["*.google.com"]
        mock_args.proxy = "http://upstream-proxy:8080"  # CRITICAL: upstream proxy set
        mock_parse.return_value = mock_args

        # Mock ProxyServer to raise KeyboardInterrupt immediately
        mock_proxy = AsyncMock()
        mock_proxy.start = AsyncMock(side_effect=KeyboardInterrupt)
        mock_proxy_class.return_value = mock_proxy

        # Import main function
        from stream.main import main

        # Run main() and expect KeyboardInterrupt to be caught
        await main()

        # Verify upstream proxy was logged (line 66)
        mock_logger.info.assert_any_call(
            "Using upstream proxy: http://upstream-proxy:8080"
        )


@pytest.mark.asyncio
async def test_main_keyboard_interrupt_handling():
    """
    测试场景: main() 函数处理 KeyboardInterrupt 异常
    预期: 覆盖 lines 79-80 (except KeyboardInterrupt: logger.info(...))
    """
    with (
        patch("stream.main.parse_args") as mock_parse,
        patch("stream.main.ProxyServer") as mock_proxy_class,
        patch("stream.main.logging.getLogger") as mock_get_logger,
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_args = MagicMock()
        mock_args.host = "127.0.0.1"
        mock_args.port = 3120
        mock_args.domains = ["*.google.com"]
        mock_args.proxy = None
        mock_parse.return_value = mock_args

        # Mock ProxyServer.start() to raise KeyboardInterrupt
        mock_proxy = AsyncMock()
        mock_proxy.start = AsyncMock(side_effect=KeyboardInterrupt)
        mock_proxy_class.return_value = mock_proxy

        from stream.main import main

        # Run main() - KeyboardInterrupt should be caught
        await main()

        # Verify shutdown message was logged (line 80)
        mock_logger.info.assert_any_call("Shutting down proxy server")


@pytest.mark.asyncio
async def test_main_cancelled_error_re_raising():
    """
    测试场景: main() 函数重新抛出 CancelledError
    预期: 覆盖 lines 81-82 (except asyncio.CancelledError: raise)
    """
    with (
        patch("stream.main.parse_args") as mock_parse,
        patch("stream.main.ProxyServer") as mock_proxy_class,
    ):
        mock_args = MagicMock()
        mock_args.host = "127.0.0.1"
        mock_args.port = 3120
        mock_args.domains = ["*.google.com"]
        mock_args.proxy = None
        mock_parse.return_value = mock_args

        # Mock ProxyServer.start() to raise CancelledError
        mock_proxy = AsyncMock()
        mock_proxy.start = AsyncMock(side_effect=asyncio.CancelledError)
        mock_proxy_class.return_value = mock_proxy

        from stream.main import main

        # Run main() - CancelledError should be re-raised
        with pytest.raises(asyncio.CancelledError):
            await main()


@pytest.mark.asyncio
async def test_main_generic_exception_handling():
    """
    测试场景: main() 函数处理通用异常并退出
    预期: 覆盖 lines 83-85 (except Exception: logger.error(...); sys.exit(1))
    """
    with (
        patch("stream.main.parse_args") as mock_parse,
        patch("stream.main.ProxyServer") as mock_proxy_class,
        patch("stream.main.logging.getLogger") as mock_get_logger,
        patch("stream.main.sys.exit") as mock_sys_exit,
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_args = MagicMock()
        mock_args.host = "127.0.0.1"
        mock_args.port = 3120
        mock_args.domains = ["*.google.com"]
        mock_args.proxy = None
        mock_parse.return_value = mock_args

        # Mock ProxyServer.start() to raise generic exception
        test_error = RuntimeError("Proxy server startup failed")
        mock_proxy = AsyncMock()
        mock_proxy.start = AsyncMock(side_effect=test_error)
        mock_proxy_class.return_value = mock_proxy

        from stream.main import main

        # Run main() - generic exception should be caught
        await main()

        # Verify error was logged (line 84)
        mock_logger.error.assert_called_once_with(
            f"Error starting proxy server: {test_error}"
        )

        # Verify sys.exit(1) was called (line 85)
        mock_sys_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_builtin_with_default_port():
    """
    测试场景: builtin() 函数在 port=None 时使用默认端口
    预期: 覆盖 line 110 (if port is None: port = 3120)
    """
    with (
        patch("stream.main.ProxyServer") as mock_proxy_class,
        patch("stream.main.logging.getLogger") as mock_get_logger,
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Mock ProxyServer to immediately raise KeyboardInterrupt
        mock_proxy = AsyncMock()
        mock_proxy.start = AsyncMock(side_effect=KeyboardInterrupt)
        mock_proxy_class.return_value = mock_proxy

        from stream.main import builtin

        # Call builtin with port=None (line 110 should execute)
        await builtin(queue=None, port=None, proxy=None)

        # Verify ProxyServer was created with default port 3120
        mock_proxy_class.assert_called_once()
        call_kwargs = mock_proxy_class.call_args[1]
        assert call_kwargs["port"] == 3120  # Default port was used


@pytest.mark.asyncio
async def test_builtin_keyboard_interrupt_handling():
    """
    测试场景: builtin() 函数处理 KeyboardInterrupt 异常
    预期: 覆盖 lines 123-124 (except KeyboardInterrupt: logger.info(...))
    """
    with (
        patch("stream.main.ProxyServer") as mock_proxy_class,
        patch("stream.main.logging.getLogger") as mock_get_logger,
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Mock ProxyServer.start() to raise KeyboardInterrupt
        mock_proxy = AsyncMock()
        mock_proxy.start = AsyncMock(side_effect=KeyboardInterrupt)
        mock_proxy_class.return_value = mock_proxy

        from stream.main import builtin

        # Run builtin() - KeyboardInterrupt should be caught
        await builtin(queue=None, port=3120, proxy=None)

        # Verify shutdown message was logged (line 124)
        mock_logger.info.assert_any_call("Shutting down proxy server")


@pytest.mark.asyncio
async def test_builtin_cancelled_error_re_raising():
    """
    测试场景: builtin() 函数重新抛出 CancelledError
    预期: 覆盖 lines 125-126 (except asyncio.CancelledError: raise)
    """
    with patch("stream.main.ProxyServer") as mock_proxy_class:
        # Mock ProxyServer.start() to raise CancelledError
        mock_proxy = AsyncMock()
        mock_proxy.start = AsyncMock(side_effect=asyncio.CancelledError)
        mock_proxy_class.return_value = mock_proxy

        from stream.main import builtin

        # Run builtin() - CancelledError should be re-raised
        with pytest.raises(asyncio.CancelledError):
            await builtin(queue=None, port=3120, proxy=None)


@pytest.mark.asyncio
async def test_builtin_generic_exception_handling():
    """
    测试场景: builtin() 函数处理通用异常并退出
    预期: 覆盖 lines 127-129 (except Exception: logger.error(...); sys.exit(1))
    """
    with (
        patch("stream.main.ProxyServer") as mock_proxy_class,
        patch("stream.main.logging.getLogger") as mock_get_logger,
        patch("stream.main.sys.exit") as mock_sys_exit,
    ):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Mock ProxyServer.start() to raise generic exception
        test_error = RuntimeError("Critical proxy failure")
        mock_proxy = AsyncMock()
        mock_proxy.start = AsyncMock(side_effect=test_error)
        mock_proxy_class.return_value = mock_proxy

        from stream.main import builtin

        # Run builtin() - generic exception should be caught
        await builtin(queue=None, port=3120, proxy=None)

        # Verify error was logged (line 128)
        mock_logger.error.assert_called_once_with(
            f"Error starting proxy server: {test_error}"
        )

        # Verify sys.exit(1) was called (line 129)
        mock_sys_exit.assert_called_once_with(1)
