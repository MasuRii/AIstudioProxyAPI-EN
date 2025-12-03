import asyncio
import threading
import time
import logging
from typing import Dict, Set
from collections import defaultdict
from config.settings import QUOTA_SOFT_LIMIT, QUOTA_HARD_LIMIT, MODEL_QUOTA_LIMITS
from models.exceptions import QuotaExceededError

logger = logging.getLogger(__name__)

class GlobalState:
    """
    Singleton class to hold global application state, specifically for Quota Exceeded logic.
    """
    _instance = None
    IS_QUOTA_EXCEEDED = False
    NEEDS_ROTATION = False # [GR-01] Soft Signal Flag
    QUOTA_EXCEEDED_TIMESTAMP = 0.0
    
    # Global Event for holding requests during auth rotation
    # Initially set to True (allowed) by init_rotation_lock()
    AUTH_ROTATION_LOCK = asyncio.Event()
    
    # Global Event to signal Quota Exceeded immediately
    QUOTA_EXCEEDED_EVENT = asyncio.Event()

    # Event to signal that a rotation operation has completed.
    rotation_complete_event = asyncio.Event()

    # Track the type of the last error for adaptive cooldowns
    # Values: 'RATE_LIMIT', 'QUOTA_EXCEEDED', or None
    last_error_type = None

    # Token usage tracking for proactive rotation
    # [QUOTA-02] Changed from single int to dict for model-specific tracking
    current_profile_model_usage: Dict[str, int] = defaultdict(int)
    current_profile_exhausted_models: Set[str] = set()

    # [FINAL-02] Dynamic Rotation Guard: Track queued requests
    queued_request_count = 0

    # Global Shutdown Event (Thread-safe for signal handlers)
    # Used to circuit-break logic during aggressive shutdown
    IS_SHUTTING_DOWN = threading.Event()

    # [ID-01] Global Recovery State Manager
    # Flag to indicate if a recovery operation (auth rotation) is currently active
    IS_RECOVERING = False
    # Event to signal that recovery is complete and streams can resume
    RECOVERY_EVENT = asyncio.Event()
    # [FIX-RACE] Track last rotation timestamp to handle race conditions
    LAST_ROTATION_TIMESTAMP = 0.0

    # [CONCURRENCY-FIX] Track the currently active stream request ID
    # Used to gate consumers and prevent zombie streams from processing data
    CURRENT_STREAM_REQ_ID = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
        return cls._instance

    @classmethod
    def start_recovery(cls):
        """
        Signals the start of a recovery operation (e.g., auth rotation).
        Pauses streams and sets the recovery flag.
        """
        cls.IS_RECOVERING = True
        cls.RECOVERY_EVENT.clear()
        logger.info("🔄 SYSTEM: Recovery Mode Initiated. Streams will pause.")

    @classmethod
    def finish_recovery(cls):
        """
        Signals the completion of a recovery operation.
        Resumes streams and clears the recovery flag.
        """
        cls.IS_RECOVERING = False
        cls.RECOVERY_EVENT.set()
        # [FIX-RACE] Update timestamp on finish
        cls.LAST_ROTATION_TIMESTAMP = time.time()
        logger.info(f"✅ SYSTEM: Recovery Mode Finished at {cls.LAST_ROTATION_TIMESTAMP}. Streams resuming.")

    @classmethod
    def init_rotation_lock(cls):
        """Initialize the rotation lock to allow requests."""
        cls.AUTH_ROTATION_LOCK.set()
        logger.info("🔐 Global Auth Rotation Lock initialized (OPEN).")

    @classmethod
    def set_quota_exceeded(cls, message: str = "", model_id: str = None):
        """
        Sets the global quota exceeded flag and logs a critical warning.
        Also determines the error type based on the message for adaptive cooldowns.
        Optionally accepts a model_id to flag specific model exhaustion.
        """
        if not cls.IS_QUOTA_EXCEEDED:
            cls.IS_QUOTA_EXCEEDED = True
            cls.QUOTA_EXCEEDED_TIMESTAMP = time.time()
            cls.QUOTA_EXCEEDED_EVENT.set()
            
            # Determine error type
            safe_message = message if message else ""
            msg_lower = safe_message.lower()
            if "429" in msg_lower or "rate limit" in msg_lower or "resource has been exhausted" in msg_lower:
                # API "RESOURCE_EXHAUSTED" usually means 429/quota shared behavior,
                # but "rate limit" specifically implies a temporary 429.
                # However, Gemini "Resource has been exhausted" is often a harder limit.
                # Let's verify standard Gemini strings:
                # "429: Too Many Requests" -> Rate Limit
                # "429: Resource has been exhausted" -> Quota
                if "too many requests" in msg_lower:
                    cls.last_error_type = 'RATE_LIMIT'
                else:
                    cls.last_error_type = 'QUOTA_EXCEEDED'
            elif "quota" in msg_lower:
                 cls.last_error_type = 'QUOTA_EXCEEDED'
            else:
                 # Default fallback if unknown
                 cls.last_error_type = 'QUOTA_EXCEEDED'
            
            # [FIX] If model_id is provided, immediately mark it as exhausted so rotation logic knows
            if model_id and cls.last_error_type == 'QUOTA_EXCEEDED':
                cls.current_profile_exhausted_models.add(model_id.lower())
                logger.warning(f"⛔ Identified specific model exhaustion: {model_id}")

            logger.critical(f"⛔ GLOBAL ALERT: Quota Exceeded! Type: {cls.last_error_type} (Event Signal Sent)")

    @classmethod
    def reset_quota_status(cls):
        """
        Resets the global quota exceeded flag.
        """
        cls.IS_QUOTA_EXCEEDED = False
        cls.NEEDS_ROTATION = False # Reset soft flag too
        cls.QUOTA_EXCEEDED_TIMESTAMP = 0.0
        cls.last_error_type = None
        cls.QUOTA_EXCEEDED_EVENT.clear()
        
        # [QUOTA-02] Reset model usage stats
        cls.current_profile_model_usage.clear()
        cls.current_profile_exhausted_models.clear()
        
        logger.info("✅ GLOBAL ALERT: Quota status manually reset.")

    @classmethod
    def increment_token_count(cls, count: int, model_id: str = "default"):
        """
        Increments the token count for the current profile and checks if it exceeds the limit.
        [GR-01] Implements Graceful Rotation logic.
        """
        if count <= 0:
            return
            
        # Ensure model_id is a valid string for key usage
        safe_model_id = model_id if model_id else "default"
        model_key = safe_model_id.lower()
        
        cls.current_profile_model_usage[model_key] += count
        current_usage = cls.current_profile_model_usage[model_key]
        
        # Retrieve limit (fallback to global hard limit)
        limit = MODEL_QUOTA_LIMITS.get(model_key, QUOTA_HARD_LIMIT)
        
        # Check Hard Limit (Emergency Kill / Model Exhaustion)
        if current_usage >= limit:
            logger.critical(f"⛔ HARD LIMIT REACHED ({model_key}): {current_usage} >= {limit}. Marking model as exhausted.")
            cls.current_profile_exhausted_models.add(model_key)
            # Trigger global rotation signal
            cls.set_quota_exceeded(message=f"Quota exceeded for model {model_key}")
            # Raise exception to propagate up to request processor
            raise QuotaExceededError(f"Quota exceeded for model {model_key} ({current_usage} >= {limit})")

        # Check Soft Limit (Graceful Signal)
        # Note: Using global soft limit as baseline for rotation signal
        if current_usage >= QUOTA_SOFT_LIMIT and not cls.NEEDS_ROTATION:
            logger.warning(f"🔄 SOFT LIMIT REACHED ({model_key}): {current_usage} >= {QUOTA_SOFT_LIMIT}. Setting NEEDS_ROTATION flag.")
            cls.NEEDS_ROTATION = True
        
        # Log status
        limit_str = f"{QUOTA_SOFT_LIMIT}(Soft)/{limit}(Hard)"
        logger.info(f"📊 Token usage updated ({model_key}): +{count} => {current_usage} (Limits: {limit_str}) | Rotation Pending: {cls.NEEDS_ROTATION}")