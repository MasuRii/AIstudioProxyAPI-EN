import asyncio
import threading
import time
import logging
from config.settings import PROACTIVE_ROTATION_TOKEN_LIMIT

logger = logging.getLogger(__name__)

class GlobalState:
    """
    Singleton class to hold global application state, specifically for Quota Exceeded logic.
    """
    _instance = None
    IS_QUOTA_EXCEEDED = False
    QUOTA_EXCEEDED_TIMESTAMP = 0.0
    
    # Global Event for holding requests during auth rotation
    # Initially set to True (allowed) by init_rotation_lock()
    AUTH_ROTATION_LOCK = asyncio.Event()
    
    # Global Event to signal Quota Exceeded immediately
    QUOTA_EXCEEDED_EVENT = asyncio.Event()

    # Track the type of the last error for adaptive cooldowns
    # Values: 'RATE_LIMIT', 'QUOTA_EXCEEDED', or None
    last_error_type = None

    # Token usage tracking for proactive rotation
    current_profile_token_count = 0

    # [FINAL-02] Dynamic Rotation Guard: Track queued requests
    queued_request_count = 0

    # Global Shutdown Event (Thread-safe for signal handlers)
    # Used to circuit-break logic during aggressive shutdown
    IS_SHUTTING_DOWN = threading.Event()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
        return cls._instance

    @classmethod
    def init_rotation_lock(cls):
        """Initialize the rotation lock to allow requests."""
        cls.AUTH_ROTATION_LOCK.set()
        logger.info("🔐 Global Auth Rotation Lock initialized (OPEN).")

    @classmethod
    def set_quota_exceeded(cls, message: str = ""):
        """
        Sets the global quota exceeded flag and logs a critical warning.
        Also determines the error type based on the message for adaptive cooldowns.
        """
        if not cls.IS_QUOTA_EXCEEDED:
            cls.IS_QUOTA_EXCEEDED = True
            cls.QUOTA_EXCEEDED_TIMESTAMP = time.time()
            cls.QUOTA_EXCEEDED_EVENT.set()
            
            # Determine error type
            msg_lower = message.lower()
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

            logger.critical(f"⛔ GLOBAL ALERT: Quota Exceeded! Type: {cls.last_error_type} (Event Signal Sent)")

    @classmethod
    def reset_quota_status(cls):
        """
        Resets the global quota exceeded flag.
        """
        cls.IS_QUOTA_EXCEEDED = False
        cls.QUOTA_EXCEEDED_TIMESTAMP = 0.0
        cls.last_error_type = None
        cls.QUOTA_EXCEEDED_EVENT.clear()
        logger.info("✅ GLOBAL ALERT: Quota status manually reset.")

    @classmethod
    def increment_token_count(cls, count: int):
        """
        Increments the token count for the current profile and checks if it exceeds the limit.
        """
        if count <= 0:
            return
            
        cls.current_profile_token_count += count
        logger.info(f"📊 Token usage updated: +{count} => {cls.current_profile_token_count}/{PROACTIVE_ROTATION_TOKEN_LIMIT}")
        
        if cls.current_profile_token_count >= PROACTIVE_ROTATION_TOKEN_LIMIT:
            logger.warning(f"⚠️ Proactive Rotation Triggered: Token limit exceeded ({cls.current_profile_token_count} >= {PROACTIVE_ROTATION_TOKEN_LIMIT})")
            cls.set_quota_exceeded()