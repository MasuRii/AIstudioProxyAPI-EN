import os
from unittest.mock import MagicMock, patch

import pytest

from launcher.runner import Launcher


class TestConfigPrecedence:
    """
    Tests to ensure that configuration precedence is correctly handled:
    1. CLI Argument (Explicitly Set) > Environment Variable
    2. Environment Variable > CLI Argument (Default Value)

    This specifically targets the fix where CLI defaults (e.g. False)
    were overwriting .env settings (True).
    """

    @pytest.fixture
    def mock_launcher(self):
        """Creates a Launcher instance with mocked dependencies."""
        with (
            patch("launcher.runner.parse_args") as mock_parse,
            patch("atexit.register"),  # Prevent atexit cleanup hooks from registering
        ):
            # Setup a basic mock args object with defaults
            mock_args = MagicMock()
            # Defaults for boolean flags as defined in argparse (usually False)
            mock_args.auto_save_auth = False
            mock_args.server_redirect_print = False
            mock_args.debug_logs = False
            mock_args.trace_logs = False

            # Track whether CLI flags were explicitly provided (default: not from CLI)
            mock_args.auto_save_auth_from_cli = False
            mock_args.server_redirect_print_from_cli = False
            mock_args.debug_logs_from_cli = False
            mock_args.trace_logs_from_cli = False

            # Application defaults
            mock_args.server_log_level = "INFO"
            mock_args.exit_on_auth_save = False
            mock_args.save_auth_as = None
            mock_args.auth_save_timeout = 30
            mock_args.server_port = 2048
            mock_args.stream_port = 3120
            mock_args.internal_camoufox_proxy = None

            mock_parse.return_value = mock_args

            launcher = Launcher()
            # Partial initialization usually done in run()
            launcher.final_launch_mode = "debug"
            launcher.effective_active_auth_json_path = None
            launcher.simulated_os_for_camoufox = "linux"

            return launcher

    @pytest.mark.parametrize(
        "env_var, cli_arg_attr, env_value, cli_value, expected",
        [
            # AUTO_SAVE_AUTH
            (
                "AUTO_SAVE_AUTH",
                "auto_save_auth",
                "true",
                False,
                "true",
            ),  # Env=True, CLI=Default(False) -> Env wins
            (
                "AUTO_SAVE_AUTH",
                "auto_save_auth",
                "false",
                True,
                "true",
            ),  # Env=False, CLI=Explicit(True) -> CLI wins
            (
                "AUTO_SAVE_AUTH",
                "auto_save_auth",
                "false",
                False,
                "false",
            ),  # Both False -> False
            # SERVER_REDIRECT_PRINT
            ("SERVER_REDIRECT_PRINT", "server_redirect_print", "true", False, "true"),
            ("SERVER_REDIRECT_PRINT", "server_redirect_print", "false", True, "true"),
            ("SERVER_REDIRECT_PRINT", "server_redirect_print", "false", False, "false"),
            # DEBUG_LOGS_ENABLED
            ("DEBUG_LOGS_ENABLED", "debug_logs", "true", False, "true"),
            ("DEBUG_LOGS_ENABLED", "debug_logs", "false", True, "true"),
            ("DEBUG_LOGS_ENABLED", "debug_logs", "false", False, "false"),
            # TRACE_LOGS_ENABLED
            ("TRACE_LOGS_ENABLED", "trace_logs", "true", False, "true"),
            ("TRACE_LOGS_ENABLED", "trace_logs", "false", True, "true"),
            ("TRACE_LOGS_ENABLED", "trace_logs", "false", False, "false"),
        ],
    )
    def test_boolean_flag_precedence(
        self, mock_launcher, env_var, cli_arg_attr, env_value, cli_value, expected
    ):
        """
        Verifies that boolean flags obey the precedence rules.
        """
        # 1. Setup Environment
        with patch.dict(os.environ, {env_var: env_value}, clear=True):
            # 2. Setup CLI Args
            setattr(mock_launcher.args, cli_arg_attr, cli_value)
            # Set the _from_cli flag: True if cli_value is True (explicit), False otherwise (default)
            from_cli_attr = f"{cli_arg_attr}_from_cli"
            setattr(mock_launcher.args, from_cli_attr, cli_value)

            # 3. Execution match
            # We need a dummy ws endpoint for _setup_environment_variables
            mock_launcher._setup_environment_variables("ws://test")

            # 4. Assertion
            assert os.environ.get(env_var) == expected, (
                f"Failed for {env_var}: Env={env_value}, CLI={cli_value}. Expected {expected} but got {os.environ.get(env_var)}"
            )

    def test_auto_save_auth_default_persistence(self, mock_launcher):
        """Specific test to ensure AUTO_SAVE_AUTH persists correctly when only in env."""
        with patch.dict(os.environ, {"AUTO_SAVE_AUTH": "true"}, clear=True):
            mock_launcher.args.auto_save_auth = False  # CLI default

            mock_launcher._setup_environment_variables("ws://dummy")

            assert os.environ["AUTO_SAVE_AUTH"] == "true"

    def test_cli_override(self, mock_launcher):
        """Specific test to ensure CLI True overrides Env False."""
        with patch.dict(os.environ, {"AUTO_SAVE_AUTH": "false"}, clear=True):
            mock_launcher.args.auto_save_auth = True  # CLI Explicit True
            mock_launcher.args.auto_save_auth_from_cli = True

            mock_launcher._setup_environment_variables("ws://dummy")

            assert os.environ["AUTO_SAVE_AUTH"] == "true"
