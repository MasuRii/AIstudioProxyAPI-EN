# --- browser_utils/initialization/scripts.py ---
import asyncio
import logging
import os

from playwright.async_api import BrowserContext as AsyncBrowserContext

logger = logging.getLogger("AIStudioProxyServer")


async def add_init_scripts_to_context(context: AsyncBrowserContext):
    """Add initialization scripts to browser context (fallback option)"""
    try:
        from config.settings import USERSCRIPT_PATH

        # Check if script file exists
        if not os.path.exists(USERSCRIPT_PATH):
            logger.info(
                f"Script file does not exist, skipping script injection: {USERSCRIPT_PATH}"
            )
            return

        # Read script content
        with open(USERSCRIPT_PATH, "r", encoding="utf-8") as f:
            script_content = f.read()

        # Clean UserScript headers
        cleaned_script = _clean_userscript_headers(script_content)

        # Add to context initialization scripts
        await context.add_init_script(cleaned_script)
        logger.info(
            f"Added script to browser context initialization scripts: {os.path.basename(USERSCRIPT_PATH)}"
        )

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error adding initialization script to context: {e}")


def _clean_userscript_headers(script_content: str) -> str:
    """Clean UserScript header information"""
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
