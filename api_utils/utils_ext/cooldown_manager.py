import json
import os
import threading
from datetime import datetime

COOLDOWN_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'cooldown_status.json')
_lock = threading.Lock()

def load_cooldown_profiles():
    """
    Loads the cooldown profiles from the persistent JSON file.

    Returns:
        dict: A dictionary of cooldown profiles.
    """
    with _lock:
        if not os.path.exists(COOLDOWN_FILE):
            return {}
        try:
            with open(COOLDOWN_FILE, 'r') as f:
                data = json.load(f)
                # Convert ISO 8601 strings back to datetime objects
                profiles = {}
                for profile, ts in data.items():
                    try:
                        profiles[profile] = datetime.fromisoformat(ts)
                    except (ValueError, TypeError):
                        continue
                return profiles
        except (json.JSONDecodeError, IOError):
            return {}

def save_cooldown_profiles(profiles):
    """
    Saves the cooldown profiles to the persistent JSON file.

    Args:
        profiles (dict): A dictionary of cooldown profiles to save.
    """
    with _lock:
        try:
            # Convert datetime objects to ISO 8601 strings for JSON serialization
            serializable_profiles = {}
            for profile, ts in profiles.items():
                if isinstance(ts, datetime):
                    serializable_profiles[profile] = ts.isoformat()
                elif isinstance(ts, (int, float)):
                    # Handle float timestamps if they slip in
                    try:
                        serializable_profiles[profile] = datetime.fromtimestamp(ts).isoformat()
                    except (ValueError, OSError):
                        pass
            
            with open(COOLDOWN_FILE, 'w') as f:
                json.dump(serializable_profiles, f, indent=4)
        except IOError:
            pass