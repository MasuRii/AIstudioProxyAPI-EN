import asyncio
from typing import AsyncGenerator


async def use_helper_get_response(
    helper_endpoint: str, helper_sapisid: str
) -> AsyncGenerator[str, None]:
    import aiohttp

    from api_utils.server_state import state

    logger = state.logger

    logger.info(f"Attempting to use Helper endpoint: {helper_endpoint}")

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
                    logger.error(
                        f"Helper endpoint returned error status: {response.status}"
                    )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error using Helper endpoint: {e}")
