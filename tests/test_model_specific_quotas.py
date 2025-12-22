# tests/test_model_specific_quotas.py

import unittest
from unittest.mock import patch

from config import global_state
from config.global_state import GlobalState


class TestModelSpecificQuotas(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test."""
        GlobalState.reset_quota_status()
        global_state.MODEL_QUOTA_LIMITS.clear()

    def tearDown(self):
        """Clean up test environment after each test."""
        GlobalState.reset_quota_status()
        global_state.MODEL_QUOTA_LIMITS.clear()

    def test_model_specific_quota_overrides_global(self):
        """Verify model-specific quota overrides the global limit."""
        from models.exceptions import QuotaExceededError

        with patch("config.global_state.QUOTA_HARD_LIMIT", 550000):
            global_state.MODEL_QUOTA_LIMITS["gemini-pro"] = 1000

            GlobalState.increment_token_count(999, "gemini-pro")
            self.assertNotIn("gemini-pro", GlobalState.current_profile_exhausted_models)

            with self.assertRaises(QuotaExceededError):
                GlobalState.increment_token_count(1, "gemini-pro")
            self.assertIn("gemini-pro", GlobalState.current_profile_exhausted_models)

    def test_global_quota_fallback(self):
        """Verify global QUOTA_HARD_LIMIT is used as a fallback."""
        from models.exceptions import QuotaExceededError

        with patch("config.global_state.QUOTA_HARD_LIMIT", 500):
            GlobalState.increment_token_count(499, "unknown-model")
            self.assertNotIn(
                "unknown-model", GlobalState.current_profile_exhausted_models
            )

            with self.assertRaises(QuotaExceededError):
                GlobalState.increment_token_count(1, "unknown-model")
            self.assertIn("unknown-model", GlobalState.current_profile_exhausted_models)

    def test_quota_exceeded_for_one_model_only(self):
        """Verify that exceeding the quota for one model does not affect others."""
        from models.exceptions import QuotaExceededError

        with patch("config.global_state.QUOTA_HARD_LIMIT", 550000):
            global_state.MODEL_QUOTA_LIMITS["gemini-pro"] = 100
            global_state.MODEL_QUOTA_LIMITS["gemini-flash"] = 200

            with self.assertRaises(QuotaExceededError):
                GlobalState.increment_token_count(100, "gemini-pro")
            self.assertIn("gemini-pro", GlobalState.current_profile_exhausted_models)
            self.assertTrue(GlobalState.IS_QUOTA_EXCEEDED)

            self.assertNotIn(
                "gemini_flash", GlobalState.current_profile_exhausted_models
            )

            GlobalState.increment_token_count(150, "gemini-flash")
            self.assertNotIn(
                "gemini-flash", GlobalState.current_profile_exhausted_models
            )

    def test_successful_api_call_unaffected(self):
        """Regression: Ensure a standard successful API call is unaffected."""
        global_state.MODEL_QUOTA_LIMITS["gemini-pro"] = 1000
        GlobalState.increment_token_count(50, "gemini-pro")
        self.assertFalse(GlobalState.IS_QUOTA_EXCEEDED)
        self.assertNotIn("gemini-pro", GlobalState.current_profile_exhausted_models)


if __name__ == "__main__":
    unittest.main()
