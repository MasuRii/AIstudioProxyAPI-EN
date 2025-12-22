# --- browser_utils/initialization/network.py ---
import asyncio
import json
import logging

from playwright.async_api import BrowserContext as AsyncBrowserContext

from .scripts import add_init_scripts_to_context

logger = logging.getLogger("AIStudioProxyServer")


async def setup_network_interception_and_scripts(context: AsyncBrowserContext):
    """Setup network interception and script injection"""
    try:
        from config.settings import ENABLE_SCRIPT_INJECTION

        if not ENABLE_SCRIPT_INJECTION:
            logger.debug("[Network] Script injection disabled")
            return

        # Setup network interception
        await _setup_model_list_interception(context)

        # Optional: still inject scripts as fallback
        await add_init_scripts_to_context(context)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error setting up network interception and scripts: {e}")


async def _setup_model_list_interception(context: AsyncBrowserContext):
    """Setup model list network interception"""
    try:

        async def handle_model_list_route(route):
            """Handle model list request route"""
            request = route.request

            # Check if it's a model list request
            if "alkalimakersuite" in request.url and "ListModels" in request.url:
                logger.info(f"Intercepted model list request: {request.url}")

                # Continue original request
                response = await route.fetch()

                # Get original response body
                original_body = await response.body()

                # Process response
                modified_body = await _modify_model_list_response(
                    original_body, request.url
                )

                # Return modified response
                await route.fulfill(response=response, body=modified_body)
            else:
                # For other requests, continue normally
                await route.continue_()

        # Register route interceptor
        await context.route("**/*", handle_model_list_route)
        logger.info("Model list network interception setup")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error setting up model list network interception: {e}")


async def _modify_model_list_response(original_body: bytes, url: str) -> bytes:
    """Modify model list response (Cleanup/Pass-through)"""
    try:
        # Decode response body
        original_text = original_body.decode("utf-8")

        # Handle anti-hijack prefix
        ANTI_HIJACK_PREFIX = ")]}'\n"
        has_prefix = False
        if original_text.startswith(ANTI_HIJACK_PREFIX):
            original_text = original_text[len(ANTI_HIJACK_PREFIX) :]
            has_prefix = True

        # Parse JSON to ensure it's valid, but we don't inject models anymore
        try:
            json_data = json.loads(original_text)
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse model list response JSON: {json_err}")
            return original_body

        # Serialize back to JSON
        modified_text = json.dumps(json_data, separators=(",", ":"))

        # Add prefix back
        if has_prefix:
            modified_text = ANTI_HIJACK_PREFIX + modified_text

        return modified_text.encode("utf-8")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error processing model list response: {e}")
        return original_body
