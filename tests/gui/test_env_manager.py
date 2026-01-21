"""
Tests for gui/env_manager.py - Environment file management
"""

import os
import tempfile
from pathlib import Path

import pytest

from gui.env_manager import EnvManager, get_env_manager, reset_env_manager


@pytest.fixture
def temp_env_file():
    """Create a temporary .env file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("""# Test configuration
PORT=2048
STREAM_PORT=3120
DEBUG_LOGS_ENABLED=true
DEFAULT_TEMPERATURE=1.0
SERVER_LOG_LEVEL=INFO
FUNCTION_CALLING_MODE=auto
""")
        f.flush()
        yield Path(f.name)
    os.unlink(f.name)


@pytest.fixture
def temp_example_file():
    """Create a temporary .env.example file for testing."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env.example", delete=False
    ) as f:
        f.write("""# Example configuration
PORT=2048
STREAM_PORT=3120
""")
        f.flush()
        yield Path(f.name)
    os.unlink(f.name)


@pytest.fixture
def env_manager(temp_env_file, temp_example_file):
    """Create an EnvManager instance for testing."""
    reset_env_manager()
    return EnvManager(temp_env_file, temp_example_file)


class TestEnvManagerInit:
    """Tests for EnvManager initialization."""

    def test_loads_existing_file(self, env_manager):
        """Test that EnvManager loads existing .env file."""
        assert env_manager.get("PORT") == 2048

    def test_creates_from_example_if_missing(self, temp_example_file):
        """Test creating .env from .env.example if missing."""
        reset_env_manager()
        missing_path = Path(tempfile.gettempdir()) / "nonexistent_test.env"
        if missing_path.exists():
            missing_path.unlink()

        manager = EnvManager(missing_path, temp_example_file)
        assert missing_path.exists()
        assert manager.get("PORT") == 2048
        missing_path.unlink()


class TestEnvManagerGet:
    """Tests for EnvManager.get() method."""

    def test_get_int_value(self, env_manager):
        """Test getting integer values."""
        assert env_manager.get("PORT") == 2048
        assert isinstance(env_manager.get("PORT"), int)

    def test_get_bool_value(self, env_manager):
        """Test getting boolean values."""
        assert env_manager.get("DEBUG_LOGS_ENABLED") is True
        assert isinstance(env_manager.get("DEBUG_LOGS_ENABLED"), bool)

    def test_get_float_value(self, env_manager):
        """Test getting float values."""
        assert env_manager.get("DEFAULT_TEMPERATURE") == 1.0
        assert isinstance(env_manager.get("DEFAULT_TEMPERATURE"), float)

    def test_get_string_value(self, env_manager):
        """Test getting string values."""
        assert env_manager.get("SERVER_LOG_LEVEL") == "INFO"
        assert isinstance(env_manager.get("SERVER_LOG_LEVEL"), str)

    def test_get_choice_value(self, env_manager):
        """Test getting choice values."""
        assert env_manager.get("FUNCTION_CALLING_MODE") == "auto"

    def test_get_missing_returns_default(self, env_manager):
        """Test that missing keys return schema default."""
        # QUOTA_SOFT_LIMIT is in schema but not in our test file
        assert env_manager.get("QUOTA_SOFT_LIMIT") == 850000

    def test_get_raw_value(self, env_manager):
        """Test getting raw string value."""
        raw = env_manager.get_raw("DEBUG_LOGS_ENABLED")
        assert raw == "true"
        assert isinstance(raw, str)


class TestEnvManagerSet:
    """Tests for EnvManager.set() method."""

    def test_set_int_value(self, env_manager):
        """Test setting integer values."""
        env_manager.set("PORT", 3000)
        assert env_manager.get("PORT") == 3000

    def test_set_bool_value(self, env_manager):
        """Test setting boolean values."""
        env_manager.set("DEBUG_LOGS_ENABLED", False)
        assert env_manager.get("DEBUG_LOGS_ENABLED") is False

    def test_set_float_value(self, env_manager):
        """Test setting float values."""
        env_manager.set("DEFAULT_TEMPERATURE", 0.7)
        assert env_manager.get("DEFAULT_TEMPERATURE") == 0.7


class TestEnvManagerDirtyState:
    """Tests for dirty state tracking."""

    def test_initially_not_dirty(self, env_manager):
        """Test that newly loaded manager is not dirty."""
        assert env_manager.is_dirty() is False

    def test_dirty_after_set(self, env_manager):
        """Test that manager becomes dirty after setting a value."""
        env_manager.set("PORT", 9999)
        assert env_manager.is_dirty() is True

    def test_get_modified_keys(self, env_manager):
        """Test getting list of modified keys."""
        env_manager.set("PORT", 9999)
        env_manager.set("STREAM_PORT", 8888)
        modified = env_manager.get_modified_keys()
        assert "PORT" in modified
        assert "STREAM_PORT" in modified


class TestEnvManagerSave:
    """Tests for saving .env file."""

    def test_save_writes_file(self, env_manager, temp_env_file):
        """Test that save writes to file."""
        env_manager.set("PORT", 5000)
        assert env_manager.save() is True

        # Re-read the file
        with open(temp_env_file) as f:
            content = f.read()
        assert "PORT=5000" in content

    def test_save_clears_dirty_state(self, env_manager):
        """Test that save clears dirty state."""
        env_manager.set("PORT", 5000)
        assert env_manager.is_dirty() is True
        env_manager.save()
        assert env_manager.is_dirty() is False


class TestEnvManagerCategories:
    """Tests for category handling."""

    def test_get_category_keys(self, env_manager):
        """Test getting keys by category."""
        server_keys = env_manager.get_category_keys("server")
        assert "PORT" in server_keys
        assert "STREAM_PORT" in server_keys

    def test_get_schema_info(self, env_manager):
        """Test getting schema info for a key."""
        info = env_manager.get_schema_info("PORT")
        assert info is not None
        default, type_hint, description, category = info
        assert default == 2048
        assert type_hint == "int"
        assert category == "server"

    def test_categories_dict_exists(self, env_manager):
        """Test that CATEGORIES dict is defined."""
        assert len(EnvManager.CATEGORIES) > 0
        assert "server" in EnvManager.CATEGORIES
        assert "logging" in EnvManager.CATEGORIES


class TestEnvManagerHotReload:
    """Tests for hot reload functionality."""

    def test_register_callback(self, env_manager):
        """Test registering hot reload callback."""
        callback_called = []

        def callback(modified):
            callback_called.append(modified)

        env_manager.register_hot_reload_callback(callback)
        env_manager.set("PORT", 9999)
        env_manager.trigger_hot_reload()

        assert len(callback_called) == 1
        assert "PORT" in callback_called[0]

    def test_unregister_callback(self, env_manager):
        """Test unregistering hot reload callback."""
        callback_called = []

        def callback(modified):
            callback_called.append(modified)

        env_manager.register_hot_reload_callback(callback)
        env_manager.unregister_hot_reload_callback(callback)
        env_manager.set("PORT", 9999)
        env_manager.trigger_hot_reload()

        assert len(callback_called) == 0

    def test_apply_to_environment(self, env_manager):
        """Test applying settings to os.environ."""
        env_manager.set("PORT", 7777)
        env_manager.apply_to_environment()
        assert os.environ.get("PORT") == "7777"


class TestEnvManagerReset:
    """Tests for reset functionality."""

    def test_reset_to_defaults(self, env_manager):
        """Test resetting all values to defaults."""
        env_manager.set("PORT", 9999)
        env_manager.reset_to_defaults()
        assert env_manager.get("PORT") == 2048

    def test_discard_changes(self, env_manager):
        """Test discarding unsaved changes."""
        original = env_manager.get("PORT")
        env_manager.set("PORT", 9999)
        env_manager.discard_changes()
        assert env_manager.get("PORT") == original


class TestGetEnvManagerSingleton:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self, temp_env_file, temp_example_file):
        """Test that get_env_manager returns singleton."""
        reset_env_manager()
        manager1 = get_env_manager(temp_env_file, temp_example_file)
        manager2 = get_env_manager()
        assert manager1 is manager2

    def test_reset_clears_singleton(self, temp_env_file, temp_example_file):
        """Test that reset_env_manager clears singleton."""
        reset_env_manager()
        manager1 = get_env_manager(temp_env_file, temp_example_file)
        reset_env_manager()
        manager2 = get_env_manager(temp_env_file, temp_example_file)
        assert manager1 is not manager2
