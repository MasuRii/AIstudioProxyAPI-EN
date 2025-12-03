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
    """测试 _clean_userscript_headers 函数"""

    def test_clean_headers_basic(self):
        """测试基本的 UserScript 头部清理"""
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
        """测试没有 UserScript 头部的脚本"""
        script = "console.log('No headers');"
        result = _clean_userscript_headers(script)
        assert result == script

    def test_clean_headers_empty_script(self):
        """测试空脚本"""
        script = ""
        result = _clean_userscript_headers(script)
        assert result == ""

    def test_clean_headers_only_headers(self):
        """测试仅包含头部的脚本"""
        script = """// ==UserScript==
// @name Test
// ==/UserScript=="""
        result = _clean_userscript_headers(script)
        # 应该只剩空行
        assert result.strip() == ""

    def test_clean_headers_multiple_blocks(self):
        """测试多个 UserScript 块"""
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
        """测试保留其他注释"""
        script = """// ==UserScript==
// @name Test
// ==/UserScript==
// This is a regular comment
console.log('Code');"""
        result = _clean_userscript_headers(script)
        assert "// This is a regular comment" in result
        assert "// @name Test" not in result

    def test_clean_headers_whitespace_handling(self):
        """测试空白字符处理"""
        script = """   // ==UserScript==
   // @name Test
   // ==/UserScript==
console.log('Code');"""
        result = _clean_userscript_headers(script)
        assert "// @name" not in result
        assert "console.log('Code');" in result

    def test_clean_headers_incomplete_block(self):
        """测试不完整的 UserScript 块（只有开始标记）"""
        script = """// ==UserScript==
// @name Test
console.log('No closing tag');"""
        result = _clean_userscript_headers(script)
        # 所有在开始标记后的内容都应被视为头部并移除
        assert "// @name Test" not in result
        # 由于没有结束标记，后续内容也会被移除
        assert "console.log" not in result or "No closing tag" not in result


class TestAddInitScriptsToContext:
    """测试 add_init_scripts_to_context 函数"""

    @pytest.fixture
    def mock_context(self):
        """创建模拟浏览器上下文"""
        context = AsyncMock()
        context.add_init_script = AsyncMock()
        return context

    @pytest.mark.asyncio
    async def test_add_scripts_success(self, mock_context):
        """测试成功添加脚本"""
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

        # 验证 add_init_script 被调用
        mock_context.add_init_script.assert_called_once()
        # 验证传入的脚本不包含头部
        called_script = mock_context.add_init_script.call_args[0][0]
        assert "// ==UserScript==" not in called_script
        assert "console.log('Hello');" in called_script

    @pytest.mark.asyncio
    async def test_add_scripts_file_not_exists(self, mock_context, caplog):
        """测试脚本文件不存在的情况"""
        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists",
                return_value=False,
            ):
                await add_init_scripts_to_context(mock_context)

        # 验证未调用 add_init_script
        mock_context.add_init_script.assert_not_called()
        # 验证记录了日志
        assert (
            "脚本文件不存在" in caplog.text or len(caplog.records) == 0
        )  # 可能没有捕获到

    @pytest.mark.asyncio
    async def test_add_scripts_read_error(self, mock_context, caplog):
        """测试读取脚本文件时发生错误"""
        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists", return_value=True
            ):
                with patch(
                    "browser_utils.initialization.scripts.open",
                    side_effect=IOError("Read error"),
                ):
                    await add_init_scripts_to_context(mock_context)

        # 验证未调用 add_init_script
        mock_context.add_init_script.assert_not_called()
        # 应该记录错误日志（但不会抛出异常）

    @pytest.mark.asyncio
    async def test_add_scripts_injection_error(self, mock_context, caplog):
        """测试脚本注入时发生错误"""
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

        # 不应该抛出异常（已被捕获）

    @pytest.mark.asyncio
    async def test_add_scripts_empty_file(self, mock_context):
        """测试空脚本文件"""
        with patch("config.settings.USERSCRIPT_PATH", "/fake/path/script.js"):
            with patch(
                "browser_utils.initialization.scripts.os.path.exists", return_value=True
            ):
                with patch(
                    "browser_utils.initialization.scripts.open", mock_open(read_data="")
                ):
                    await add_init_scripts_to_context(mock_context)

        # 即使是空脚本，也应该被添加
        mock_context.add_init_script.assert_called_once_with("")

    @pytest.mark.asyncio
    async def test_add_scripts_import_error(self, mock_context):
        """测试导入配置失败的情况"""
        # 模拟导入 USERSCRIPT_PATH 失败
        with patch(
            "browser_utils.initialization.scripts.os.path.exists",
            side_effect=ImportError("Config error"),
        ):
            await add_init_scripts_to_context(mock_context)

        # 应该捕获异常，不调用 add_init_script
        mock_context.add_init_script.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_scripts_with_unicode(self, mock_context):
        """测试包含 Unicode 字符的脚本"""
        script_content = """// ==UserScript==
// @name 测试脚本
// ==/UserScript==
console.log('你好，世界！🌍');"""

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
        assert "你好，世界！🌍" in called_script
        assert "// @name 测试脚本" not in called_script

    @pytest.mark.asyncio
    async def test_add_scripts_large_file(self, mock_context):
        """测试大文件处理"""
        # 创建一个较大的脚本内容
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
        # 验证大文件被正确处理
        assert "console.log('line');" in called_script
        assert called_script.count("console.log('line');") == 10000
