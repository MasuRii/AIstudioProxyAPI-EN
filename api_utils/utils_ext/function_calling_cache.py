"""
Function Calling Cache Module

Manages caching of function calling state to avoid redundant UI operations.
Implements digest-based caching for tool definitions and toggle state caching.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import settings
from config.settings import FUNCTION_CALLING_DEBUG
from logging_utils.fc_debug import FCModule, get_fc_logger

# FC debug logger for cache-specific events
fc_logger = get_fc_logger()


@dataclass
class FunctionCallingCacheEntry:
    """Represents a cached function calling state.

    Attributes:
        tools_digest: SHA256 hash of tool definitions (first 16 chars).
        toggle_enabled: Whether FC toggle is on.
        declarations_set: Whether declarations were successfully set.
        timestamp: When cached (epoch seconds).
        model_name: Associated model name (optional).
    """

    tools_digest: str  # SHA256 hash of tool definitions
    toggle_enabled: bool  # Whether FC toggle is on
    declarations_set: bool  # Whether declarations were successfully set
    timestamp: float  # When cached
    model_name: Optional[str] = None  # Associated model


class FunctionCallingCache:
    """
    Manages caching of function calling state to avoid redundant UI operations.

    Caching Strategy:
    1. Toggle State: Cache whether FC toggle is enabled
    2. Tool Digest: Hash tool definitions to detect changes
    3. Invalidation: On model switch, new chat, or explicit clear

    Usage:
        cache = FunctionCallingCache.get_instance()

        # Check if cache is valid before UI operations
        digest = cache.compute_tools_digest(tools)
        if cache.is_cache_valid(digest, model_name):
            # Skip UI operations
            pass
        else:
            # Perform UI operations, then update cache
            cache.update_cache(digest, toggle_enabled=True, declarations_set=True)
    """

    _instance: Optional["FunctionCallingCache"] = None

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the cache.

        Args:
            logger: Optional logger instance. If None, uses default logger.
        """
        self.logger = logger or logging.getLogger("AIStudioProxyServer")
        self._cache: Optional[FunctionCallingCacheEntry] = None
        self._enabled = getattr(settings, "FUNCTION_CALLING_CACHE_ENABLED", True)
        self._debug = getattr(settings, "FUNCTION_CALLING_DEBUG", False)
        self._ttl = getattr(settings, "FUNCTION_CALLING_CACHE_TTL", 0)
        self._hit_count = 0
        self._miss_count = 0

    @classmethod
    def get_instance(
        cls, logger: Optional[logging.Logger] = None
    ) -> "FunctionCallingCache":
        """Get or create the singleton instance.

        Args:
            logger: Optional logger instance.

        Returns:
            The singleton FunctionCallingCache instance.
        """
        if cls._instance is None:
            cls._instance = cls(logger)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None

    def compute_tools_digest(self, tools: List[Dict[str, Any]]) -> str:
        """Compute SHA256 digest of tool definitions for change detection.

        Args:
            tools: List of tool definitions (OpenAI format).

        Returns:
            First 16 characters of SHA256 hex digest.
        """
        if not tools:
            return "empty"

        # Normalize and serialize tools for consistent hashing
        # Sort keys to ensure deterministic output
        try:
            normalized = json.dumps(tools, sort_keys=True, separators=(",", ":"))
            return hashlib.sha256(normalized.encode()).hexdigest()[:16]
        except (TypeError, ValueError) as e:
            if self._debug:
                self.logger.warning(f"[FC:Cache] Failed to compute digest: {e}")
            return "invalid"

    def is_cache_valid(
        self,
        tools_digest: str,
        model_name: Optional[str] = None,
        req_id: str = "",
    ) -> bool:
        """Check if cached state matches current request.

        Args:
            tools_digest: Digest of current tool definitions.
            model_name: Current model name (optional).
            req_id: Request ID for logging.

        Returns:
            True if cache is valid and can be used, False otherwise.
        """
        prefix = f"[{req_id}] " if req_id else ""

        if not self._enabled:
            if self._debug:
                self.logger.debug(f"{prefix}[FC:Cache] Caching disabled")
            if FUNCTION_CALLING_DEBUG:
                fc_logger.debug(FCModule.CACHE, "Caching disabled", req_id=req_id)
            return False

        if self._cache is None:
            if self._debug:
                self.logger.debug(f"{prefix}[FC:Cache] No cached state")
            if FUNCTION_CALLING_DEBUG:
                fc_logger.log_cache_miss(req_id, "no_cached_state")
            self._miss_count += 1
            return False

        # Check TTL if configured
        if self._ttl > 0:
            age = time.time() - self._cache.timestamp
            if age > self._ttl:
                if self._debug:
                    self.logger.debug(
                        f"{prefix}[FC:Cache] Cache expired (age={age:.1f}s > TTL={self._ttl}s)"
                    )
                if FUNCTION_CALLING_DEBUG:
                    fc_logger.log_cache_miss(req_id, f"expired_ttl_{age:.1f}s")
                self._miss_count += 1
                return False

        # Check digest match
        if self._cache.tools_digest != tools_digest:
            if self._debug:
                self.logger.debug(
                    f"{prefix}[FC:Cache] Digest mismatch "
                    f"(cached={self._cache.tools_digest[:8]}... vs current={tools_digest[:8]}...)"
                )
            if FUNCTION_CALLING_DEBUG:
                fc_logger.log_cache_miss(req_id, "digest_mismatch")
            self._miss_count += 1
            return False

        # Check model match if provided
        if (
            model_name
            and self._cache.model_name
            and self._cache.model_name != model_name
        ):
            if self._debug:
                self.logger.debug(
                    f"{prefix}[FC:Cache] Model changed "
                    f"({self._cache.model_name} -> {model_name})"
                )
            if FUNCTION_CALLING_DEBUG:
                fc_logger.log_cache_miss(req_id, "model_changed")
            self._miss_count += 1
            return False

        # Cache is valid
        self._hit_count += 1
        age = time.time() - self._cache.timestamp
        if self._debug:
            self.logger.debug(
                f"{prefix}[FC:Cache] Valid cache found "
                f"(digest={tools_digest[:8]}..., toggle={self._cache.toggle_enabled})"
            )
        if FUNCTION_CALLING_DEBUG:
            fc_logger.log_cache_hit(req_id, tools_digest, age)
        return True

    def get_cached_state(self) -> Optional[FunctionCallingCacheEntry]:
        """Get current cached state if available.

        Returns:
            The cached entry or None if no cache exists.
        """
        return self._cache

    def update_cache(
        self,
        tools_digest: str,
        toggle_enabled: bool,
        declarations_set: bool,
        model_name: Optional[str] = None,
        req_id: str = "",
    ) -> None:
        """Update cache with new state.

        Args:
            tools_digest: Digest of tool definitions.
            toggle_enabled: Whether FC toggle is enabled.
            declarations_set: Whether declarations were set successfully.
            model_name: Model name (optional).
            req_id: Request ID for logging.
        """
        if not self._enabled:
            return

        prefix = f"[{req_id}] " if req_id else ""

        self._cache = FunctionCallingCacheEntry(
            tools_digest=tools_digest,
            toggle_enabled=toggle_enabled,
            declarations_set=declarations_set,
            timestamp=time.time(),
            model_name=model_name,
        )
        if self._debug:
            self.logger.debug(
                f"{prefix}[FC:Cache] Updated: digest={tools_digest[:8]}..., "
                f"toggle={toggle_enabled}, declarations_set={declarations_set}"
            )
        if FUNCTION_CALLING_DEBUG:
            fc_logger.debug(
                FCModule.CACHE,
                f"Cache updated: digest={tools_digest[:8]}..., "
                f"toggle={toggle_enabled}, declarations={declarations_set}",
                req_id=req_id,
            )

    def update_toggle_state(self, enabled: bool, req_id: str = "") -> None:
        """Update just the toggle state without changing other cache data.

        Args:
            enabled: Whether the toggle is enabled.
            req_id: Request ID for logging.
        """
        if self._cache:
            prefix = f"[{req_id}] " if req_id else ""
            self._cache.toggle_enabled = enabled
            self._cache.timestamp = time.time()
            if self._debug:
                self.logger.debug(
                    f"{prefix}[FC:Cache] Toggle updated: enabled={enabled}"
                )

    def invalidate(self, reason: str = "manual", req_id: str = "") -> None:
        """Clear the cache.

        Args:
            reason: Reason for invalidation (for logging).
            req_id: Request ID for logging.
        """
        prefix = f"[{req_id}] " if req_id else ""
        if self._cache:
            if self._debug:
                self.logger.debug(f"{prefix}[FC:Cache] Invalidated: {reason}")
            if FUNCTION_CALLING_DEBUG:
                fc_logger.debug(
                    FCModule.CACHE, f"Cache invalidated: {reason}", req_id=req_id
                )
        self._cache = None

    def is_toggle_cached_enabled(self) -> Optional[bool]:
        """Quick check if toggle is cached as enabled.

        Returns:
            True if toggle is cached as enabled,
            False if cached as disabled,
            None if no cache exists.
        """
        if not self._enabled or self._cache is None:
            return None
        return self._cache.toggle_enabled

    @property
    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._enabled

    @property
    def cache_stats(self) -> Dict[str, Any]:
        """Return cache statistics for debugging.

        Returns:
            Dictionary with cache statistics.
        """
        if self._cache is None:
            return {
                "cached": False,
                "enabled": self._enabled,
                "hits": self._hit_count,
                "misses": self._miss_count,
            }

        return {
            "cached": True,
            "enabled": self._enabled,
            "tools_digest": self._cache.tools_digest,
            "toggle_enabled": self._cache.toggle_enabled,
            "declarations_set": self._cache.declarations_set,
            "model": self._cache.model_name,
            "age_seconds": round(time.time() - self._cache.timestamp, 2),
            "hits": self._hit_count,
            "misses": self._miss_count,
        }


__all__ = [
    "FunctionCallingCache",
    "FunctionCallingCacheEntry",
]
