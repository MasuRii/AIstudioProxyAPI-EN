"""
Tests for api_utils.model_switching module.

Test Strategy:
- Unit tests: Test model analysis and switching logic individually
- Use REAL asyncio.Lock for model_switching_lock and params_cache_lock
- Use real server_state.state object for state management
- Mock only external boundaries: Browser operations (switch_ai_studio_model)
- Integration tests for concurrent model switches:
  See tests/integration/test_model_switching_concurrency.py

Coverage Target: 90%+
Mock Budget: <35 (down from 82)
"""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api_utils.context_types import RequestContext
from api_utils.model_switching import (
    analyze_model_requirements,
    handle_model_switching,
    handle_parameter_cache,
)
from api_utils.server_state import state

# ==================== Test Classes ====================


class TestAnalyzeModelRequirements:
    """Tests for analyze_model_requirements function."""

    @pytest.mark.asyncio
    async def test_no_requested_model_returns_unchanged_context(
        self, make_request_context
    ):
        """Test that no requested model leaves context unchanged."""
        req_id = "test-req"
        context = make_request_context(
            current_ai_studio_model_id="gemini-1.5-pro",
            parsed_model_list=[
                {"id": "gemini-1.5-pro"},
                {"id": "gemini-1.5-flash"},
            ],
        )
        context["model_id_to_use"] = "gemini-1.5-pro"
        context["needs_model_switching"] = False

        requested_model = ""  # No model requested
        proxy_model_name = "proxy-model"

        result = await analyze_model_requirements(
            req_id, context, requested_model, proxy_model_name
        )

        # Should not modify context when no model requested
        assert "needs_model_switching" not in result or not result.get(
            "needs_model_switching", False
        )

    @pytest.mark.asyncio
    async def test_requested_model_same_as_proxy_no_switch(self, make_request_context):
        """Test that requesting proxy model doesn't trigger switch."""
        req_id = "test-req"
        context = make_request_context(
            current_ai_studio_model_id="gemini-1.5-pro",
            parsed_model_list=[{"id": "gemini-1.5-pro"}],
        )

        requested_model = "proxy-model"
        proxy_model_name = "proxy-model"

        result = await analyze_model_requirements(
            req_id, context, requested_model, proxy_model_name
        )

        # Proxy model should not trigger switch
        assert "needs_model_switching" not in result or not result.get(
            "needs_model_switching", False
        )

    @pytest.mark.asyncio
    async def test_requested_different_valid_model_requires_switch(
        self, make_request_context
    ):
        """Test that valid different model triggers switch requirement."""
        req_id = "test-req"
        context = make_request_context(
            current_ai_studio_model_id="gemini-1.5-pro",
            parsed_model_list=[
                {"id": "gemini-1.5-pro"},
                {"id": "gemini-1.5-flash"},
            ],
        )

        requested_model = "gemini-1.5-flash"
        proxy_model_name = "proxy-model"

        result = await analyze_model_requirements(
            req_id, context, requested_model, proxy_model_name
        )

        # Should flag model switch needed
        assert result.get("needs_model_switching") is True
        assert result["model_id_to_use"] == "gemini-1.5-flash"

    @pytest.mark.asyncio
    async def test_requested_same_model_no_switch(self, make_request_context):
        """Test that requesting current model doesn't trigger switch."""
        req_id = "test-req"
        context = make_request_context(
            current_ai_studio_model_id="gemini-1.5-pro",
            parsed_model_list=[{"id": "gemini-1.5-pro"}],
        )

        requested_model = "gemini-1.5-pro"
        proxy_model_name = "proxy-model"

        result = await analyze_model_requirements(
            req_id, context, requested_model, proxy_model_name
        )

        # Should set model_id but not require switching
        assert result["model_id_to_use"] == "gemini-1.5-pro"
        assert "needs_model_switching" not in result or not result.get(
            "needs_model_switching", False
        )

    @pytest.mark.asyncio
    async def test_invalid_model_raises_bad_request(self, make_request_context):
        """Test that invalid model raises 400 bad request error."""
        req_id = "test-req"
        context = make_request_context(
            current_ai_studio_model_id="gemini-1.5-pro",
            parsed_model_list=[
                {"id": "gemini-1.5-pro"},
                {"id": "gemini-1.5-flash"},
            ],
        )

        requested_model = "invalid-model"
        proxy_model_name = "proxy-model"

        with pytest.raises(HTTPException) as exc:
            await analyze_model_requirements(
                req_id, context, requested_model, proxy_model_name
            )

        assert exc.value.status_code == 400
        assert "Invalid model 'invalid-model'" in exc.value.detail
        assert "gemini-1.5-pro" in exc.value.detail  # Available models listed

    @pytest.mark.asyncio
    async def test_no_parsed_model_list_allows_any_model(self, make_request_context):
        """Test that empty model list skips validation."""
        req_id = "test-req"
        context = make_request_context(
            current_ai_studio_model_id="gemini-1.5-pro",
            parsed_model_list=[],  # Empty list
        )

        requested_model = "any-model"
        proxy_model_name = "proxy-model"

        # Should not raise error when list is empty
        result = await analyze_model_requirements(
            req_id, context, requested_model, proxy_model_name
        )

        assert result["model_id_to_use"] == "any-model"


class TestHandleModelSwitching:
    """Tests for handle_model_switching function."""

    @pytest.mark.asyncio
    async def test_no_switch_needed_returns_immediately(
        self, real_locks_mock_browser, make_request_context
    ):
        """Test that no switch needed skips lock acquisition."""
        req_id = "test-req"
        context = make_request_context(
            model_switching_lock=real_locks_mock_browser.model_switching_lock
        )
        context["needs_model_switching"] = False

        # Lock should not be locked initially
        assert not real_locks_mock_browser.model_switching_lock.locked()

        result = await handle_model_switching(req_id, context)

        # Should return unchanged context
        assert result == context
        # Lock should never have been acquired
        assert not real_locks_mock_browser.model_switching_lock.locked()

    @pytest.mark.asyncio
    async def test_successful_model_switch_updates_state(
        self, real_locks_mock_browser, make_request_context
    ):
        """Test successful model switch updates server state."""
        req_id = "test-req"

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            # Set up initial state
            state.current_ai_studio_model_id = "gemini-1.5-pro"

            context = make_request_context(
                current_ai_studio_model_id="gemini-1.5-pro",
                model_switching_lock=real_locks_mock_browser.model_switching_lock,
            )
            context["needs_model_switching"] = True
            context["model_id_to_use"] = "gemini-1.5-flash"

            # Mock browser switch operation
            with patch(
                "browser_utils.switch_ai_studio_model",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_switch:
                result = await handle_model_switching(req_id, context)

                # Verify browser switch was called
                mock_switch.assert_called_once_with(
                    context["page"], "gemini-1.5-flash", req_id
                )

                # Verify state was updated
                assert state.current_ai_studio_model_id == "gemini-1.5-flash"
                assert result["model_actually_switched"] is True
                assert result["current_ai_studio_model_id"] == "gemini-1.5-flash"

        finally:
            # Restore original state
            state.current_ai_studio_model_id = original_model

    @pytest.mark.asyncio
    async def test_failed_model_switch_reverts_state(
        self, real_locks_mock_browser, make_request_context
    ):
        """Test that failed switch reverts state and raises error."""
        req_id = "test-req"

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            # Set up initial state
            state.current_ai_studio_model_id = "gemini-1.5-pro"

            context = make_request_context(
                current_ai_studio_model_id="gemini-1.5-pro",
                model_switching_lock=real_locks_mock_browser.model_switching_lock,
            )
            context["needs_model_switching"] = True
            context["model_id_to_use"] = "gemini-1.5-flash"

            # Mock browser switch to fail
            with patch(
                "browser_utils.switch_ai_studio_model",
                new_callable=AsyncMock,
                return_value=False,
            ):
                with pytest.raises(HTTPException) as exc:
                    await handle_model_switching(req_id, context)

                # Verify error status and message
                assert exc.value.status_code == 422
                assert "gemini-1.5-flash" in exc.value.detail

                # Verify state was reverted to original
                assert state.current_ai_studio_model_id == "gemini-1.5-pro"

        finally:
            # Restore original state
            state.current_ai_studio_model_id = original_model

    @pytest.mark.asyncio
    async def test_already_switched_model_skips_switch(
        self, real_locks_mock_browser, make_request_context
    ):
        """Test that already-correct model skips switch operation."""
        req_id = "test-req"

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            # State already matches target model
            state.current_ai_studio_model_id = "gemini-1.5-flash"

            context = make_request_context(
                current_ai_studio_model_id="gemini-1.5-flash",
                model_switching_lock=real_locks_mock_browser.model_switching_lock,
            )
            context["needs_model_switching"] = True
            context["model_id_to_use"] = "gemini-1.5-flash"

            with patch(
                "browser_utils.switch_ai_studio_model",
                new_callable=AsyncMock,
            ) as mock_switch:
                result = await handle_model_switching(req_id, context)

                # Should not call browser switch (already correct)
                mock_switch.assert_not_called()

                # Result should not have switched flag
                assert "model_actually_switched" not in result or not result.get(
                    "model_actually_switched", False
                )

        finally:
            # Restore original state
            state.current_ai_studio_model_id = original_model


class TestHandleParameterCache:
    """Tests for handle_parameter_cache function."""

    @pytest.mark.asyncio
    async def test_cache_cleared_when_model_switched(
        self, real_locks_mock_browser, make_request_context
    ):
        """Test that parameter cache is cleared after model switch."""
        req_id = "test-req"

        context = make_request_context(
            current_ai_studio_model_id="gemini-1.5-flash",
            params_cache_lock=real_locks_mock_browser.params_cache_lock,
        )
        context["model_actually_switched"] = True
        context["page_params_cache"] = {
            "temperature": 0.7,
            "max_tokens": 1024,
            "last_known_model_id_for_params": "gemini-1.5-pro",
        }

        await handle_parameter_cache(req_id, context)

        # Cache should be cleared and only new model ID stored
        assert context["page_params_cache"] == {
            "last_known_model_id_for_params": "gemini-1.5-flash"
        }

    @pytest.mark.asyncio
    async def test_cache_cleared_when_model_differs_from_cache(
        self, real_locks_mock_browser, make_request_context
    ):
        """Test cache cleared when current model differs from cached model."""
        req_id = "test-req"

        context = make_request_context(
            current_ai_studio_model_id="gemini-1.5-flash",
            params_cache_lock=real_locks_mock_browser.params_cache_lock,
        )
        context["model_actually_switched"] = False  # Not just switched
        context["page_params_cache"] = {
            "temperature": 0.7,
            "last_known_model_id_for_params": "gemini-1.5-pro",  # Different!
        }

        await handle_parameter_cache(req_id, context)

        # Cache should be cleared because model ID mismatch
        assert context["page_params_cache"] == {
            "last_known_model_id_for_params": "gemini-1.5-flash"
        }

    @pytest.mark.asyncio
    async def test_cache_preserved_when_model_matches(
        self, real_locks_mock_browser, make_request_context
    ):
        """Test cache preserved when model matches cached model."""
        req_id = "test-req"

        context = make_request_context(
            current_ai_studio_model_id="gemini-1.5-pro",
            params_cache_lock=real_locks_mock_browser.params_cache_lock,
        )
        context["model_actually_switched"] = False
        context["page_params_cache"] = {
            "temperature": 0.7,
            "max_tokens": 1024,
            "last_known_model_id_for_params": "gemini-1.5-pro",  # Matches!
        }

        await handle_parameter_cache(req_id, context)

        # Cache should be preserved
        assert context["page_params_cache"]["temperature"] == 0.7
        assert context["page_params_cache"]["max_tokens"] == 1024
        assert (
            context["page_params_cache"]["last_known_model_id_for_params"]
            == "gemini-1.5-pro"
        )

    @pytest.mark.asyncio
    async def test_cache_uses_real_lock(self, real_locks_mock_browser):
        """Test that parameter cache uses real asyncio.Lock."""
        req_id = "test-req"
        lock = real_locks_mock_browser.params_cache_lock

        # Verify lock is real asyncio.Lock
        assert isinstance(lock, asyncio.Lock)
        assert not lock.locked()

        context = cast(
            RequestContext,
            {
                "logger": MagicMock(),
                "params_cache_lock": lock,
                "page_params_cache": {},
                "current_ai_studio_model_id": "gemini-1.5-pro",
                "model_actually_switched": True,
            },
        )

        # Acquire lock externally to test contention
        async with lock:
            # Start cache handling in background
            cache_task = asyncio.create_task(handle_parameter_cache(req_id, context))

            # Give it a moment to try acquiring lock
            await asyncio.sleep(0.01)

            # Lock should still be held by us
            assert lock.locked()

        # Wait for cache task to complete (should acquire lock after we release)
        await cache_task

        # Lock should be released
        assert not lock.locked()
