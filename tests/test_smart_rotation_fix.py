"""
Test for smart auth profile rotation fix
Tests that rotation properly considers model-specific cooldowns
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

# Import the functions we want to test
from browser_utils.auth_rotation import _find_best_profile_in_dirs, _normalize_model_id


class TestSmartRotationFix(unittest.TestCase):
    """Test smart rotation logic with model-specific cooldowns"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.saved_dir = os.path.join(self.test_dir, "saved")
        self.emergency_dir = os.path.join(self.test_dir, "emergency")
        os.makedirs(self.saved_dir, exist_ok=True)
        os.makedirs(self.emergency_dir, exist_ok=True)
        
        # Create test profile files
        self.profile1 = os.path.join(self.saved_dir, "profile1.json")
        self.profile2 = os.path.join(self.saved_dir, "profile2.json")
        self.profile3 = os.path.join(self.saved_dir, "profile3.json")
        self.emergency_profile = os.path.join(self.emergency_dir, "emergency.json")
        
        # Create dummy profile content
        profile_content = {"cookies": [{"name": "test", "value": "test"}]}
        
        for profile_path in [self.profile1, self.profile2, self.profile3, self.emergency_profile]:
            with open(profile_path, 'w') as f:
                json.dump(profile_content, f)

    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_normalize_model_id(self):
        """Test model ID normalization"""
        test_cases = [
            ("gemini 3 pro preview", "gemini-3-pro-preview"),
            ("gemini-2.5-pro", "gemini-2.5-pro"),
            ("gemini 2.5 pro", "gemini-2.5-pro"),  # Should preserve dots for known models
            ("default", "default"),
            ("", "default"),
            (None, "default"),
        ]
        
        for input_id, expected in test_cases:
            result = _normalize_model_id(input_id)
            self.assertEqual(result, expected, f"Failed for input: {input_id}")

    def test_find_best_profile_gemini_3_pro_preview(self):
        """Test that profiles with gemini-3-pro-preview cooldown are excluded"""
        # Mock cooldown data similar to user's config
        cooldown_data = {
            self.profile1: {
                "gemini-3-pro-preview": (datetime.now() + timedelta(hours=1)).timestamp(),
                "default": (datetime.now() + timedelta(hours=1)).timestamp()
            },
            self.profile2: {
                "default": (datetime.now() + timedelta(hours=1)).timestamp()
            },
            # profile3 has no cooldown - should be selected
            # emergency_profile has no cooldown - should be selected
        }
        
        with patch('browser_utils.auth_rotation._COOLDOWN_PROFILES', cooldown_data), \
             patch('browser_utils.auth_rotation.get_profile_usage', return_value=1):
            
            # Test with gemini-3-pro-preview - should exclude profile1 but include others
            best_profile = _find_best_profile_in_dirs(
                [self.saved_dir, self.emergency_dir], 
                target_model_id="gemini 3 pro preview"
            )
            
            # Should not be profile1 (has gemini-3-pro-preview cooldown)
            self.assertNotEqual(best_profile, self.profile1)
            # Should be either profile2, profile3, or emergency_profile
            self.assertIn(best_profile, [self.profile2, self.profile3, self.emergency_profile])

    def test_find_best_profile_no_model_specific_cooldown(self):
        """Test that profiles without specific model cooldown are included"""
        # Mock cooldown data - only default cooldown
        cooldown_data = {
            self.profile1: {
                "default": (datetime.now() + timedelta(hours=1)).timestamp()
            },
            # Other profiles have no cooldown
        }
        
        with patch('browser_utils.auth_rotation._COOLDOWN_PROFILES', cooldown_data), \
             patch('browser_utils.auth_rotation.get_profile_usage', return_value=1):
            
            # Test with gemini-3-pro-preview - should include all profiles since none have specific cooldown
            best_profile = _find_best_profile_in_dirs(
                [self.saved_dir, self.emergency_dir], 
                target_model_id="gemini 3 pro preview"
            )
            
            # Should be able to select any profile (including profile1)
            self.assertIsNotNone(best_profile)

    def test_find_best_profile_global_cooldown_excludes_all(self):
        """Test that global cooldown excludes all profiles"""
        # Mock cooldown data with global cooldown
        cooldown_data = {
            self.profile1: {
                "global": (datetime.now() + timedelta(hours=1)).timestamp()
            },
            self.profile2: {
                "global": (datetime.now() + timedelta(hours=1)).timestamp()
            },
            self.profile3: {
                "global": (datetime.now() + timedelta(hours=1)).timestamp()
            },
            self.emergency_profile: {
                "global": (datetime.now() + timedelta(hours=1)).timestamp()
            },
        }
        
        with patch('browser_utils.auth_rotation._COOLDOWN_PROFILES', cooldown_data), \
             patch('browser_utils.auth_rotation.get_profile_usage', return_value=1):
            
            # Test with any model - should return None since all have global cooldown
            best_profile = _find_best_profile_in_dirs(
                [self.saved_dir, self.emergency_dir], 
                target_model_id="gemini 3 pro preview"
            )
            
            # Should return None since all profiles are in global cooldown
            self.assertIsNone(best_profile)

    def test_find_best_profile_expired_cooldown(self):
        """Test that expired cooldowns don't exclude profiles"""
        # Mock cooldown data with expired cooldown
        cooldown_data = {
            self.profile1: {
                "gemini-3-pro-preview": (datetime.now() - timedelta(hours=1)).timestamp(),  # Expired
                "default": (datetime.now() - timedelta(hours=1)).timestamp()  # Expired
            },
        }
        
        with patch('browser_utils.auth_rotation._COOLDOWN_PROFILES', cooldown_data), \
             patch('browser_utils.auth_rotation.get_profile_usage', return_value=1):
            
            # Test with gemini-3-pro-preview - should include profile1 since cooldown expired
            best_profile = _find_best_profile_in_dirs(
                [self.saved_dir, self.emergency_dir], 
                target_model_id="gemini 3 pro preview"
            )
            
            # Should be able to select profile1 since cooldown expired
            self.assertIsNotNone(best_profile)
            self.assertEqual(best_profile, self.profile1)


if __name__ == '__main__':
    unittest.main()