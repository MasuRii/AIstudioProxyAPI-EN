import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

# Add repository root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import AFTER sys.path modification
from api_utils.utils_ext import cooldown_manager


class TestCooldownPersistence(unittest.TestCase):
    def setUp(self):
        # Create a temporary file for testing
        self.test_file = 'test_cooldown_status.json'
        self.patcher = patch('api_utils.utils_ext.cooldown_manager.COOLDOWN_FILE', self.test_file)
        self.mock_file = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_legacy_persistence(self):
        """Test saving and loading flat structure (legacy behavior)"""
        now = datetime.now()
        profiles = {
            'profile1': now,
            'profile2': now - timedelta(hours=1)
        }
        
        cooldown_manager.save_cooldown_profiles(profiles)
        
        loaded_profiles = cooldown_manager.load_cooldown_profiles()
        
        self.assertIn('profile1', loaded_profiles)
        self.assertIsInstance(loaded_profiles['profile1'], datetime)
        # Compare ISO strings to avoid microsecond precision issues during serialization
        self.assertEqual(loaded_profiles['profile1'].isoformat(), now.isoformat())

    def test_nested_persistence(self):
        """Test saving and loading nested structure (model-specific cooldowns)"""
        now = datetime.now()
        profiles = {
            'profile1': {
                'gpt-4': now,
                'claude-3': now - timedelta(hours=1)
            },
            'profile2': now
        }
        
        cooldown_manager.save_cooldown_profiles(profiles)
        
        loaded_profiles = cooldown_manager.load_cooldown_profiles()
        
        # Check nested structure
        self.assertIn('profile1', loaded_profiles)
        self.assertIsInstance(loaded_profiles['profile1'], dict)
        self.assertIn('gpt-4', loaded_profiles['profile1'])
        self.assertEqual(loaded_profiles['profile1']['gpt-4'].isoformat(), now.isoformat())
        
        # Check mixed flat structure
        self.assertIn('profile2', loaded_profiles)
        self.assertIsInstance(loaded_profiles['profile2'], datetime)
        self.assertEqual(loaded_profiles['profile2'].isoformat(), now.isoformat())

    def test_corrupted_data_handling(self):
        """Test handling of corrupted data"""
        with open(self.test_file, 'w') as f:
            f.write("{invalid_json")
            
        loaded_profiles = cooldown_manager.load_cooldown_profiles()
        self.assertEqual(loaded_profiles, {})

if __name__ == '__main__':
    unittest.main()