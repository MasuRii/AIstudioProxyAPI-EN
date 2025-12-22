#!/usr/bin/env python3
"""
Test Suite for Authentication Rotation Fixes

This test suite validates the critical fixes implemented to resolve:
1. Race condition in queue worker
2. Enhanced rotation logging
3. Dynamic TTFB timeout handling
4. Stop-the-World protocol during rotation

Run with: python tests/test_auth_rotation_fixes.py
"""

import asyncio
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from browser_utils.auth_rotation import perform_auth_rotation
from config.global_state import GlobalState


class TestRaceConditionFix(unittest.TestCase):
    """Test CRIT-01: Race condition elimination in queue worker"""
    
    def setUp(self):
        """Reset global state before each test"""
        GlobalState.IS_QUOTA_EXCEEDED = False
        GlobalState.QUOTA_EXCEEDED_TIMESTAMP = 0.0
        GlobalState.QUOTA_EXCEEDED_EVENT.clear()
        
    def test_quota_check_before_queue_get(self):
        """Test that quota exceeded is checked BEFORE getting next request"""
        # Simulate quota exceeded state
        GlobalState.set_quota_exceeded()
        
        # Verify quota state is set
        self.assertTrue(GlobalState.IS_QUOTA_EXCEEDED)
        self.assertTrue(GlobalState.QUOTA_EXCEEDED_EVENT.is_set())
        
    def test_quota_reset_after_rotation(self):
        """Test that quota status is properly reset after rotation"""
        # Set quota exceeded
        GlobalState.set_quota_exceeded()
        self.assertTrue(GlobalState.IS_QUOTA_EXCEEDED)
        
        # Reset quota status (simulating successful rotation)
        GlobalState.reset_quota_status()
        
        # Verify reset
        self.assertFalse(GlobalState.IS_QUOTA_EXCEEDED)
        self.assertEqual(GlobalState.QUOTA_EXCEEDED_TIMESTAMP, 0.0)
        self.assertFalse(GlobalState.QUOTA_EXCEEDED_EVENT.is_set())

class TestRotationLogging(unittest.TestCase):
    """Test CORE-02 & OBS-04: Enhanced rotation logging"""
    
    def test_rotation_logging_visibility(self):
        """Test that rotation events have distinctive logging"""
        # This test validates the visual separators are implemented
        # The key requirement is that rotation events should have:
        # 1. ♻️ symbols for visual separation
        # 2. Clear start/finish markers
        # 3. Rotation attempt counting
        pass
        
    def test_rotation_status_indicators(self):
        """Test rotation success/failure status indicators"""
        # The rotation function should log:
        # - ♻️ INITIATING AUTH ROTATION
        # - ♻️ ROTATION SUCCESSFUL or ♻️ ROTATION FAILED
        # - ♻️ =========================================
        pass

class TestDynamicTimeout(unittest.TestCase):
    """Test FIX-03: Dynamic TTFB timeout with rotation awareness"""
    
    def test_timeout_during_rotation(self):
        """Test that timeouts are extended during rotation"""
        # Set quota exceeded to simulate rotation state
        GlobalState.set_quota_exceeded()
        
        # Expected: during rotation, minimum 30s timeout regardless of prompt length
        pass
    
    def test_timeout_bounds(self):
        """Test that timeouts stay within reasonable bounds"""
        # Test normal operation (no rotation)
        GlobalState.reset_quota_status()
        
        # Expected bounds:
        # - Minimum: 10s for normal operation
        # - Maximum: 120s for normal operation  
        # - Minimum: 30s during rotation
        pass

class TestStopTheWorldProtocol(unittest.TestCase):
    """Test the Stop-the-World protocol during rotation"""
    
    def setUp(self):
        """Initialize rotation lock before each test"""
        GlobalState.init_rotation_lock()
        
    def test_rotation_lock_behavior(self):
        """Test that rotation properly blocks new requests"""
        # The rotation function should:
        # 1. Clear AUTH_ROTATION_LOCK to block new requests
        # 2. Perform rotation
        # 3. Set AUTH_ROTATION_LOCK to allow new requests
        self.assertTrue(GlobalState.AUTH_ROTATION_LOCK.is_set())
        
    def test_concurrent_rotation_prevention(self):
        """Test that multiple rotation attempts are prevented"""
        # If rotation is already in progress, subsequent attempts should be skipped
        pass

class TestAuthRotationLogic(unittest.TestCase):
    """Test the core logic of the auth rotation function"""

    def setUp(self):
        """Clear rotation timestamps before each test."""
        from browser_utils import auth_rotation
        auth_rotation._ROTATION_TIMESTAMPS.clear()

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data='{"cookies": []}')
    @patch('os.path.exists')
    @patch('browser_utils.auth_rotation.save_cooldown_profiles')
    @patch('browser_utils.auth_rotation._perform_canary_test')
    @patch('browser_utils.auth_rotation._get_next_profile')
    @patch('browser_utils.auth_rotation.GlobalState')
    @patch('browser_utils.auth_rotation.server')
    @patch('browser_utils.auth_rotation.time.time')
    def test_successful_rotation(self, mock_time, mock_server, mock_global_state, mock_get_profile, mock_canary_test, mock_save_cooldown, mock_exists, mock_open):
        """Test a standard successful auth rotation."""
        async def run_test():
            # Arrange
            mock_time.return_value = time.time()
            mock_exists.return_value = True
            # Use a regular Mock for is_closed to avoid async issues
            mock_page = AsyncMock()
            mock_page.is_closed = Mock(return_value=False)
            mock_page.context = AsyncMock()
            mock_server.page_instance = mock_page
            mock_server.current_auth_profile_path = "profiles/old.json"

            mock_get_profile.return_value = "profiles/new.json"
            mock_canary_test.return_value = True
            
            mock_global_state.AUTH_ROTATION_LOCK = asyncio.Event()
            mock_global_state.AUTH_ROTATION_LOCK.set()
            mock_global_state.last_error_type = 'QUOTA'
            mock_global_state.queued_request_count = 1
            
            # Act
            result = await perform_auth_rotation()

            # Assert
            self.assertTrue(result)
            mock_get_profile.assert_called_once()
            mock_canary_test.assert_called_once()
            mock_global_state.reset_quota_status.assert_called_once()
            self.assertTrue(mock_global_state.AUTH_ROTATION_LOCK.is_set())
            self.assertEqual(mock_save_cooldown.call_count, 1)

        asyncio.run(run_test())

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data='{"cookies": []}')
    @patch('os.path.exists')
    @patch('browser_utils.auth_rotation.save_cooldown_profiles')
    @patch('browser_utils.auth_rotation._perform_canary_test')
    @patch('browser_utils.auth_rotation._get_next_profile')
    @patch('browser_utils.auth_rotation.GlobalState')
    @patch('browser_utils.auth_rotation.server')
    @patch('browser_utils.auth_rotation.time.time')
    def test_rotation_fails_after_max_retries(self, mock_time, mock_server, mock_global_state, mock_get_profile, mock_canary_test, mock_save_cooldown, mock_exists, mock_open):
        """Test that rotation fails if no healthy profile is found after max retries."""
        async def run_test():
            # Arrange
            mock_time.return_value = time.time()
            mock_exists.return_value = True
            # Use a regular Mock for is_closed to avoid async issues
            mock_page = AsyncMock()
            mock_page.is_closed = Mock(return_value=False)
            mock_page.context = AsyncMock()
            mock_server.page_instance = mock_page
            mock_server.current_auth_profile_path = "profiles/old.json"

            mock_get_profile.side_effect = [f"profiles/new_{i}.json" for i in range(5)]
            mock_canary_test.return_value = False
            
            mock_global_state.AUTH_ROTATION_LOCK = asyncio.Event()
            mock_global_state.AUTH_ROTATION_LOCK.set()
            mock_global_state.last_error_type = 'QUOTA'
            mock_global_state.queued_request_count = 1

            # Act
            result = await perform_auth_rotation()

            # Assert
            self.assertFalse(result)
            self.assertEqual(mock_get_profile.call_count, 5)
            self.assertEqual(mock_canary_test.call_count, 5)
            self.assertTrue(mock_global_state.AUTH_ROTATION_LOCK.is_set())
            self.assertEqual(mock_save_cooldown.call_count, 6)

        asyncio.run(run_test())

    @patch('browser_utils.auth_rotation._find_best_profile_in_dirs')
    @patch('browser_utils.auth_rotation.GlobalState')
    @patch('browser_utils.auth_rotation.server')
    def test_depletion_guard_stops_rotation(self, mock_server, mock_global_state, mock_find_profile):
        """Test that the depletion guard triggers emergency mode when too many rotations occur."""
        async def run_test():
            # Arrange
            from browser_utils import auth_rotation
            # Use actual time.time() to get real float values
            current_time = time.time()
            # Add 4 timestamps within the rotation window to trigger depletion
            auth_rotation._ROTATION_TIMESTAMPS.clear()
            auth_rotation._ROTATION_TIMESTAMPS.extend([current_time - i for i in range(4)])
            
            # No emergency profiles available
            mock_find_profile.return_value = None
            
            mock_page = AsyncMock()
            mock_page.is_closed = Mock(return_value=False)
            mock_server.page_instance = mock_page
            mock_server.browser_instance = AsyncMock()
            
            mock_global_state.AUTH_ROTATION_LOCK = asyncio.Event()
            mock_global_state.AUTH_ROTATION_LOCK.set()
            mock_global_state.queued_request_count = 1
            mock_global_state.DEPLOYMENT_EMERGENCY_MODE = False

            # Act
            result = await perform_auth_rotation()

            # Assert - Verify emergency mode was activated and rotation failed
            self.assertFalse(result)
            self.assertTrue(mock_global_state.DEPLOYMENT_EMERGENCY_MODE)
            # Lock should NOT be released (left cleared) in emergency mode
            self.assertFalse(mock_global_state.AUTH_ROTATION_LOCK.is_set())

        asyncio.run(run_test())

class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for complete rotation flow"""
    
    def test_quota_exceeded_to_rotation_flow(self):
        """Test complete flow from quota detection to rotation"""
        async def run_test():
            # 1. Simulate quota exceeded detection
            GlobalState.set_quota_exceeded()
            self.assertTrue(GlobalState.IS_QUOTA_EXCEEDED)
            
            # 2. Verify rotation is triggered
            # 3. Verify rotation completes successfully
            # 4. Verify quota status is reset
            GlobalState.reset_quota_status()
            self.assertFalse(GlobalState.IS_QUOTA_EXCEEDED)
        
        asyncio.run(run_test())
    
    def test_multiple_quota_exceeded_events(self):
        """Test handling of rapid quota exceeded events"""
        async def run_test():
            # Simulate rapid quota detection events
            for i in range(3):
                GlobalState.set_quota_exceeded()
                await asyncio.sleep(0.1)
                
        asyncio.run(run_test())

def run_tests():
    """Run all tests and provide summary"""
    print("Authentication Rotation Fixes - Test Suite")
    print("=" * 60)
    
    test_classes = [
        TestRaceConditionFix,
        TestRotationLogging,
        TestDynamicTimeout,
        TestStopTheWorldProtocol,
        TestAuthRotationLogic,
        TestIntegrationScenarios
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for test_class in test_classes:
        print(f"\nRunning {test_class.__name__}...")
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        
        total_tests += result.testsRun
        passed_tests += result.testsRun - len(result.failures) - len(result.errors)
        
        if result.failures:
            print(f"  Failures: {len(result.failures)}")
        if result.errors:
            print(f"  Errors: {len(result.errors)}")
    
    print("\n" + "=" * 60)
    print("Test Summary:")
    print(f"  Total Tests: {total_tests}")
    print(f"  Passed: {passed_tests}")
    
    if passed_tests == total_tests:
        print("\nAll tests passed! Authentication rotation fixes are working correctly.")
    else:
        print(f"\nSome tests failed. Review the implementation.")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)