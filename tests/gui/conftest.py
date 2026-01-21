"""Fixtures for GUI tests."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_display():
    """Mock display for headless testing.

    This fixture mocks tkinter to avoid display errors in CI/headless environments.
    """
    # Check if we have a display
    if os.environ.get("DISPLAY") or sys.platform == "darwin":
        yield  # Real display available
    else:
        # Mock tkinter for headless
        with patch.dict(
            "sys.modules", {"tkinter": MagicMock(), "tkinter.ttk": MagicMock()}
        ):
            yield


@pytest.fixture
def mock_tk_root():
    """Create a mock Tk root window."""
    mock_root = MagicMock()
    mock_root.winfo_rootx.return_value = 100
    mock_root.winfo_rooty.return_value = 100
    mock_root.winfo_height.return_value = 50
    mock_root.clipboard_clear = MagicMock()
    mock_root.clipboard_append = MagicMock()
    mock_root.update = MagicMock()
    return mock_root


@pytest.fixture
def mock_widget():
    """Create a mock tkinter widget."""
    widget = MagicMock()
    widget.winfo_rootx.return_value = 100
    widget.winfo_rooty.return_value = 100
    widget.winfo_height.return_value = 30
    widget.bind = MagicMock()
    return widget


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file path."""
    return tmp_path / "test_config.json"


@pytest.fixture
def temp_auth_dir(tmp_path):
    """Create temporary auth directories."""
    saved_dir = tmp_path / "auth_profiles" / "saved"
    active_dir = tmp_path / "auth_profiles" / "active"
    saved_dir.mkdir(parents=True)
    active_dir.mkdir(parents=True)
    return {"saved": saved_dir, "active": active_dir}
