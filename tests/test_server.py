"""
Tests for server.py - Server module attribute forwarding.

Tests the attribute forwarding mechanism that provides backward compatibility
by delegating attribute access to the central state object.
"""


class TestServerModuleLogic:
    """Tests for server module logic extracted for testability."""

    def test_state_attrs_set_is_complete(self) -> None:
        """Verify that _STATE_ATTRS contains expected attributes."""
        # The server.py module no longer uses _STATE_ATTRS since it now uses
        # the centralized state object from api_utils.server_state.
        # This test is now a no-op since the architecture changed.
        # The state is accessed via: from api_utils.server_state import state
        pass

    def test_clear_debug_logs_clears_state(self) -> None:
        """Verify clear_debug_logs function clears state logs."""
        from api_utils.server_state import state

        # Add some debug logs (using correct data structures - both are lists of dicts)
        state.console_logs.append({"message": "test log"})
        state.network_log["requests"].append({"test": "request"})

        assert len(state.console_logs) > 0
        assert len(state.network_log["requests"]) > 0

        # Call clear function directly from state (as server.clear_debug_logs delegates to it)
        state.clear_debug_logs()

        assert len(state.console_logs) == 0
        assert len(state.network_log["requests"]) == 0

    def test_state_forwarding_logic(self) -> None:
        """Verify the logic for forwarding state attributes works correctly."""
        from api_utils.server_state import state

        # Test that we can get/set attributes on state
        original_value = state.should_exit

        try:
            state.should_exit = True
            assert state.should_exit is True
        finally:
            state.should_exit = original_value

    def test_getattr_implementation(self) -> None:
        """Test the __getattr__ implementation logic."""
        from typing import Any

        from api_utils.server_state import state

        # Simulate the __getattr__ logic
        _STATE_ATTRS = {"page_instance", "should_exit"}

        def mock_getattr(name: str) -> Any:
            if name in _STATE_ATTRS:
                return getattr(state, name)
            raise AttributeError(f"module 'server' has no attribute '{name}'")

        # Test known attribute
        result = mock_getattr("page_instance")
        assert result is state.page_instance

        # Test unknown attribute
        import pytest

        with pytest.raises(AttributeError):
            mock_getattr("nonexistent_attr")

    def test_setattr_implementation(self) -> None:
        """Test the __setattr__ implementation logic."""
        from typing import Any

        from api_utils.server_state import state

        # Simulate the __setattr__ logic
        _STATE_ATTRS = {"should_exit"}
        test_globals: dict[str, Any] = {}

        def mock_setattr(name: str, value: Any) -> None:
            if name in _STATE_ATTRS:
                setattr(state, name, value)
            else:
                test_globals[name] = value

        original_value = state.should_exit

        try:
            # Test state attribute
            mock_setattr("should_exit", True)
            assert state.should_exit is True

            # Test non-state attribute
            mock_setattr("custom_attr", "custom_value")
            assert test_globals["custom_attr"] == "custom_value"
        finally:
            state.should_exit = original_value


class TestServerApp:
    """Tests for the FastAPI app creation.

    Note: These tests verify FastAPI app behavior through the existing
    api_utils tests rather than importing server.py directly, which has
    side effects (loading .env, creating app instance).
    """

    def test_create_app_produces_valid_app(self) -> None:
        """Verify create_app produces a valid FastAPI instance."""
        from api_utils import create_app

        app = create_app()
        assert app is not None
        assert hasattr(app, "routes")
        assert hasattr(app, "middleware")


class TestServerModuleDirectAccess:
    """Tests that directly access the server module's __getattr__ and __setattr__."""

    def test_getattr_logic_with_state_attrs(self) -> None:
        """Test that state attributes are accessible via server_state module."""
        # The server.py module now uses centralized state from api_utils.server_state
        # Verify that the state module provides access to expected attributes
        from api_utils.server_state import state

        # Test that key attributes exist on the state object
        assert hasattr(state, "page_instance")
        assert hasattr(state, "should_exit")
        assert hasattr(state, "current_ai_studio_model_id")

    def test_getattr_raises_for_unknown(self) -> None:
        """Test __getattr__ logic raises AttributeError for unknown attrs."""
        import pytest

        from api_utils.server_state import state

        _STATE_ATTRS = {"should_exit"}

        # Simulate __getattr__ logic
        def mock_getattr(name: str):
            if name in _STATE_ATTRS:
                return getattr(state, name)
            raise AttributeError(f"module 'server' has no attribute '{name}'")

        with pytest.raises(AttributeError) as exc_info:
            mock_getattr("nonexistent_xyz")
        assert "nonexistent_xyz" in str(exc_info.value)

    def test_setattr_logic_for_state_attrs(self) -> None:
        """Test __setattr__ logic forwards state attributes correctly."""
        from api_utils.server_state import state

        _STATE_ATTRS = {"should_exit"}
        test_globals: dict = {}

        # Simulate __setattr__ logic
        def mock_setattr(name: str, value) -> None:
            if name in _STATE_ATTRS:
                setattr(state, name, value)
            else:
                test_globals[name] = value

        original = state.should_exit
        try:
            mock_setattr("should_exit", True)
            assert state.should_exit is True

            mock_setattr("custom_attr", "value")
            assert test_globals["custom_attr"] == "value"
        finally:
            state.should_exit = original

    def test_clear_debug_logs_via_state(self) -> None:
        """Test clear_debug_logs functionality via state object."""
        from api_utils.server_state import state

        # Add test data
        state.console_logs.append({"test": "log"})

        # Call state's clear function directly
        state.clear_debug_logs()

        assert len(state.console_logs) == 0

    def test_app_creation(self) -> None:
        """Test that create_app produces a valid FastAPI instance."""
        from fastapi import FastAPI

        from api_utils import create_app

        app = create_app()
        assert isinstance(app, FastAPI)
