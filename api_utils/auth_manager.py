import asyncio
import glob
import logging
import os
from typing import List, Optional, Set

from launcher.config import SAVED_AUTH_DIR

logger = logging.getLogger("AuthManager")


class AuthManager:
    """
    Manages authentication profiles for rotation and error recovery.
    """

    def __init__(self) -> None:
        self.failed_profiles: Set[str] = set()
        self.current_profile: Optional[str] = None

        # Initialize with the profile from environment if available
        initial_profile = os.environ.get("ACTIVE_AUTH_JSON_PATH")
        if initial_profile:
            self.current_profile = initial_profile

    async def get_available_profiles(self) -> List[str]:
        """List all .json files in the saved auth directory."""
        if not os.path.exists(SAVED_AUTH_DIR):
            logger.warning(f"Saved auth directory not found: {SAVED_AUTH_DIR}")
            return []

        loop = asyncio.get_running_loop()
        pattern = os.path.join(SAVED_AUTH_DIR, "*.json")
        # Run glob in executor to avoid blocking the event loop
        profiles = await loop.run_in_executor(None, glob.glob, pattern)
        return sorted(profiles)  # Sort for deterministic order

    async def get_next_profile(self) -> str:
        """
        Get the next available profile that hasn't failed yet.
        Raises RuntimeError if no profiles are available.
        """
        profiles = await self.get_available_profiles()

        # 获取已失败配置文件的 basename 集合 (避免路径差异导致的重复)
        failed_basenames = {os.path.basename(p) for p in self.failed_profiles}
        current_basename = (
            os.path.basename(self.current_profile) if self.current_profile else None
        )

        # Filter out failed profiles by basename comparison
        available = [
            p
            for p in profiles
            if os.path.basename(p) not in failed_basenames
            and os.path.basename(p) != current_basename  # 也排除当前配置文件
        ]

        if not available:
            msg = f"All authentication profiles exhausted. Failed: {len(self.failed_profiles)}, Total: {len(profiles)}"
            logger.critical(msg)
            raise RuntimeError(msg)

        # Simple strategy: Pick the first available one.
        next_profile = available[0]
        self.current_profile = next_profile
        logger.info(f"Switched to auth profile: {os.path.basename(next_profile)}")
        return next_profile

    def mark_profile_failed(self, profile_path: Optional[str] = None) -> None:
        """Mark a profile as failed so it won't be used again in this cycle."""
        target = profile_path or self.current_profile
        if target:
            self.failed_profiles.add(target)
            logger.warning(f"Marked auth profile as failed: {os.path.basename(target)}")
        else:
            logger.warning(
                "Attempted to mark profile failed but no profile provided or active."
            )


# Global instance
auth_manager = AuthManager()
