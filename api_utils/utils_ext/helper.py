import asyncio
from typing import AsyncGenerator


async def use_helper_get_response(
    helper_endpoint: str, helper_sapisid: str
) -> AsyncGenerator[str, None]:
    import aiohttp

    from server import logger

    logger.info(f"正在尝试使用Helper端点: {helper_endpoint}")

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"SAPISID={helper_sapisid}" if helper_sapisid else "",
            }
            async with session.get(helper_endpoint, headers=headers) as response:
                if response.status == 200:
                    async for chunk in response.content.iter_chunked(1024):
                        if chunk:
                            yield chunk.decode("utf-8", errors="ignore")
                else:
                    logger.error(f"Helper端点返回错误状态: {response.status}")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"使用Helper端点时出错: {e}")
