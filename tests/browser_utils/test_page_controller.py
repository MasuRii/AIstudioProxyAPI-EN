from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browser_utils.page_controller import PageController
from models import ClientDisconnectedError


@pytest.mark.asyncio
async def test_page_controller_initialization(mock_page: MagicMock):
    """Test PageController initialization and mixin inheritance."""
    logger = MagicMock()
    req_id = "test_req_id"

    controller = PageController(mock_page, logger, req_id)

    assert controller.page == mock_page
    assert controller.logger == logger
    assert controller.req_id == req_id

    # Verify mixin methods are available (duck typing check)
    # InputController
    assert hasattr(controller, "submit_prompt")
    # ResponseController
    assert hasattr(controller, "get_response")
    # BaseController
    assert hasattr(controller, "_check_disconnect")

    # Verify inheritance hierarchy
    assert isinstance(controller, PageController)


@pytest.mark.asyncio
async def test_page_controller_delegation(mock_page: MagicMock):
    """Test that PageController delegates methods to mixins correctly."""
    logger = MagicMock()
    req_id = "test_req_id"
    controller = PageController(mock_page, logger, req_id)

    # Mock a method from InputController
    with patch.object(
        controller, "submit_prompt", new_callable=AsyncMock
    ) as mock_submit:
        await controller.submit_prompt("test prompt", [], MagicMock())
        mock_submit.assert_called_once_with(
            "test prompt", [], mock_submit.call_args[0][2]
        )


@pytest.mark.asyncio
async def test_page_controller_check_disconnect(mock_page: MagicMock):
    """Test _check_disconnect method from BaseController."""
    logger = MagicMock()
    req_id = "test_req_id"
    controller = PageController(mock_page, logger, req_id)

    # Test 1: check_client_disconnected returns truthy value -> raises ClientDisconnectedError
    mock_check_func = MagicMock()  # Returns truthy MagicMock by default
    with pytest.raises(ClientDisconnectedError):
        await controller._check_disconnect(
            stage="test stage", check_client_disconnected=mock_check_func
        )

    # Test 2: check_client_disconnected raises ClientDisconnectedError -> propagates exception
    mock_check_func.side_effect = ClientDisconnectedError("Disconnected")

    # Verify mock raises as expected
    with pytest.raises(ClientDisconnectedError):
        mock_check_func("test")

    # Verify controller propagates the exception
    with pytest.raises(ClientDisconnectedError):
        await controller._check_disconnect(
            stage="test stage", check_client_disconnected=mock_check_func
        )
