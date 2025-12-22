import glob
import logging
import os
import sys
from unittest.mock import MagicMock

# --- MOCKS ---
sys.modules['config'] = MagicMock()
sys.modules['config.global_state'] = MagicMock()
sys.modules['config.settings'] = MagicMock()
sys.modules['config.timeouts'] = MagicMock()
sys.modules['config.selectors'] = MagicMock()
sys.modules['server'] = MagicMock()
sys.modules['api_utils.utils_ext.usage_tracker'] = MagicMock()
sys.modules['api_utils.utils_ext.cooldown_manager'] = MagicMock()
sys.modules['playwright.async_api'] = MagicMock()

# Specific attributes
sys.modules['config.settings'].HIGH_TRAFFIC_QUEUE_THRESHOLD = 5
sys.modules['config.settings'].ROTATION_DEPLETION_GUARD_HIGH_TRAFFIC = 10
sys.modules['config.settings'].AUTO_ROTATE_AUTH_PROFILE = True
sys.modules['config.timeouts'].RATE_LIMIT_COOLDOWN_SECONDS = 300
sys.modules['config.timeouts'].QUOTA_EXCEEDED_COOLDOWN_SECONDS = 14400
sys.modules['api_utils.utils_ext.usage_tracker'].get_profile_usage.return_value = 0
sys.modules['api_utils.utils_ext.cooldown_manager'].load_cooldown_profiles.return_value = {}

# Setup logging
logging.basicConfig(level=logging.INFO)

# --- IMPORT ---
# We need to import the actual functions. 
# Since we mocked dependencies, we can import the module.
from browser_utils.auth_rotation import _get_next_profile


# --- TEST SETUP ---
def setup_test_files():
    dirs = [
        "auth_profiles/active",
        "auth_profiles/saved",
        "auth_profiles/emergency"
    ]
    for d in dirs:
        if os.path.exists(d):
            # Clean up json files
            for f in glob.glob(os.path.join(d, "*.json")):
                os.remove(f)
        else:
            os.makedirs(d)
    return dirs

def create_profile(path):
    with open(path, 'w') as f:
        f.write("{}")

# --- TESTS ---

def test_emergency_inclusion():
    print("--- Test 1: Emergency Inclusion in Standard Scan ---")
    setup_test_files()
    
    # Case: Only profile in emergency
    create_profile("auth_profiles/emergency/emergency_1.json")
    
    print("Searching for profile (Active/Saved empty, Emergency has file)...")
    profile = _get_next_profile()
    
    if profile and "emergency" in profile:
        print(f"SUCCESS: Found emergency profile: {profile}")
    else:
        print(f"FAILURE: Did not find emergency profile. Result: {profile}")

def test_active_empty_logic():
    print("\n--- Test 2: Active/Saved Empty ---")
    setup_test_files()
    # No files created
    
    print("Searching for profile (All empty)...")
    profile = _get_next_profile()
    print(f"Result: {profile}")

if __name__ == "__main__":
    try:
        test_emergency_inclusion()
        test_active_empty_logic()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()