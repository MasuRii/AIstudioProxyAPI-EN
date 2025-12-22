import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add repository root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from browser_utils import auth_rotation
from config.global_state import GlobalState


class TestAuthRotationCooldownFix(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Reset GlobalState
        GlobalState.reset_quota_status()
        GlobalState.current_profile_exhausted_models = set()
        GlobalState.last_error_type = None
        GlobalState.AUTH_ROTATION_LOCK.set() # Ensure lock is open initially

        # Mock server module
        self.mock_server = MagicMock()
        self.mock_server.current_auth_profile_path = "auth_profiles/saved/old_profile.json"
        self.mock_server.current_ai_studio_model_id = "gemini-1.5-pro"
        self.mock_server.page_instance = MagicMock()
        self.mock_server.page_instance.is_closed.return_value = False
        self.mock_server.page_instance.context = MagicMock()
        self.mock_server.page_instance.context.clear_cookies = MagicMock()
        self.mock_server.page_instance.context.add_cookies = MagicMock()

        # Apply server mock
        self.server_patcher = patch('browser_utils.auth_rotation.server', self.mock_server)
        self.server_patcher.start()

        # Mock file operations to avoid actual IO
        self.open_patcher = patch('builtins.open', new_callable=MagicMock)
        self.mock_open = self.open_patcher.start()
        self.json_load_patcher = patch('json.load', return_value={"cookies": []})
        self.json_load_patcher.start()

        # Mock os.path.exists to always return True
        self.exists_patcher = patch('os.path.exists', return_value=True)
        self.exists_patcher.start()

    async def asyncTearDown(self):
        self.server_patcher.stop()
        self.open_patcher.stop()
        self.json_load_patcher.stop()
        self.exists_patcher.stop()

    @patch('browser_utils.auth_rotation.save_cooldown_profiles')
    @patch('browser_utils.auth_rotation._get_next_profile', return_value="auth_profiles/saved/new_profile.json")
    @patch('browser_utils.auth_rotation._perform_canary_test', return_value=True)
    async def test_model_specific_cooldown_application(self, mock_canary, mock_get_next, mock_save):
        """Test that quota exhaustion results in model-specific cooldowns, not just 'default'."""

        # Setup scenario: Quota Exceeded for a specific model
        GlobalState.last_error_type = 'QUOTA_EXCEEDED'
        GlobalState.current_profile_exhausted_models.add("gemini-1.5-pro")

        # Mock the cooldown profiles dict in the module
        # We need to make sure it's a real dict so updates persist during the function call
        test_cooldown_profiles = {}
        with patch('browser_utils.auth_rotation._COOLDOWN_PROFILES', test_cooldown_profiles):
            # Perform rotation
            await auth_rotation.perform_auth_rotation(target_model_id="gemini-1.5-pro")

            # Verify save was called
            mock_save.assert_called()

            # Verify the correct structure was saved
            # Expected: {'auth_profiles/saved/old_profile.json': {'gemini-1.5-pro': timestamp}}

            saved_data = mock_save.call_args[0][0]
            old_profile = "auth_profiles/saved/old_profile.json"

            self.assertIn(old_profile, saved_data)
            self.assertIsInstance(saved_data[old_profile], dict)
            self.assertIn("gemini-1.5-pro", saved_data[old_profile])

            # Ensure 'default' or 'global' is NOT present if only specific model failed
            self.assertNotIn("default", saved_data[old_profile])
            self.assertNotIn("global", saved_data[old_profile])

    @patch('browser_utils.auth_rotation.save_cooldown_profiles')
    @patch('browser_utils.auth_rotation._get_next_profile', return_value="auth_profiles/saved/new_profile.json")
    @patch('browser_utils.auth_rotation._perform_canary_test', return_value=True)
    async def test_fallback_to_current_model_id(self, mock_canary, mock_get_next, mock_save):
        """Test fallback to server.current_ai_studio_model_id if exhausted set is empty."""

        # Setup scenario: Quota Exceeded, but set is empty (e.g. detected via UI text, not token count)
        GlobalState.last_error_type = 'QUOTA_EXCEEDED'
        GlobalState.current_profile_exhausted_models = set()

        # Ensure server has a current model ID
        self.mock_server.current_ai_studio_model_id = "gemini-ultra"

        test_cooldown_profiles = {}
        with patch('browser_utils.auth_rotation._COOLDOWN_PROFILES', test_cooldown_profiles):
            await auth_rotation.perform_auth_rotation()

            saved_data = mock_save.call_args[0][0]
            old_profile = "auth_profiles/saved/old_profile.json"

            self.assertIn(old_profile, saved_data)
            self.assertIsInstance(saved_data[old_profile], dict)
            # Should have used the fallback model ID
            self.assertIn("gemini-ultra", saved_data[old_profile])

if __name__ == '__main__':
    unittest.main()
