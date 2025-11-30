import unittest
from unittest.mock import patch, MagicMock
import os
import time
from datetime import datetime, timedelta

# Import the module to test
from browser_utils import auth_rotation

class TestSmartRotationLogic(unittest.TestCase):

    def setUp(self):
        # Reset cooldown profiles before each test
        # We need to patch the module-level variable used in the target module
        self.original_cooldowns = auth_rotation._COOLDOWN_PROFILES
        auth_rotation._COOLDOWN_PROFILES = {}
    
    def tearDown(self):
        auth_rotation._COOLDOWN_PROFILES = self.original_cooldowns

    @patch('browser_utils.auth_rotation.glob.glob')
    @patch('browser_utils.auth_rotation.os.path.exists')
    @patch('browser_utils.auth_rotation.get_profile_usage')
    def test_efficiency_preference(self, mock_usage, mock_exists, mock_glob):
        """
        Scenario 1: The "Efficiency" Test
        Profile_Partial: Cooldown on "Gemini 2.5", Valid for "Gemini 3".
        Profile_Fresh: Valid for ALL.
        Action: Request "Gemini 3".
        Expectation: Profile_Partial MUST be selected.
        """
        print("\n--- Test 1: Efficiency Preference ---")
        
        # Setup Files - Use abspath to ensure consistency with os.path.abspath usage in actual code
        profile_partial = os.path.abspath("/abs/path/profile_partial.json")
        profile_fresh = os.path.abspath("/abs/path/profile_fresh.json")
        
        # Important: Order in glob doesn't matter for the test logic, but we provide them
        mock_glob.return_value = [profile_partial, profile_fresh]
        mock_exists.return_value = True
        
        # Setup Usage 
        # Crucial: Profile_Fresh has LOWER usage. 
        # Under OLD logic, Fresh wins. 
        # Under NEW logic, Partial (Efficiency Score 1) wins over Fresh (Efficiency Score 0).
        mock_usage.side_effect = lambda p: 2000 if p == profile_partial else 1000
        
        # Setup Cooldowns
        # Partial is in cooldown for gemini-2.5-pro
        future_time = datetime.now() + timedelta(hours=1)
        # We modify the module's variable directly as the code uses it directly
        auth_rotation._COOLDOWN_PROFILES[profile_partial] = {
            "gemini-2.5-pro": future_time
        }
        
        # Action: Request Gemini 3
        target_model = "gemini-3-pro-preview"
        selected = auth_rotation._find_best_profile_in_dirs(["/dummy/dir"], target_model)
        
        print(f"Selected: {selected}")
        print(f"Expected: {profile_partial} (because it recycles partially exhausted profile)")
        
        # Assertion
        self.assertEqual(selected, profile_partial, "Should prefer partially exhausted profile over fresh one, even if fresh has lower usage")

    @patch('browser_utils.auth_rotation.glob.glob')
    @patch('browser_utils.auth_rotation.os.path.exists')
    @patch('browser_utils.auth_rotation.get_profile_usage')
    def test_safety_exclusion(self, mock_usage, mock_exists, mock_glob):
        """
        Scenario 2: The "Safety" Test
        Profile_Partial: Cooldown on "Gemini 2.5".
        Profile_Fresh: Valid for ALL.
        Action: Request "Gemini 2.5".
        Expectation: Profile_Fresh MUST be selected.
        """
        print("\n--- Test 2: Safety Exclusion ---")
        
        profile_partial = os.path.abspath("/abs/path/profile_partial.json")
        profile_fresh = os.path.abspath("/abs/path/profile_fresh.json")
        
        mock_glob.return_value = [profile_partial, profile_fresh]
        mock_exists.return_value = True
        mock_usage.side_effect = lambda p: 100 # Usage equal
        
        # Setup Cooldowns
        future_time = datetime.now() + timedelta(hours=1)
        auth_rotation._COOLDOWN_PROFILES[profile_partial] = {
            "gemini-2.5-pro": future_time
        }
        
        # Action: Request Gemini 2.5
        target_model = "gemini-2.5-pro"
        selected = auth_rotation._find_best_profile_in_dirs(["/dummy/dir"], target_model)
        
        print(f"Selected: {selected}")
        print(f"Expected: {profile_fresh}")
        
        self.assertEqual(selected, profile_fresh, "Should exclude profile in cooldown for target model")

    @patch('browser_utils.auth_rotation.glob.glob')
    @patch('browser_utils.auth_rotation.os.path.exists')
    @patch('browser_utils.auth_rotation.get_profile_usage')
    def test_wear_leveling(self, mock_usage, mock_exists, mock_glob):
        """
        Scenario 3: The "Wear Leveling" Test
        Profile_A: Valid, Usage 1000.
        Profile_B: Valid, Usage 2000.
        Action: Request any.
        Expectation: Profile_A MUST be selected.
        """
        print("\n--- Test 3: Wear Leveling ---")
        
        profile_a = os.path.abspath("/abs/path/profile_a.json")
        profile_b = os.path.abspath("/abs/path/profile_b.json")
        
        mock_glob.return_value = [profile_a, profile_b]
        mock_exists.return_value = True
        
        # Setup Usage
        mock_usage.side_effect = lambda p: 1000 if p == profile_a else 2000
        
        # No Cooldowns -> Equal Efficiency Score (0)
        auth_rotation._COOLDOWN_PROFILES = {}
        
        target_model = "gemini-3-pro-preview"
        selected = auth_rotation._find_best_profile_in_dirs(["/dummy/dir"], target_model)
        
        print(f"Selected: {selected}")
        print(f"Expected: {profile_a}")
        
        self.assertEqual(selected, profile_a, "Should prefer lower usage when efficiency scores are equal")

    @patch('browser_utils.auth_rotation.glob.glob')
    @patch('browser_utils.auth_rotation.os.path.exists')
    @patch('browser_utils.auth_rotation.get_profile_usage')
    def test_legacy_json_compatibility(self, mock_usage, mock_exists, mock_glob):
        """
        Scenario 4: Compatibility Test with User's JSON Structure.
        Verifies that the logic handles mixed types (datetime objects from JSON load vs floats from runtime)
        and absolute paths correctly.
        """
        print("\n--- Test 4: Legacy JSON Compatibility ---")
        
        # 1. Setup paths exactly as they might appear on Windows (escaped in code, but clean strings in memory)
        # Using a raw string for the path to simulate the absolute path key
        profile_path = os.path.abspath("auth_profiles/saved/rosavival002.json")
        
        # 2. Setup Cooldowns mimicking load_cooldown_profiles output (datetime objects)
        # User provided: "gemini-2.5-pro": "2025-12-01T01:52:00.112199"
        # Since this is in the future, it should count as an active cooldown.
        future_iso = datetime.now() + timedelta(days=365) # Ensure it's in the future
        
        auth_rotation._COOLDOWN_PROFILES = {
            profile_path: {
                "gemini-2.5-pro": future_iso, # Object type: datetime (simulating loaded JSON)
                "gemini-runtime-added": time.time() + 9999 # Object type: float (simulating runtime add)
            }
        }
        
        # 3. Setup Files
        mock_glob.return_value = [profile_path]
        mock_exists.return_value = True
        mock_usage.return_value = 500
        
        # 4. Action: Request a DIFFERENT model (gemini-3)
        # The profile is in cooldown for gemini-2.5 (datetime) and gemini-runtime (float).
        # Both are "Other" models.
        # Both are in the future.
        # Efficiency Score should be 2.
        
        target_model = "gemini-3-pro-preview"
        
        # We need to spy on the internal priority calculation to verify it didn't crash
        # and calculated score > 0.
        # Since we can't easily spy on the inner function call result without more complex mocking,
        # we'll rely on the function returning successfully.
        
        try:
            selected = auth_rotation._find_best_profile_in_dirs(["/dummy/dir"], target_model)
            print(f"Selected: {selected}")
            self.assertEqual(selected, profile_path, "Should successfully select profile using legacy/mixed data types")
        except Exception as e:
            self.fail(f"Compatibility test failed with error: {e}")

if __name__ == '__main__':
    unittest.main()
