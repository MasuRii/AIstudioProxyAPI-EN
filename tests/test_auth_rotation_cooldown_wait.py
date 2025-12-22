import os
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to the Python path to resolve module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

from browser_utils.auth_rotation import perform_auth_rotation
from config.global_state import GlobalState

# Mark the entire module as async
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def setup_teardown():
    """Set up and tear down global state for each test."""
    GlobalState.AUTH_ROTATION_LOCK.set()
    GlobalState.DEPLOYMENT_EMERGENCY_MODE = False
    GlobalState.reset_quota_status()
    
    yield
    
    GlobalState.reset_quota_status()
    GlobalState.AUTH_ROTATION_LOCK.set()


async def test_perform_auth_rotation_waits_for_cooldown():
    """
    Test that perform_auth_rotation waits for the correct duration when all profiles are on cooldown.
    """
    cooldown_duration = 2
    start_time = time.time()

    # Set up cooldown profiles
    mock_cooldown_profiles = {
        "/path/to/profile1.json": {"global": (datetime.now() + timedelta(seconds=10)).timestamp()},
        "/path/to/profile2.json": {"global": (datetime.now() + timedelta(seconds=cooldown_duration)).timestamp()}
    }
    
    # Track calls to _get_next_profile
    call_count = 0
    
    def mock_get_next_profile(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: no profiles available
            return None
        else:
            # Subsequent calls: profile becomes available after cooldown
            return "/path/to/profile2.json"
    
    # Set up mocks
    mock_canary = AsyncMock(return_value=True)
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_context = MagicMock()
    mock_context.clear_cookies = AsyncMock()
    mock_context.add_cookies = AsyncMock()
    mock_page.context = mock_context
    
    # Mock other dependencies
    with patch('browser_utils.auth_rotation._get_next_profile', side_effect=mock_get_next_profile), \
         patch('browser_utils.auth_rotation._COOLDOWN_PROFILES', mock_cooldown_profiles), \
         patch('browser_utils.auth_rotation._perform_canary_test', mock_canary), \
         patch('browser_utils.auth_rotation.save_cooldown_profiles'), \
         patch('browser_utils.auth_rotation.GlobalState.last_error_type', 'QUOTA_EXCEEDED'), \
         patch('server.page_instance', mock_page), \
         patch('server.current_auth_profile_path', "/path/to/old_profile.json"), \
         patch('browser_utils.auth_rotation.QUOTA_EXCEEDED_COOLDOWN_SECONDS', 30), \
         patch('browser_utils.auth_rotation.RATE_LIMIT_COOLDOWN_SECONDS', 10), \
         patch('builtins.open') as mock_open, \
         patch('os.path.exists', return_value=True):
        
        # Configure file opening to return valid profile data
        mock_file = MagicMock()
        mock_file.read.return_value = '{"cookies": []}'
        mock_open.return_value.__enter__.return_value = mock_file
        
        # Run the function
        result = await perform_auth_rotation()
    
    # Verify the result
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Assertions
    assert result is True, "perform_auth_rotation should return True after waiting"
    assert execution_time >= cooldown_duration, \
        f"Expected wait time >= {cooldown_duration}s, got {execution_time:.2f}s"
    assert call_count >= 2, f"Expected at least 2 calls to _get_next_profile, got {call_count}"
    
    # Verify that the mock was called and waiting occurred
    assert mock_canary.called, "Canary test should have been called"