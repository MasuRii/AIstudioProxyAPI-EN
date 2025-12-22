import asyncio
import json
import logging
import os
from typing import Dict

logger = logging.getLogger("UsageTracker")

USAGE_FILE = os.path.join("config", "profile_usage.json")
_USAGE_LOCK = asyncio.Lock()

def _load_usage_data() -> Dict[str, int]:
    """Internal function to load usage data from disk."""
    if not os.path.exists(USAGE_FILE):
        return {}
    try:
        with open(USAGE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load profile usage data: {e}")
        return {}

def _save_usage_data(data: Dict[str, int]) -> None:
    """Internal function to save usage data to disk."""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
        with open(USAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        logger.error(f"Failed to save profile usage data: {e}")

async def increment_profile_usage(profile_path: str, tokens: int) -> None:
    """
    Increments the usage count for a specific profile.
    This function is async and thread-safe via asyncio.Lock.
    """
    if not profile_path or not os.path.exists(profile_path):
        return

    # Normalize path to ensure consistency as key
    profile_path = os.path.abspath(profile_path)

    async with _USAGE_LOCK:
        usage_data = _load_usage_data()
        
        # Smart path reconciliation: Check if we have data for this file under a different path
        target_key = profile_path
        if profile_path not in usage_data:
            profile_basename = os.path.basename(profile_path)
            for key in list(usage_data.keys()):
                if os.path.basename(key) == profile_basename:
                    # Found a match by filename! Migrate the data to the new path
                    logger.info(f"Migrating usage data for '{profile_basename}' from '{key}' to '{profile_path}'")
                    usage_data[profile_path] = usage_data.pop(key)
                    target_key = profile_path
                    break
        
        current_usage = usage_data.get(target_key, 0)
        usage_data[target_key] = current_usage + tokens
        _save_usage_data(usage_data)
        logger.debug(f"Updated usage for {os.path.basename(profile_path)}: +{tokens} tokens (Total: {usage_data[target_key]})")

def get_profile_usage(profile_path: str) -> int:
    """
    Returns the total usage for a profile.
    Reads directly from file (blocking), suitable for auth rotation logic which might run in sync context or low frequency.
    For high frequency, consider caching.
    Includes fallback logic to find usage by filename if absolute path doesn't match (handles moved files).
    """
    profile_path = os.path.abspath(profile_path)
    usage_data = _load_usage_data()
    
    # Direct match
    if profile_path in usage_data:
        return usage_data[profile_path]
        
    # Fallback: Match by filename
    # This handles cases where files are moved (e.g. saved -> emergency) but usage data has old path
    profile_basename = os.path.basename(profile_path)
    for key, usage in usage_data.items():
        if os.path.basename(key) == profile_basename:
            return usage
            
    return 0