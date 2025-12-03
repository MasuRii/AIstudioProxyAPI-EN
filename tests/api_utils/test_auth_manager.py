import os
from unittest.mock import AsyncMock, patch

import pytest

from api_utils.auth_manager import AuthManager, auth_manager

# --- Fixtures ---


@pytest.fixture
def manager():
    return AuthManager()


@pytest.fixture
def mock_saved_auth_dir(tmp_path):
    """Mock the SAVED_AUTH_DIR constant."""
    with patch("api_utils.auth_manager.SAVED_AUTH_DIR", str(tmp_path)):
        yield tmp_path


# --- Tests ---


def test_init_default():
    """Test initialization without environment variable."""
    with patch.dict(os.environ, {}, clear=True):
        am = AuthManager()
        assert am.current_profile is None
        assert am.failed_profiles == set()


def test_init_with_env_var():
    """Test initialization with ACTIVE_AUTH_JSON_PATH."""
    with patch.dict(os.environ, {"ACTIVE_AUTH_JSON_PATH": "/path/to/auth.json"}):
        am = AuthManager()
        assert am.current_profile == "/path/to/auth.json"


@pytest.mark.asyncio
async def test_get_available_profiles_no_dir(manager):
    """Test get_available_profiles when directory doesn't exist."""
    with patch("os.path.exists", return_value=False):
        profiles = await manager.get_available_profiles()
        assert profiles == []


@pytest.mark.asyncio
async def test_get_available_profiles_success(manager, mock_saved_auth_dir):
    """Test get_available_profiles with existing files."""
    # Create dummy auth files
    (mock_saved_auth_dir / "auth1.json").touch()
    (mock_saved_auth_dir / "auth2.json").touch()

    with patch("os.path.exists", return_value=True):
        profiles = await manager.get_available_profiles()

    assert len(profiles) == 2
    assert any("auth1.json" in p for p in profiles)
    assert any("auth2.json" in p for p in profiles)
    # Check sorting
    assert profiles == sorted(profiles)


@pytest.mark.asyncio
async def test_get_next_profile_success(manager):
    """Test getting next profile successfully."""
    mock_profiles = ["/dir/auth1.json", "/dir/auth2.json"]

    with patch.object(
        manager, "get_available_profiles", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_profiles

        # First call
        next_p = await manager.get_next_profile()
        assert next_p == "/dir/auth1.json"
        assert manager.current_profile == "/dir/auth1.json"


@pytest.mark.asyncio
async def test_get_next_profile_skips_failed(manager):
    """Test that failed profiles are skipped."""
    mock_profiles = ["/dir/auth1.json", "/dir/auth2.json", "/dir/auth3.json"]
    manager.failed_profiles.add("/dir/auth1.json")

    with patch.object(
        manager, "get_available_profiles", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_profiles

        next_p = await manager.get_next_profile()
        assert next_p == "/dir/auth2.json"

        # Mark auth2 as failed and try again
        manager.mark_profile_failed()  # marks current (auth2)

        next_p_2 = await manager.get_next_profile()
        assert next_p_2 == "/dir/auth3.json"


@pytest.mark.asyncio
async def test_get_next_profile_skips_current(manager):
    """Test that current profile is skipped even if not failed (to ensure rotation if needed, or just behavior check)."""
    # Actually logic says: os.path.basename(p) != current_basename
    # So if we call get_next_profile, it should give us a *different* one if available.

    mock_profiles = ["/dir/auth1.json", "/dir/auth2.json"]
    manager.current_profile = "/dir/auth1.json"

    with patch.object(
        manager, "get_available_profiles", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_profiles

        next_p = await manager.get_next_profile()
        assert next_p == "/dir/auth2.json"


@pytest.mark.asyncio
async def test_get_next_profile_exhausted(manager):
    """Test raising RuntimeError when no profiles available."""
    with patch.object(
        manager, "get_available_profiles", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = []

        with pytest.raises(RuntimeError, match="All authentication profiles exhausted"):
            await manager.get_next_profile()


@pytest.mark.asyncio
async def test_get_next_profile_all_failed(manager):
    """Test raising RuntimeError when all profiles failed."""
    mock_profiles = ["/dir/auth1.json"]
    manager.failed_profiles.add("/dir/auth1.json")

    with patch.object(
        manager, "get_available_profiles", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_profiles

        with pytest.raises(RuntimeError, match="All authentication profiles exhausted"):
            await manager.get_next_profile()


def test_mark_profile_failed(manager):
    """Test marking profile as failed."""
    # 1. With explicit path
    manager.mark_profile_failed("/dir/auth1.json")
    assert "/dir/auth1.json" in manager.failed_profiles

    # 2. With current profile
    manager.current_profile = "/dir/auth2.json"
    manager.mark_profile_failed()
    assert "/dir/auth2.json" in manager.failed_profiles

    # 3. No profile active and no arg
    manager.current_profile = None
    manager.mark_profile_failed()  # Should log warning but not crash
    # (Assert log if needed, but no crash is enough for basic coverage)


def test_reset_failures(manager):
    """Test resetting failures."""
    manager.failed_profiles.add("test")
    manager.reset_failures()
    assert len(manager.failed_profiles) == 0


def test_global_instance():
    """Ensure global instance exists."""
    assert isinstance(auth_manager, AuthManager)
