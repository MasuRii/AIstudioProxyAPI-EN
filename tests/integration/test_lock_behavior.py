"""
Integration tests for lock behavior and concurrency control.

These tests verify that the lock hierarchy (processing_lock > model_switching_lock >
params_cache_lock) works correctly with REAL asyncio.Lock instances, catching
race conditions that mocked tests cannot detect.
"""

import asyncio

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_processing_lock_prevents_concurrent_execution(real_server_state):
    """
    Verify that processing_lock prevents concurrent browser access.

    This test uses REAL asyncio.Lock to ensure that two "requests" cannot
    execute simultaneously, preventing race conditions in browser automation.
    """
    execution_log = []
    lock = real_server_state.processing_lock

    async def simulate_request_processing(request_id: str, delay: float):
        """Simulate processing a request with the processing lock."""
        execution_log.append(f"{request_id}_start")

        async with lock:
            execution_log.append(f"{request_id}_acquired_lock")
            # Simulate some async work (browser interaction)
            await asyncio.sleep(delay)
            execution_log.append(f"{request_id}_releasing_lock")

        execution_log.append(f"{request_id}_done")

    # Start two tasks concurrently
    task1 = asyncio.create_task(simulate_request_processing("req1", 0.1))
    task2 = asyncio.create_task(simulate_request_processing("req2", 0.05))

    await asyncio.gather(task1, task2)

    # Verify execution order - req1 should complete entirely before req2 starts
    # or vice versa (depends on which acquires lock first)
    req1_acquired_idx = execution_log.index("req1_acquired_lock")
    req1_releasing_idx = execution_log.index("req1_releasing_lock")
    req2_acquired_idx = execution_log.index("req2_acquired_lock")
    req2_releasing_idx = execution_log.index("req2_releasing_lock")

    # One request must fully complete lock section before other enters
    req1_finished_before_req2_started = req1_releasing_idx < req2_acquired_idx
    req2_finished_before_req1_started = req2_releasing_idx < req1_acquired_idx

    assert req1_finished_before_req2_started or req2_finished_before_req1_started, (
        f"Lock did not prevent concurrent execution. Log: {execution_log}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_model_switching_lock_serializes_switches(real_server_state):
    """
    Verify that model_switching_lock prevents concurrent model changes.

    This test ensures that when multiple requests try to switch models,
    they are serialized properly and state remains consistent.
    """
    lock = real_server_state.model_switching_lock
    switch_order = []

    async def simulate_model_switch(request_id: str, target_model: str):
        """Simulate switching to a model."""
        async with lock:
            switch_order.append(f"{request_id}_start")
            # Simulate model switch operation
            await asyncio.sleep(0.05)
            real_server_state.current_ai_studio_model_id = target_model
            switch_order.append(f"{request_id}_done_{target_model}")

    # Start three concurrent model switch attempts
    tasks = [
        asyncio.create_task(simulate_model_switch("req1", "gemini-1.5-pro")),
        asyncio.create_task(simulate_model_switch("req2", "gemini-1.5-flash")),
        asyncio.create_task(simulate_model_switch("req3", "gemini-1.0-pro")),
    ]

    await asyncio.gather(*tasks)

    # Verify all switches completed
    assert len(switch_order) == 6  # 3 start + 3 done

    # Verify switches were serialized (each start followed by its done before next start)
    for i in range(0, len(switch_order), 2):
        start = switch_order[i]
        done = switch_order[i + 1]
        # Each start should be immediately followed by its done
        req_id = start.split("_")[0]
        assert done.startswith(f"{req_id}_done"), (
            f"Switches not serialized: {switch_order}"
        )

    # Verify final state is one of the target models
    assert real_server_state.current_ai_studio_model_id in [
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.0-pro",
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lock_hierarchy_no_deadlock(real_server_state):
    """
    Verify that lock hierarchy (processing > model_switching > params_cache)
    prevents deadlocks when nested.

    This test ensures that locks can be safely nested in the correct order.
    """
    processing_lock = real_server_state.processing_lock
    model_lock = real_server_state.model_switching_lock
    params_lock = real_server_state.params_cache_lock

    execution_log = []

    async def nested_lock_operation(operation_id: str):
        """Simulate operation that needs multiple locks in hierarchy order."""
        async with processing_lock:
            execution_log.append(f"{operation_id}_processing_acquired")

            async with model_lock:
                execution_log.append(f"{operation_id}_model_acquired")

                async with params_lock:
                    execution_log.append(f"{operation_id}_params_acquired")
                    await asyncio.sleep(0.01)  # Simulate work
                    execution_log.append(f"{operation_id}_params_released")

                execution_log.append(f"{operation_id}_model_released")

            execution_log.append(f"{operation_id}_processing_released")

    # Run nested lock operations
    # If deadlock occurs, this will timeout (pytest-timeout will catch it)
    await nested_lock_operation("op1")
    await nested_lock_operation("op2")

    # Verify both operations completed successfully
    assert "op1_params_acquired" in execution_log
    assert "op2_params_acquired" in execution_log
    assert len(execution_log) == 12  # 6 events per operation


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lock_release_on_exception(real_server_state):
    """
    Verify that locks are properly released even when exceptions occur.

    This is critical for preventing deadlocks in production.
    """
    lock = real_server_state.processing_lock
    execution_log = []

    async def failing_operation(op_id: str):
        """Operation that acquires lock then fails."""
        try:
            async with lock:
                execution_log.append(f"{op_id}_acquired")
                raise ValueError(f"Simulated error in {op_id}")
        except ValueError:
            execution_log.append(f"{op_id}_caught_exception")

    async def normal_operation(op_id: str):
        """Normal operation that acquires lock."""
        async with lock:
            execution_log.append(f"{op_id}_acquired")
            await asyncio.sleep(0.01)
            execution_log.append(f"{op_id}_done")

    # First operation fails but should release lock
    await failing_operation("fail_op")

    # Second operation should be able to acquire lock (not deadlocked)
    await normal_operation("success_op")

    # Verify both operations ran
    assert "fail_op_acquired" in execution_log
    assert "fail_op_caught_exception" in execution_log
    assert "success_op_acquired" in execution_log
    assert "success_op_done" in execution_log


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_queue_and_lock_access(real_server_state):
    """
    Verify that queue and lock work correctly together under concurrent load.

    This simulates the real scenario where multiple requests are queued and
    processed sequentially due to processing_lock.
    """
    queue = real_server_state.request_queue
    lock = real_server_state.processing_lock
    processed_order = []

    async def producer(num_items: int):
        """Add items to queue."""
        for i in range(num_items):
            await queue.put({"id": i, "data": f"item_{i}"})
            await asyncio.sleep(0.01)  # Simulate arrival rate

    async def consumer(consumer_id: str):
        """Process items from queue with lock."""
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                break

            async with lock:
                # Simulate processing
                await asyncio.sleep(0.02)
                processed_order.append((consumer_id, item["id"]))
                queue.task_done()

    # Start producer and two consumers concurrently
    producer_task = asyncio.create_task(producer(5))
    consumer1_task = asyncio.create_task(consumer("c1"))
    consumer2_task = asyncio.create_task(consumer("c2"))

    await producer_task
    await asyncio.gather(consumer1_task, consumer2_task)

    # Verify all items were processed
    assert len(processed_order) == 5

    # Verify all items 0-4 were processed
    processed_ids = [item_id for _, item_id in processed_order]
    assert sorted(processed_ids) == [0, 1, 2, 3, 4]

    # Verify queue is empty
    assert queue.empty()
