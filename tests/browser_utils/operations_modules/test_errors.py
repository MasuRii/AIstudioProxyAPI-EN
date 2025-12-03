# -*- coding: utf-8 -*-
"""Tests for browser_utils/operations_modules/errors.py"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_utils.operations_modules.errors import (
    detect_and_extract_page_error,
    save_error_snapshot,
)


@pytest.mark.asyncio
async def test_detect_and_extract_page_error_empty_message():
    """Test when error toast exists but message locator returns empty string."""
    page = MagicMock()
    error_locator = MagicMock()
    message_locator = MagicMock()

    # Set up proper chain: page.locator().last
    page.locator.return_value.last = error_locator
    error_locator.locator.return_value = message_locator

    error_locator.wait_for = AsyncMock()
    message_locator.text_content = AsyncMock(return_value="")  # Empty string

    result = await detect_and_extract_page_error(page, "test_req")

    # Should return default message (line 22)
    assert result == "检测到错误提示框，但无法提取特定消息。"


@pytest.mark.asyncio
async def test_detect_and_extract_page_error_general_exception():
    """Test handling of general exceptions during error detection."""
    page = MagicMock()
    error_locator = MagicMock()

    page.locator.return_value.last = error_locator

    # Cause a general exception (not PlaywrightAsyncError)
    error_locator.wait_for = AsyncMock()
    error_locator.locator.side_effect = ValueError("Unexpected error")

    result = await detect_and_extract_page_error(page, "test_req")

    # Should handle exception and return None (line 27)
    assert result is None


@pytest.mark.asyncio
async def test_save_error_snapshot_with_all_params():
    """Test save_error_snapshot calls debug_utils correctly."""
    with patch(
        "browser_utils.debug_utils.save_error_snapshot_enhanced", new_callable=AsyncMock
    ) as mock_save:
        await save_error_snapshot(
            error_name="test_error",
            error_exception=ValueError("Test"),
            error_stage="testing",
            additional_context={"key": "value"},
            locators={"button": "selector"},
        )

        # Should call enhanced snapshot with all params (lines 50-57)
        mock_save.assert_called_once()
        call_args = mock_save.call_args
        assert call_args[0][0] == "test_error"
        assert call_args[1]["error_stage"] == "testing"
        assert call_args[1]["additional_context"] == {"key": "value"}
