# --- browser_utils/initialization/scripts.py ---
import asyncio
import logging
import os

from playwright.async_api import BrowserContext as AsyncBrowserContext

logger = logging.getLogger("AIStudioProxyServer")


async def add_init_scripts_to_context(context: AsyncBrowserContext):
    """在浏览器上下文中添加初始化脚本（备用方案）"""
    try:
        from config.settings import USERSCRIPT_PATH

        # 检查脚本文件是否存在
        if not os.path.exists(USERSCRIPT_PATH):
            logger.info(f"脚本文件不存在，跳过脚本注入: {USERSCRIPT_PATH}")
            return

        # 读取脚本内容
        with open(USERSCRIPT_PATH, "r", encoding="utf-8") as f:
            script_content = f.read()

        # 清理UserScript头部
        cleaned_script = _clean_userscript_headers(script_content)

        # 添加到上下文的初始化脚本
        await context.add_init_script(cleaned_script)
        logger.info(
            f"已将脚本添加到浏览器上下文初始化脚本: {os.path.basename(USERSCRIPT_PATH)}"
        )

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"添加初始化脚本到上下文时发生错误: {e}")


def _clean_userscript_headers(script_content: str) -> str:
    """清理UserScript头部信息"""
    lines = script_content.split("\n")
    cleaned_lines = []
    in_userscript_block = False

    for line in lines:
        if line.strip().startswith("// ==UserScript=="):
            in_userscript_block = True
            continue
        elif line.strip().startswith("// ==/UserScript=="):
            in_userscript_block = False
            continue
        elif in_userscript_block:
            continue
        else:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)
