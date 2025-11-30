import asyncio
import os
import logging
import glob
import time
import random
import json
from datetime import datetime, timedelta
from typing import Optional
from playwright.async_api import Page, TimeoutError


from config.global_state import GlobalState
from config.settings import (
    HIGH_TRAFFIC_QUEUE_THRESHOLD, 
    ROTATION_DEPLETION_GUARD_HIGH_TRAFFIC,
    AUTO_ROTATE_AUTH_PROFILE
)
from config.timeouts import RATE_LIMIT_COOLDOWN_SECONDS, QUOTA_EXCEEDED_COOLDOWN_SECONDS
from config import AI_STUDIO_URL_PATTERN
from config.selectors import PROMPT_TEXTAREA_SELECTOR
import server  # To access global browser/page instances
from api_utils.utils_ext.usage_tracker import get_profile_usage
from api_utils.utils_ext.cooldown_manager import load_cooldown_profiles, save_cooldown_profiles

logger = logging.getLogger("AuthRotation")

# Track recently used profiles to avoid rapid cycling/reuse
# Maps filename -> timestamp of last use
_USED_PROFILES_HISTORY = {}
_HISTORY_RETENTION_SECONDS = 3600 * 2 # 2 hours retention for history

# Profiles currently in cooldown (e.g. due to quota limit)
# Maps filename -> Dict[model_id, expiry_timestamp] OR filename -> expiry_timestamp (legacy/global)
_COOLDOWN_PROFILES = load_cooldown_profiles()

# [FINAL-02] Depletion Guard: Track rotation attempts
_ROTATION_TIMESTAMPS = []
_ROTATION_LIMIT_WINDOW = 60 # seconds
_ROTATION_LIMIT_COUNT = 3   # max attempts per window

def _find_best_profile_in_dirs(directories: list[str], target_model_id: str = None) -> Optional[str]:
    """
    Finds the best available profile within a given list of directories.
    - Scans for .json files.
    - Excludes profiles in cooldown (Global or Model-Specific).
    - Sorts by usage count (ascending) and then randomly.
    """
    if not directories or not isinstance(directories, list):
        return None

    logger.info(f"[DEBUG] Scanning directories: {directories}")
    all_profiles = []
    for d in directories:
        if d and isinstance(d, str) and os.path.exists(d):
            files = glob.glob(os.path.join(d, "*.json"))
            logger.info(f"[DEBUG] Found {len(files)} profiles in {d}")
            all_profiles.extend([os.path.abspath(f) for f in files])
        else:
            logger.warning(f"[DEBUG] Directory missing or invalid: {d} (Abs: {os.path.abspath(d) if d else 'None'})")

    if not all_profiles:
        logger.warning(f"[DEBUG] No profiles found in {directories}")
        return None

    # Filter out profiles that don't exist or are in cooldown
    valid_profiles = []
    now = time.time()
    
    for p in all_profiles:
        if not os.path.exists(p):
            continue
            
        if p in _COOLDOWN_PROFILES:
            cooldown_data = _COOLDOWN_PROFILES[p]
            
            # Check if cooldown is active
            is_cooldown_active = False
            
            if isinstance(cooldown_data, dict):
                # New Format: Dict[model_id, timestamp]
                # Check Global Cooldown
                if "global" in cooldown_data:
                     ts = cooldown_data["global"]
                     ts_val = ts.timestamp() if hasattr(ts, 'timestamp') else ts
                     if ts_val > now:
                         is_cooldown_active = True
                
                # Check Specific Model Cooldown
                if not is_cooldown_active and target_model_id:
                     model_key = target_model_id.lower()
                     if model_key in cooldown_data:
                         ts = cooldown_data[model_key]
                         ts_val = ts.timestamp() if hasattr(ts, 'timestamp') else ts
                         if ts_val > now:
                             is_cooldown_active = True
            else:
                # Legacy Format: timestamp direct
                if cooldown_data:
                    ts = cooldown_data
                    ts_val = ts.timestamp() if hasattr(ts, 'timestamp') else ts
                    if isinstance(ts_val, (int, float)) and ts_val > now:
                        is_cooldown_active = True
            
            if is_cooldown_active:
                continue
                
        valid_profiles.append(p)

    if not valid_profiles:
        return None

    # Usage-Based Selection Logic:
    # 1. Random shuffle (secondary sort factor)
    random.shuffle(valid_profiles)
    # 2. Sort by usage (primary sort factor, stable sort preserves randomness for ties)
    valid_profiles.sort(key=get_profile_usage)

    return valid_profiles[0]


def _get_next_profile(target_model_id: str = None) -> Optional[str]:
    """
    Implements a two-tiered profile selection system: Standard and Emergency.

    Tier 1 (Standard):
    - Scans `auth_profiles/saved` and `auth_profiles/active`.
    - Selects the best profile based on usage and cooldown status.

    Tier 2 (Emergency):
    - If no standard profiles are available, falls back to `auth_profiles/emergency`.
    - Selects the best emergency profile using the same logic.
    """
    # Ensure the emergency directory exists
    emergency_dir = "auth_profiles/emergency"
    abs_emergency = os.path.abspath(emergency_dir)
    logger.info(f"[DEBUG] Emergency Dir: {emergency_dir} (Absolute: {abs_emergency})")
    os.makedirs(emergency_dir, exist_ok=True)
    
    # Note: Cooldown cleanup is complex with nested structure.
    # We rely on check-time filtering in _find_best_profile_in_dirs to handle expired entries effectively.

    # --- Tier 1: Standard Profiles ---
    logger.info(f"Tier 1: Searching for standard profiles... (Target Model: {target_model_id or 'Any'})")
    standard_dirs = ["auth_profiles/saved", "auth_profiles/active"]
    best_profile = _find_best_profile_in_dirs(standard_dirs, target_model_id)

    if best_profile:
        usage_val = get_profile_usage(best_profile)
        logger.info(f"🎯 Selected standard profile '{os.path.basename(best_profile)}' with usage: {usage_val}")
        return best_profile

    # --- Tier 2: Emergency Profiles ---
    logger.warning("Tier 1 yielded no profiles. Falling back to Tier 2: Emergency Pool.")
    emergency_dirs = [emergency_dir]
    best_emergency_profile = _find_best_profile_in_dirs(emergency_dirs, target_model_id)

    if best_emergency_profile:
        usage_val = get_profile_usage(best_emergency_profile)
        logger.info(f"🚨 Selected emergency profile '{os.path.basename(best_emergency_profile)}' with usage: {usage_val}")
        return best_emergency_profile

    logger.error("No available profiles in standard or emergency pools.")
    return None


async def _perform_canary_test(page: Page) -> bool:
    """
    Performs a simple check to ensure the new profile is healthy.
    Navigates to the chat page and verifies a key element is present.
    """
    if not page or page.is_closed():
        logger.warning("⚠️ Canary Test: Page is not available.")
        return False

    try:
        logger.info("🔬 Performing Canary Test on new profile...")
        target_url = f"https://{AI_STUDIO_URL_PATTERN}prompts/new_chat"
        await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

        # Check for a reliable element that indicates a logged-in state
        await page.wait_for_selector(PROMPT_TEXTAREA_SELECTOR, timeout=15000)

        logger.info("✅ Canary Test Passed: Profile is healthy.")
        return True
    except TimeoutError:
        logger.warning("❌ Canary Test Failed: Timed out waiting for key element. Profile is likely bad.")
        return False
    except Exception as e:
        logger.error(f"❌ Canary Test Failed: Unexpected error - {e}", exc_info=True)
        return False


async def perform_auth_rotation(target_model_id: str = None) -> bool:
    """
    Performs the authentication profile rotation with a soft-swap and canary test.
    
    Checks AUTO_ROTATE_AUTH_PROFILE environment variable to determine if rotation should proceed.

    1. Acquires Hard Lock (stops requests).
    2. Enters a loop to find a healthy profile.
    3. Selects next profile, puts the old one in cooldown.
    4. Performs a soft-swap of cookies.
    5. Runs a canary test to validate the new profile.
    6. If healthy, breaks the loop and releases the lock.
    7. If unhealthy, adds the profile to cooldown and repeats.
    """
    
    # Check if auto-rotation is enabled via environment variable
    if not AUTO_ROTATE_AUTH_PROFILE:
        logger.info("🔒 Auth rotation is disabled via AUTO_ROTATE_AUTH_PROFILE environment variable")
        logger.info("♻️ ROTATION SKIPPED - Auto-rotation disabled")
        logger.info("♻️ =========================================")
        return False
    
    # [OBS-04] Explicit Rotation Logging with Visual Separators
    logger.info("♻️ =========================================")
    logger.info("♻️ INITIATING AUTH ROTATION")
    logger.info("♻️ =========================================")
    
    # Avoid re-entry if already rotating (Atomic Check & Wait)
    if not GlobalState.AUTH_ROTATION_LOCK.is_set():
        logger.info("⚠️ Rotation already in progress (Lock is cleared). Waiting for completion...")
        await GlobalState.AUTH_ROTATION_LOCK.wait()
        logger.info("♻️ Rotation skipped - already in progress (Waited for completion)")
        logger.info("♻️ =========================================")
        return True

    # Atomically acquire the lock
    GlobalState.AUTH_ROTATION_LOCK.clear()
    logger.info("🔒 Request processing locked.")

    should_release_lock = True

    try:
        # [FINAL-02] Depletion Guard Check
        global _ROTATION_TIMESTAMPS
        current_time = time.time()

        # Dynamic "Rotation Window" Adjustment
        if GlobalState.queued_request_count > HIGH_TRAFFIC_QUEUE_THRESHOLD:
            effective_rotation_limit = ROTATION_DEPLETION_GUARD_HIGH_TRAFFIC
            logger.info(f"High traffic detected ({GlobalState.queued_request_count} queued). Using lenient rotation guard: {effective_rotation_limit}")
        else:
            effective_rotation_limit = _ROTATION_LIMIT_COUNT

        # Filter timestamps within the window
        _ROTATION_TIMESTAMPS = [t for t in _ROTATION_TIMESTAMPS if current_time - t < _ROTATION_LIMIT_WINDOW]
        
        if len(_ROTATION_TIMESTAMPS) >= effective_rotation_limit:
            logger.critical(f"🚨 CRITICAL: TOO MANY ROTATIONS! (limit: {effective_rotation_limit}) All accounts may be exhausted. Stopping Browser & Locking API.")
            logger.critical("♻️ ROTATION ABORTED - System Exhausted")
            logger.critical("♻️ =========================================")
            
            # SOFT DEPLETION STRATEGY: Avoid hard shutdown to maintain "No Downtime" goal
            logger.critical("🚨 DEPLETION DETECTED: Switching to emergency operation mode")
            logger.critical("🚨 All profiles exhausted, but avoiding hard shutdown")
            
            # Set emergency mode flag
            GlobalState.DEPLOYMENT_EMERGENCY_MODE = True
            
            # Try to perform soft profile rotation even during depletion
            # This maintains the "No Downtime" requirement
            try:
                # Attempt one final soft rotation with emergency profiles
                emergency_profile = _find_best_profile_in_dirs(["auth_profiles/emergency"])
                if emergency_profile:
                    logger.critical("🚨 Attempting emergency profile activation...")
                    # Perform minimal soft swap for emergency operation
                    if server.page_instance and not server.page_instance.is_closed():
                        with open(emergency_profile, 'r', encoding='utf-8') as f:
                            storage_state = json.load(f)
                        context = server.page_instance.context
                        await context.clear_cookies()
                        await context.add_cookies(storage_state.get('cookies', []))
                        logger.critical("🚨 Emergency profile activated - continuing operation")
                        return True
            except Exception as e:
                logger.critical(f"🚨 Emergency activation failed: {e}")
            
            # Only if soft emergency operation fails, then consider partial shutdown
            # But still try to maintain some level of service
            logger.critical("🚨 Entering minimal operation mode - limited service available")
            
            # PERMANENT LOCK (Do not release GlobalState.AUTH_ROTATION_LOCK)
            # We leave the lock cleared so no new requests can proceed.
            should_release_lock = False
            return False

        # Record this attempt
        _ROTATION_TIMESTAMPS.append(current_time)
        logger.info(f"🔄 Rotation attempt #{len(_ROTATION_TIMESTAMPS)} in current window")
        
        # (Lock is already acquired above)
        
        max_retries = 5
        failed_attempts = 0

        # Note: Nested try block removed, logic flattened into main try/finally
        while failed_attempts < max_retries:
            # 2. Select next profile
            logger.info("🔍 Selecting next auth profile...")
            next_profile_path = _get_next_profile(target_model_id)

            if not next_profile_path:
                logger.critical("❌ Rotation Failed: No available auth profiles found!")
                logger.critical("♻️ ROTATION FAILED - No profiles available")
                logger.critical("♻️ =========================================")
                return False

            # Always place the *previous* profile on cooldown on the first attempt
            if failed_attempts == 0:
                old_profile = getattr(server, 'current_auth_profile_path', 'unknown')
                if old_profile != 'unknown' and os.path.exists(old_profile):
                    # Calculate cooldown based on error type
                    error_type = GlobalState.last_error_type
                    
                    # Ensure existing entry is a dict if it exists
                    if old_profile not in _COOLDOWN_PROFILES or not isinstance(_COOLDOWN_PROFILES[old_profile], dict):
                        _COOLDOWN_PROFILES[old_profile] = {}
                        
                    expiry_ts = (datetime.now() + timedelta(seconds=QUOTA_EXCEEDED_COOLDOWN_SECONDS)).timestamp()
                    rate_limit_ts = (datetime.now() + timedelta(seconds=RATE_LIMIT_COOLDOWN_SECONDS)).timestamp()
                    
                    if error_type == 'RATE_LIMIT':
                         # Rate Limit -> Global Cooldown
                         _COOLDOWN_PROFILES[old_profile]["global"] = rate_limit_ts
                         logger.info(f"❄️ Placing profile in GLOBAL cooldown for {RATE_LIMIT_COOLDOWN_SECONDS}s (Rate Limit).")
                    else:
                         # Quota Exceeded -> Model Specific Cooldowns
                         
                         # 1. Identify models to cooldown
                         models_to_cooldown = set(GlobalState.current_profile_exhausted_models)
                         
                         # 2. Ensure target/current model is included if appropriate
                         # If a specific target was requested, it's likely the one failing
                         if target_model_id:
                             models_to_cooldown.add(target_model_id.lower())
                         
                         # 3. Fallback: If no models identified yet (e.g. UI detection triggered rotation before token count update),
                         # fallback to the currently active model on the server.
                         if not models_to_cooldown:
                             if server.current_ai_studio_model_id:
                                 models_to_cooldown.add(server.current_ai_studio_model_id.lower())
                             else:
                                 # Last resort
                                 models_to_cooldown.add("default")

                         # 4. Apply cooldowns
                         for m_id in models_to_cooldown:
                             _COOLDOWN_PROFILES[old_profile][m_id] = expiry_ts
                             logger.info(f"❄️ Placing profile in cooldown for model '{m_id}' for {QUOTA_EXCEEDED_COOLDOWN_SECONDS}s.")

                    save_cooldown_profiles(_COOLDOWN_PROFILES)

            new_profile_name = os.path.basename(next_profile_path)
            logger.info(f"👉 Attempting to rotate to profile: {new_profile_name}")

            # Update global state for the new profile path
            server.current_auth_profile_path = next_profile_path
            os.environ['ACTIVE_AUTH_JSON_PATH'] = next_profile_path

            # 3. Soft Context Swap
            logger.info("🚀 Performing Soft Context Swap...")
            if not server.page_instance or server.page_instance.is_closed():
                logger.error("❌ Page instance not found or closed, cannot perform soft swap.")
                return False

            try:
                try:
                    with open(next_profile_path, 'r', encoding='utf-8') as f:
                        storage_state = json.load(f)
                except (json.JSONDecodeError, OSError) as json_err:
                    logger.error(f"❌ Corrupt or inaccessible profile file '{new_profile_name}': {json_err}")
                    # Treat as a failed attempt, will trigger cooldown logic in outer except/continue
                    raise

                if not isinstance(storage_state, dict):
                    raise ValueError(f"Invalid profile format in '{new_profile_name}'")

                context = server.page_instance.context
                await context.clear_cookies()
                await context.add_cookies(storage_state.get('cookies', []))
                logger.info("✅ Injected new cookies.")

                # 4. Perform Canary Test
                if await _perform_canary_test(server.page_instance):
                    # Healthy profile found, break the loop
                    GlobalState.reset_quota_status()
                    # GlobalState.current_profile_token_count = 0 # Removed: handled by reset_quota_status
                    logger.info(f"♻️ ROTATION SUCCESSFUL with profile: {new_profile_name}")
                    logger.info("♻️ =========================================")
                    return True
                else:
                    # Canary test failed, profile is bad
                    logger.warning(f" Canary test failed for {new_profile_name}. Adding to cooldown and retrying.")
                    failed_attempts += 1
                    
                    # Place failed profile in cooldown immediately
                    expiry_time = datetime.now() + timedelta(seconds=QUOTA_EXCEEDED_COOLDOWN_SECONDS)
                    _COOLDOWN_PROFILES[next_profile_path] = expiry_time
                    save_cooldown_profiles(_COOLDOWN_PROFILES)
                    logger.info(f"❄️ Placing unhealthy profile '{new_profile_name}' in cooldown for {QUOTA_EXCEEDED_COOLDOWN_SECONDS}s.")
                    continue # Try next profile

            except Exception as swap_err:
                logger.error(f"❌ Failed to perform soft swap for {new_profile_name}: {swap_err}")
                failed_attempts += 1
                # Also place this profile on cooldown
                expiry_time = datetime.now() + timedelta(seconds=QUOTA_EXCEEDED_COOLDOWN_SECONDS)
                _COOLDOWN_PROFILES[next_profile_path] = expiry_time
                save_cooldown_profiles(_COOLDOWN_PROFILES)
                logger.info(f"❄️ Placing swap-failed profile '{new_profile_name}' in cooldown.")
                continue

        # If loop finishes without success
        logger.critical(f"🚨 ROTATION FAILED: All {max_retries} attempts to find a healthy profile failed.")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error during auth rotation loop: {e}", exc_info=True)
        logger.error("♻️ ROTATION FAILED - Unexpected error")
        logger.error("♻️ =========================================")
        return False
    finally:
        # 5. Release lock (if not permanently locked)
        if should_release_lock:
            GlobalState.AUTH_ROTATION_LOCK.set()
            logger.info("🔓 Request processing unlocked.")
            logger.info("♻️ Rotation flow completed")
            logger.info("♻️ =========================================")