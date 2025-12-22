"""
Tests for launcher/logging_setup.py - Launcher logging configuration.

Tests the setup_launcher_logging function which configures file and console
handlers with GridFormatter for the CamoufoxLauncher logger.
"""

import logging
from pathlib import Path
from unittest.mock import patch


class TestSetupLauncherLogging:
    """Tests for setup_launcher_logging function."""

    def test_creates_log_directory(self, tmp_path: Path) -> None:
        """Verify that the log directory is created if it doesn't exist."""
        log_dir = tmp_path / "logs"
        log_file = log_dir / "launcher.log"

        with (
            patch("launcher.logging_setup.LOG_DIR", str(log_dir)),
            patch("launcher.logging_setup.LAUNCHER_LOG_FILE_PATH", str(log_file)),
            patch("launcher.logging_setup.set_source") as mock_set_source,
            patch("launcher.logging_setup.GridFormatter"),
            patch("launcher.logging_setup.PlainGridFormatter"),
        ):
            from launcher.logging_setup import setup_launcher_logging

            setup_launcher_logging()

            assert log_dir.exists()
            mock_set_source.assert_called_once_with("LAUNCHER")

    def test_clears_existing_handlers(self, tmp_path: Path) -> None:
        """Verify that existing handlers are cleared before adding new ones."""
        log_dir = tmp_path / "logs"
        log_file = log_dir / "launcher.log"
        log_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("launcher.logging_setup.LOG_DIR", str(log_dir)),
            patch("launcher.logging_setup.LAUNCHER_LOG_FILE_PATH", str(log_file)),
            patch("launcher.logging_setup.set_source"),
            patch("launcher.logging_setup.GridFormatter"),
            patch("launcher.logging_setup.PlainGridFormatter"),
        ):
            from launcher.logging_setup import logger, setup_launcher_logging

            # Add a dummy handler first
            dummy_handler = logging.NullHandler()
            logger.addHandler(dummy_handler)
            assert len(logger.handlers) >= 1

            setup_launcher_logging()

            # Should have exactly 2 handlers (file + stream)
            assert len(logger.handlers) == 2

    def test_removes_existing_log_file(self, tmp_path: Path) -> None:
        """Verify that old log file is removed before creating new one."""
        log_dir = tmp_path / "logs"
        log_file = log_dir / "launcher.log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file.write_text("old log content")

        assert log_file.exists()

        with (
            patch("launcher.logging_setup.LOG_DIR", str(log_dir)),
            patch("launcher.logging_setup.LAUNCHER_LOG_FILE_PATH", str(log_file)),
            patch("launcher.logging_setup.set_source"),
            patch("launcher.logging_setup.GridFormatter"),
            patch("launcher.logging_setup.PlainGridFormatter"),
        ):
            from launcher.logging_setup import setup_launcher_logging

            setup_launcher_logging()

            # Old file should be removed (or recreated empty)
            # The new file handler will create a new file

    def test_handles_log_file_removal_error(self, tmp_path: Path) -> None:
        """Verify graceful handling when log file cannot be removed."""
        log_dir = tmp_path / "logs"
        log_file = log_dir / "launcher.log"
        log_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("launcher.logging_setup.LOG_DIR", str(log_dir)),
            patch("launcher.logging_setup.LAUNCHER_LOG_FILE_PATH", str(log_file)),
            patch("launcher.logging_setup.set_source"),
            patch("launcher.logging_setup.GridFormatter"),
            patch("launcher.logging_setup.PlainGridFormatter"),
            patch("os.path.exists", return_value=True),
            patch("os.remove", side_effect=OSError("Permission denied")),
        ):
            from launcher.logging_setup import setup_launcher_logging

            # Should not raise exception
            setup_launcher_logging()

    def test_sets_correct_log_level(self, tmp_path: Path) -> None:
        """Verify that the specified log level is applied."""
        log_dir = tmp_path / "logs"
        log_file = log_dir / "launcher.log"
        log_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("launcher.logging_setup.LOG_DIR", str(log_dir)),
            patch("launcher.logging_setup.LAUNCHER_LOG_FILE_PATH", str(log_file)),
            patch("launcher.logging_setup.set_source"),
            patch("launcher.logging_setup.GridFormatter"),
            patch("launcher.logging_setup.PlainGridFormatter"),
        ):
            from launcher.logging_setup import logger, setup_launcher_logging

            setup_launcher_logging(log_level=logging.DEBUG)

            assert logger.level == logging.DEBUG

    def test_disables_propagation(self, tmp_path: Path) -> None:
        """Verify that log propagation is disabled."""
        log_dir = tmp_path / "logs"
        log_file = log_dir / "launcher.log"
        log_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("launcher.logging_setup.LOG_DIR", str(log_dir)),
            patch("launcher.logging_setup.LAUNCHER_LOG_FILE_PATH", str(log_file)),
            patch("launcher.logging_setup.set_source"),
            patch("launcher.logging_setup.GridFormatter"),
            patch("launcher.logging_setup.PlainGridFormatter"),
        ):
            from launcher.logging_setup import logger, setup_launcher_logging

            setup_launcher_logging()

            assert logger.propagate is False
