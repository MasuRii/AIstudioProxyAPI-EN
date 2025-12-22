import json
import logging
import os
import threading
from datetime import datetime

COOLDOWN_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "cooldown_status.json"
)
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
            with open(COOLDOWN_FILE, "r") as f:
                data = json.load(f)

            profiles = {}
            for profile, val in data.items():
                if isinstance(val, dict):
                    # Handle nested model-specific cooldowns
                    model_cooldowns = {}
                    for model_id, ts in val.items():
                        try:
                            model_cooldowns[model_id] = datetime.fromisoformat(ts)
                        except (ValueError, TypeError):
                            continue
                    if model_cooldowns:
                        # Clean up redundant "default" entries when specific models exist
                        has_specific_models = any(
                            model_id != "default" for model_id in model_cooldowns.keys()
                        )
                        if has_specific_models and "default" in model_cooldowns:
                            logger = logging.getLogger("CooldownManager")
                            logger.info(
                                f"🧹 Cleaning up redundant 'default' entry for profile {os.path.basename(profile)}"
                            )
                            del model_cooldowns["default"]
                        profiles[profile] = model_cooldowns
                else:
                    # Handle legacy/global cooldowns
                    try:
                        profiles[profile] = datetime.fromisoformat(val)
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
            serializable_profiles = {}
            for profile, data in profiles.items():
                if isinstance(data, dict):
                    # Handle nested model-specific cooldowns
                    model_cooldowns = {}
                    for model_id, ts in data.items():
                        if isinstance(ts, datetime):
                            model_cooldowns[model_id] = ts.isoformat()
                        elif isinstance(ts, (int, float)):
                            try:
                                model_cooldowns[model_id] = datetime.fromtimestamp(
                                    ts
                                ).isoformat()
                            except (ValueError, OSError):
                                pass
                    serializable_profiles[profile] = model_cooldowns

                elif isinstance(data, datetime):
                    serializable_profiles[profile] = data.isoformat()
                elif isinstance(data, (int, float)):
                    try:
                        serializable_profiles[profile] = datetime.fromtimestamp(
                            data
                        ).isoformat()
                    except (ValueError, OSError):
                        pass

            with open(COOLDOWN_FILE, "w") as f:
                json.dump(serializable_profiles, f, indent=4)
        except IOError:
            pass
