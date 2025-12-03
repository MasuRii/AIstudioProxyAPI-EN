"""
Integration tests for concurrent model switching with real locks.

These tests use REAL asyncio.Lock to verify that concurrent model switch requests
are properly serialized and don't cause race conditions or state corruption.

Test Strategy:
- Use real_server_state fixture (real asyncio.Lock for model_switching_lock)
- Test concurrent requests trying to switch to different models
- Verify lock prevents concurrent switches
- Verify state remains consistent
- Test lock hierarchy (processing_lock > model_switching_lock)

Coverage Target: Concurrent model switching integrity
"""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api_utils.context_types import RequestContext
from api_utils.model_switching import handle_model_switching
from api_utils.server_state import state


@pytest.mark.integration
class TestConcurrentModelSwitching:
    """Integration tests for concurrent model switching with real locks."""

    async def test_concurrent_switches_are_serialized(self, real_server_state):
        """
        Test that concurrent model switch requests are serialized by lock.

        Verifies that the model_switching_lock prevents concurrent browser operations.
        """
        lock = real_server_state.model_switching_lock
        execution_log = []

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            state.current_ai_studio_model_id = "gemini-1.5-pro"

            async def mock_browser_switch(page, model_id, req_id):
                """Mock browser switch that logs and simulates work."""
                execution_log.append(f"{req_id}_browser_start")
                await asyncio.sleep(0.05)  # Simulate browser operation
                execution_log.append(f"{req_id}_browser_done")
                return True

            async def switch_with_logging(req_id: str, target_model: str):
                """Switch model and log execution order."""
                execution_log.append(f"{req_id}_wait_lock")

                context = cast(
                    RequestContext,
                    {
                        "req_id": req_id,
                        "logger": MagicMock(),
                        "page": real_server_state.page_instance,
                        "model_switching_lock": lock,
                        "needs_model_switching": True,
                        "model_id_to_use": target_model,
                        "current_ai_studio_model_id": state.current_ai_studio_model_id,
                    },
                )

                await handle_model_switching(req_id, context)
                execution_log.append(f"{req_id}_complete")

            # Start 3 concurrent switches with mock applied
            with patch(
                "browser_utils.switch_ai_studio_model",
                new_callable=AsyncMock,
                side_effect=mock_browser_switch,
            ):
                tasks = [
                    asyncio.create_task(
                        switch_with_logging("req1", "gemini-1.5-flash")
                    ),
                    asyncio.create_task(
                        switch_with_logging("req2", "gemini-2.0-flash")
                    ),
                    asyncio.create_task(switch_with_logging("req3", "gemini-1.5-pro")),
                ]

                await asyncio.gather(*tasks)

            # Verify serialization: no overlapping browser operations
            # Find all browser_start and browser_done pairs
            browser_starts = [
                i for i, e in enumerate(execution_log) if "browser_start" in e
            ]
            browser_dones = [
                i for i, e in enumerate(execution_log) if "browser_done" in e
            ]

            # Each done must come before the next start (no overlap)
            for i in range(len(browser_starts) - 1):
                assert browser_dones[i] < browser_starts[i + 1], (
                    f"Browser operations overlapped: "
                    f"{execution_log[browser_starts[i]]} started but "
                    f"{execution_log[browser_starts[i + 1]]} started before it finished"
                )

        finally:
            state.current_ai_studio_model_id = original_model

    async def test_state_consistency_under_concurrent_switches(self, real_server_state):
        """
        Test that server state remains consistent during concurrent switches.

        Verify the last successful switch determines final state.
        """
        lock = real_server_state.model_switching_lock

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            state.current_ai_studio_model_id = "gemini-1.5-pro"
            final_states = []

            async def switch_and_record(model_id: str, req_id: str):
                """Switch model and record final state."""
                context = cast(
                    RequestContext,
                    {
                        "req_id": req_id,
                        "logger": MagicMock(),
                        "page": real_server_state.page_instance,
                        "model_switching_lock": lock,
                        "needs_model_switching": True,
                        "model_id_to_use": model_id,
                        "current_ai_studio_model_id": state.current_ai_studio_model_id,
                    },
                )

                with patch(
                    "browser_utils.switch_ai_studio_model",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    result = await handle_model_switching(req_id, context)
                    # Record state after switch
                    final_states.append(
                        (req_id, state.current_ai_studio_model_id, result)
                    )

            # Launch 3 concurrent switches
            tasks = [
                asyncio.create_task(switch_and_record("gemini-1.5-flash", "req1")),
                asyncio.create_task(switch_and_record("gemini-2.0-flash", "req2")),
                asyncio.create_task(switch_and_record("gemini-1.5-pro", "req3")),
            ]

            await asyncio.gather(*tasks)

            # All switches should have recorded a state
            assert len(final_states) == 3

            # Final state should match the last switch that completed
            last_req_id, last_state, last_result = final_states[-1]
            assert (
                state.current_ai_studio_model_id
                == last_result["current_ai_studio_model_id"]
            )

        finally:
            state.current_ai_studio_model_id = original_model

    async def test_failed_switch_doesnt_corrupt_state(self, real_server_state):
        """
        Test that failed switch doesn't leave state in inconsistent state.

        Failed switches should revert state properly.
        """
        lock = real_server_state.model_switching_lock

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            state.current_ai_studio_model_id = "gemini-1.5-pro"

            context = cast(
                RequestContext,
                {
                    "req_id": "req1",
                    "logger": MagicMock(),
                    "page": real_server_state.page_instance,
                    "model_switching_lock": lock,
                    "needs_model_switching": True,
                    "model_id_to_use": "gemini-1.5-flash",
                    "current_ai_studio_model_id": "gemini-1.5-pro",
                },
            )

            # Mock browser switch to fail
            with patch(
                "browser_utils.switch_ai_studio_model",
                new_callable=AsyncMock,
                return_value=False,
            ):
                with pytest.raises(HTTPException):
                    await handle_model_switching("req1", context)

            # State should be reverted to original
            assert state.current_ai_studio_model_id == "gemini-1.5-pro"

            # Now try successful switch
            context["req_id"] = "req2"
            context["model_id_to_use"] = "gemini-2.0-flash"
            with patch(
                "browser_utils.switch_ai_studio_model",
                new_callable=AsyncMock,
                return_value=True,
            ):
                await handle_model_switching("req2", context)

            # State should now be updated to successful switch
            assert state.current_ai_studio_model_id == "gemini-2.0-flash"

        finally:
            state.current_ai_studio_model_id = original_model


@pytest.mark.integration
class TestLockHierarchy:
    """Tests for lock hierarchy between processing_lock and model_switching_lock."""

    async def test_model_switch_can_occur_inside_processing_lock(
        self, real_server_state
    ):
        """
        Test that model_switching_lock can be acquired inside processing_lock.

        Verifies lock hierarchy: processing_lock > model_switching_lock
        """
        processing_lock = real_server_state.processing_lock
        model_switching_lock = real_server_state.model_switching_lock

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            state.current_ai_studio_model_id = "gemini-1.5-pro"

            acquired_processing = False
            acquired_model_switching = False

            async with processing_lock:
                acquired_processing = True
                assert processing_lock.locked()

                # Should be able to acquire model_switching_lock inside
                context = cast(
                    RequestContext,
                    {
                        "req_id": "req1",
                        "logger": MagicMock(),
                        "page": real_server_state.page_instance,
                        "model_switching_lock": model_switching_lock,
                        "needs_model_switching": True,
                        "model_id_to_use": "gemini-1.5-flash",
                        "current_ai_studio_model_id": "gemini-1.5-pro",
                    },
                )

                with patch(
                    "browser_utils.switch_ai_studio_model",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    await handle_model_switching("req1", context)
                    acquired_model_switching = True

            # Both locks should have been acquired
            assert acquired_processing
            assert acquired_model_switching

            # Both should be released now
            assert not processing_lock.locked()
            assert not model_switching_lock.locked()

        finally:
            state.current_ai_studio_model_id = original_model

    async def test_concurrent_processing_and_model_switching(self, real_server_state):
        """
        Test that processing_lock prevents concurrent model switches.

        Multiple processing tasks with model switches should be serialized.
        """
        processing_lock = real_server_state.processing_lock
        model_switching_lock = real_server_state.model_switching_lock
        execution_log = []

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            state.current_ai_studio_model_id = "gemini-1.5-pro"

            async def process_with_switch(req_id: str, target_model: str):
                """Simulate request processing with model switch."""
                execution_log.append(f"{req_id}_wait_processing")

                async with processing_lock:
                    execution_log.append(f"{req_id}_acquired_processing")

                    context = cast(
                        RequestContext,
                        {
                            "req_id": req_id,
                            "logger": MagicMock(),
                            "page": real_server_state.page_instance,
                            "model_switching_lock": model_switching_lock,
                            "needs_model_switching": True,
                            "model_id_to_use": target_model,
                            "current_ai_studio_model_id": state.current_ai_studio_model_id,
                        },
                    )

                    execution_log.append(f"{req_id}_wait_model_switch")

                    with patch(
                        "browser_utils.switch_ai_studio_model",
                        new_callable=AsyncMock,
                        return_value=True,
                    ):
                        await handle_model_switching(req_id, context)

                    execution_log.append(f"{req_id}_completed")

            # Start two concurrent requests with model switches
            task1 = asyncio.create_task(process_with_switch("req1", "gemini-1.5-flash"))
            task2 = asyncio.create_task(process_with_switch("req2", "gemini-2.0-flash"))

            await asyncio.gather(task1, task2)

            # Verify one completed before other started processing
            req1_completed_idx = execution_log.index("req1_completed")
            req2_acquired_idx = execution_log.index("req2_acquired_processing")
            req2_completed_idx = execution_log.index("req2_completed")
            req1_acquired_idx = execution_log.index("req1_acquired_processing")

            # One must complete before other acquires processing lock
            assert (
                req1_completed_idx < req2_acquired_idx
                or req2_completed_idx < req1_acquired_idx
            )

        finally:
            state.current_ai_studio_model_id = original_model


@pytest.mark.integration
class TestModelSwitchRaceConditions:
    """Tests for race conditions in model switching."""

    async def test_double_check_optimization_prevents_redundant_switches(
        self, real_server_state
    ):
        """
        Test that double-check inside lock prevents redundant switches.

        If model already switched by another request, skip browser operation.
        """
        lock = real_server_state.model_switching_lock

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            state.current_ai_studio_model_id = "gemini-1.5-pro"
            switch_call_count = {"count": 0}

            async def counting_switch(*args):
                """Count how many times browser switch is called."""
                switch_call_count["count"] += 1
                await asyncio.sleep(0.05)
                return True

            async def switch_to_flash(req_id: str):
                """Switch to flash model."""
                context = cast(
                    RequestContext,
                    {
                        "req_id": req_id,
                        "logger": MagicMock(),
                        "page": real_server_state.page_instance,
                        "model_switching_lock": lock,
                        "needs_model_switching": True,
                        "model_id_to_use": "gemini-1.5-flash",
                        "current_ai_studio_model_id": state.current_ai_studio_model_id,
                    },
                )

                with patch(
                    "browser_utils.switch_ai_studio_model",
                    new_callable=AsyncMock,
                    side_effect=counting_switch,
                ):
                    await handle_model_switching(req_id, context)

            # Start two concurrent requests switching to same model
            task1 = asyncio.create_task(switch_to_flash("req1"))
            task2 = asyncio.create_task(switch_to_flash("req2"))

            await asyncio.gather(task1, task2)

            # Only one should actually call browser switch (double-check optimization)
            # Second one sees state already correct inside lock
            assert switch_call_count["count"] == 1

        finally:
            state.current_ai_studio_model_id = original_model

    async def test_rapid_model_switching(self, real_server_state):
        """
        Test rapid model switching between multiple models.

        Verifies state remains consistent despite rapid switches.
        """
        lock = real_server_state.model_switching_lock

        # Save original state
        original_model = state.current_ai_studio_model_id
        try:
            state.current_ai_studio_model_id = "gemini-1.5-pro"
            models_to_test = [
                "gemini-1.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
            ]

            async def rapid_switch(model_id: str, req_id: str):
                """Rapidly switch to model."""
                context = cast(
                    RequestContext,
                    {
                        "req_id": req_id,
                        "logger": MagicMock(),
                        "page": real_server_state.page_instance,
                        "model_switching_lock": lock,
                        "needs_model_switching": True,
                        "model_id_to_use": model_id,
                        "current_ai_studio_model_id": state.current_ai_studio_model_id,
                    },
                )

                with patch(
                    "browser_utils.switch_ai_studio_model",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    result = await handle_model_switching(req_id, context)
                    return result["current_ai_studio_model_id"]

            # Execute rapid switches
            tasks = [
                asyncio.create_task(rapid_switch(model, f"req{i}"))
                for i, model in enumerate(models_to_test)
            ]

            results = await asyncio.gather(*tasks)

            # All switches should have succeeded
            assert len(results) == len(models_to_test)

            # Final state should match one of the target models
            assert state.current_ai_studio_model_id in models_to_test

        finally:
            state.current_ai_studio_model_id = original_model
