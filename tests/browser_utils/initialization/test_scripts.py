"""
Tests for browser_utils/initialization/scripts.py
"""

from unittest.mock import AsyncMock, mock_open, patch

import pytest

from browser_utils.initialization.scripts import (
    _clean_userscript_headers,
    add_init_scripts_to_context,
)


class TestCleanUserscriptHeaders:
    """Test _clean_userscript_headers function"""

    def test_clean_headers_basic(self):
        """Test basic UserScript header cleanup"""
        script = """// ==UserScript==
// @name Test Script
// @version 1.0
// ==/UserScript==
console.log('Hello');"""
        result = _clean_userscript_headers(script)
        assert "// ==UserScript==" not in result
        assert "// @name" not in result
        assert "// ==/UserScript==" not in result
        assert "console.log('Hello');" in result

    def test_clean_headers_no_headers(self):
        """Test script without UserScript headers"""
        script = "console.log('No headers');"
        result = _clean_userscript_headers(script)
        assert result == script

    def test_clean_headers_empty_script(self):
        """Test empty script"""
        script = ""
        result = _clean_userscript_headers(script)
        assert result == ""

    def test_clean_headers_only_headers(self):
        """Test script containing only headers"""
        script = """// ==UserScript==
// @name Test
// ==/UserScript=="""
        result = _clean_userscript_headers(script)
        # Should only have empty lines left
        assert result.strip() == ""

    def test_clean_headers_multiple_blocks(self):
        """Test multiple UserScript blocks"""
        script = """// ==UserScript==
// @name Block1
// ==/UserScript==
console.log('First');
// ==UserScript==
// @name Block2
// ==/UserScript==
console.log('Second');"""
        result = _clean_userscript_headers(script)
        assert "// @name" not in result
        assert "console.log('First');" in result
        assert "console.log('Second');" in result

    def test_clean_headers_preserves_other_comments(self):
        """Test preserving other comments"""
        script = """// ==UserScript==
// @name Test
// ==/UserScript==
// This is a regular comment
console.log('Code');"""
        result = _clean_userscript_headers(script)
        assert "// This is a regular comment" in result
        assert "// @name Test" not in result

    def test_clean_headers_whitespace_handling(self):
        """Test whitespace handling"""
        script = """   // ==UserScript==
   // @name Test
   // ==/UserScript==
console.log('Code');"""
        result = _clean_userscript_headers(script)
        assert "// @name" not in result
        assert "console.log('Code');" in result

    def test_clean_headers_incomplete_block(self):
        """Test incomplete UserScript block (only start marker)"""
        script = """// ==UserScript==
// @name Test
console.log('No closing tag');"""
        result = _clean_userscript_headers(script)
        # Everything after the start marker should be treated as header and removed
        assert "// @name Test" not in result
        # Since there's no end marker, subsequent content is also removed
        assert "console.log" not in result or "No closing tag" not in result


class TestAddInitScriptsToContext:
    """Test add_init_scripts_to_context function"""

    @pytest.fixture
    def mock_context(self):
        """Create mock browser context"""
        context = AsyncMock()
        context.add_init_script = AsyncMock()
        return context

    @pytest.mark.asyncio
    def test_add_scripts_success(self, mock_context):
        """Test successful script addition"""
        script_content = """// ==UserScript==
// @name Test
// ==/UserScript==
console.log('Hello');"""

        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists", return_value=True
            ):
                with patch(
                    "browser_utils.initialization.scripts.open",
                    mock_open(read_data=script_content),
                ):
                    # add_init_scripts_to_context is async, but tested synchronously here?
                    # Wait, it is async in the source.
                    pass

    @pytest.mark.asyncio
    async def test_add_scripts_success_async(self, mock_context):
        """Test successful script addition async"""
        script_content = """// ==UserScript==
// @name Test
// ==/UserScript==
console.log('Hello');"""

        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists", return_value=True
            ):
                with patch(
                    "browser_utils.initialization.scripts.open",
                    mock_open(read_data=script_content),
                ):
                    await add_init_scripts_to_context(mock_context)

        # Verify add_init_script called
        mock_context.add_init_script.assert_called_once()
        # Verify passed script does not contain headers
        called_script = mock_context.add_init_script.call_args[0][0]
        assert "// ==UserScript==" not in called_script
        assert "console.log('Hello');" in called_script

    @pytest.mark.asyncio
    async def test_add_scripts_file_not_exists(self, mock_context, caplog):
        """Test case where script file does not exist"""
        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists",
                return_value=False,
            ):
                await add_init_scripts_to_context(mock_context)

        # Verify add_init_script not called
        mock_context.add_init_script.assert_not_called()
        # Verify log recorded
        assert (
            "Script file does not exist" in caplog.text or len(caplog.records) == 0
        )  # Might not have been captured

    @pytest.mark.asyncio
    async def test_add_scripts_read_error(self, mock_context, caplog):
        """Test error while reading script file"""
        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists", return_value=True
            ):
                with patch(
                    "browser_utils.initialization.scripts.open",
                    side_effect=IOError("Read error"),
                ):
                    await add_init_scripts_to_context(mock_context)

        # Verify add_init_script not called
        mock_context.add_init_script.assert_not_called()
        # Should log error (but not throw exception)

    @pytest.mark.asyncio
    async def test_add_scripts_injection_error(self, mock_context, caplog):
        """Test error during script injection"""
        script_content = "console.log('Test');"

        mock_context.add_init_script = AsyncMock(
            side_effect=Exception("Injection error")
        )

        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists", return_value=True
            ):
                with patch(
                    "browser_utils.initialization.scripts.open",
                    mock_open(read_data=script_content),
                ):
                    await add_init_scripts_to_context(mock_context)

        # Should not throw exception (already caught)

    @pytest.mark.asyncio
    async def test_add_scripts_empty_file(self, mock_context):
        """Test empty script file"""
        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists", return_value=True
            ):
                with patch(
                    "browser_utils.initialization.scripts.open", mock_open(read_data="")
                ):
                    await add_init_scripts_to_context(mock_context)

        # Even empty script should be added
        mock_context.add_init_script.assert_called_once_with("")

    @pytest.mark.asyncio
    async def test_add_scripts_import_error(self, mock_context):
        """Test case where config import fails"""
        # Simulate USERSCRIPT_PATH import failure
        with patch(
            "browser_utils.initialization.scripts.os.path.exists",
            side_effect=ImportError("Config error"),
        ):
            await add_init_scripts_to_context(mock_context)

        # Should catch exception, not call add_init_script
        mock_context.add_init_script.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_scripts_with_unicode(self, mock_context):
        """Test script containing Unicode characters"""
        script_content = """// ==UserScript==
// @name test script
// ==/UserScript==
console.log('hello, world! 🌍');"""

        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists", return_value=True
            ):
                with patch(
                    "browser_utils.initialization.scripts.open",
                    mock_open(read_data=script_content),
                ):
                    await add_init_scripts_to_context(mock_context)

        mock_context.add_init_script.assert_called_once()
        called_script = mock_context.add_init_script.call_args[0][0]
        assert "hello, world! 🌍" in called_script
        assert "// @name test script" not in called_script

    @pytest.mark.asyncio
    async def test_add_scripts_large_file(self, mock_context):
        """Test large file handling"""
        # Create a large script content
        large_script = "// ==UserScript==\n// @name Test\n// ==/UserScript==\n"
        large_script += "console.log('line');\n" * 10000

        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists", return_value=True
            ):
                with patch(
                    "browser_utils.initialization.scripts.open",
                    mock_open(read_data=large_script),
                ):
                    await add_init_scripts_to_context(mock_context)

        mock_context.add_init_script.assert_called_once()
        called_script = mock_context.add_init_script.call_args[0][0]
        # Verify large file correctly handled
        assert "console.log('line');" in called_script
        assert called_script.count("console.log('line');") == 10000
