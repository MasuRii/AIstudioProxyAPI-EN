from typing import Callable

from playwright.async_api import Page as AsyncPage

from models import ClientDisconnectedError


class BaseController:
    """Base controller providing common functionality."""

    def __init__(self, page: AsyncPage, logger, req_id: str):
        self.page = page
        self.logger = logger
        self.req_id = req_id

    async def _check_disconnect(self, check_client_disconnected: Callable, stage: str):
        """Check if the client has disconnected."""
        if check_client_disconnected(stage):
            raise ClientDisconnectedError(
                f"[{self.req_id}] Client disconnected at stage: {stage}"
            )
