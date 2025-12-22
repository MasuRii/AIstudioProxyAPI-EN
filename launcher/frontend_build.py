"""
Frontend build utilities for the launcher.

Provides automatic detection and rebuild of stale frontend assets.
"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("CamoufoxLauncher")

# Paths relative to project root
_PROJECT_ROOT = Path(__file__).parent.parent
_FRONTEND_DIR = _PROJECT_ROOT / "static" / "frontend"
_FRONTEND_SRC = _FRONTEND_DIR / "src"
_FRONTEND_DIST = _FRONTEND_DIR / "dist"


def _get_latest_mtime(
    directory: Path, extensions: tuple[str, ...] = (".ts", ".tsx", ".css")
) -> float:
    """Get the latest modification time of source files in a directory."""
    latest_mtime = 0.0
    if not directory.exists():
        return latest_mtime

    for file_path in directory.rglob("*"):
        if file_path.is_file() and file_path.suffix in extensions:
            try:
                mtime = file_path.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
            except OSError:
                pass
    return latest_mtime


def _get_dist_mtime() -> float:
    """Get the modification time of the dist/index.html."""
    index_html = _FRONTEND_DIST / "index.html"
    if index_html.exists():
        try:
            return index_html.stat().st_mtime
        except OSError:
            pass
    return 0.0


def is_frontend_stale() -> bool:
    """Check if frontend needs to be rebuilt."""
    if not _FRONTEND_DIST.exists():
        return True

    src_mtime = _get_latest_mtime(_FRONTEND_SRC)
    dist_mtime = _get_dist_mtime()

    if src_mtime == 0.0:
        # No source files found, don't rebuild
        return False

    return src_mtime > dist_mtime


def check_npm_available() -> bool:
    """Check if npm is available."""
    return shutil.which("npm") is not None


def rebuild_frontend() -> bool:
    """
    Rebuild the frontend.

    Returns:
        True if build succeeded, False otherwise.
    """
    if not _FRONTEND_DIR.exists():
        logger.warning(f"Frontend directory not found: {_FRONTEND_DIR}")
        return False

    if not check_npm_available():
        logger.warning("npm not installed, skipping frontend rebuild")
        return False

    # Check if node_modules exists
    if not (_FRONTEND_DIR / "node_modules").exists():
        logger.info("[Build] Installing frontend dependencies...")
        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(_FRONTEND_DIR),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.error(f"npm install failed: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.error("npm install timed out")
            return False
        except Exception as e:
            logger.error(f"npm install error: {e}")
            return False

    logger.info("[Build] Building frontend...")
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(_FRONTEND_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("[Build] Frontend build succeeded")
            return True
        else:
            # TypeScript errors go to stdout, other errors to stderr
            error_output = result.stdout.strip() or result.stderr.strip()
            if error_output:
                # Truncate long error messages for readability
                if len(error_output) > 500:
                    error_output = error_output[:500] + "\n... (truncated)"
                logger.error(f"Frontend build failed:\n{error_output}")
            else:
                logger.error(f"Frontend build failed (exit code: {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        logger.error("Frontend build timed out")
        return False
    except Exception as e:
        logger.error(f"Frontend build error: {e}")
        return False


def ensure_frontend_built(skip_build: bool = False) -> None:
    """
    Ensure frontend is built and up-to-date.

    Automatically rebuilds if source files are newer than dist.

    Args:
        skip_build: If True, skip all build checks.
                   Can also be skipped by setting environment variable SKIP_FRONTEND_BUILD=1.
    """
    import os

    # Check for skip flag from argument or environment
    if skip_build or os.environ.get("SKIP_FRONTEND_BUILD", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        logger.info("[Build] Skipping frontend build check (SKIP_FRONTEND_BUILD)")
        return

    if not _FRONTEND_SRC.exists():
        logger.debug(
            "[Build] Frontend source directory not found, skipping build check"
        )
        return

    if is_frontend_stale():
        logger.info("[Build] Detected frontend source file updates, rebuilding...")
        rebuild_frontend()
    else:
        logger.info("[Build] Frontend is up-to-date")
