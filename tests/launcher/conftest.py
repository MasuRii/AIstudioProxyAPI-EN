"""Fixtures for launcher tests."""

import logging
import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True, scope="session")
def _suppress_launcher_logging_session():
    """Suppress CamoufoxLauncher logger during launcher tests (session-scoped).

    The CamoufoxProcessManager.cleanup() method logs extensively during atexit
    cleanup. When tests in this directory instantiate Launcher (which registers
    atexit hooks), the cleanup may run after pytest has finished cleaning up
    fixtures, causing logging errors.

    This session-scoped fixture ensures the logger is suppressed before any
    tests run and restored after the session ends.
    """
    logger = logging.getLogger("CamoufoxLauncher")
    original_level = logger.level
    logger.setLevel(logging.CRITICAL + 1)  # Suppress all logs
    try:
        yield
    finally:
        logger.setLevel(original_level)


@pytest.fixture
def clean_launcher_env():
    """Provide isolated environment for launcher tests.

    Clears all environment variables but preserves LAUNCH_MODE=test
    for consistency with pytest-env global settings.

    Use this when testing argument parsing defaults or environment
    variable handling where you need a clean slate.
    """
    with patch.dict(os.environ, {"LAUNCH_MODE": "test"}, clear=True):
        yield
