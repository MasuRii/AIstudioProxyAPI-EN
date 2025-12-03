"""
Integration tests for AIstudioProxyAPI.

These tests verify that components work correctly together using real
instances (locks, queues, state) rather than mocks.

Integration tests:
- Use real asyncio.Lock, asyncio.Queue from server_state
- Mock only external boundaries (browser, page, network)
- Test actual concurrency behavior, race conditions, and timing
- Catch bugs that unit tests with heavy mocking cannot detect

Run integration tests:
    pytest -m integration -v

Run only unit tests:
    pytest -m "not integration" -v
"""
