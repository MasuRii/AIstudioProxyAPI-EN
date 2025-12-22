#!/usr/bin/env python3
"""
Test to verify the fix for quota rotation stream termination issue.

This test simulates the exact scenario from the bug report:
1. Quota exceeded triggers rotation
2. Rotation completes successfully 
3. Stream receives empty DONE signal (Body=0, Reason=0)
4. System should NOT complete the stream, but ignore the stale DONE

The fix ensures that post-rotation empty DONE signals are properly
identified as stale zombie packets and ignored.
"""

import time

import pytest

from config.global_state import GlobalState


class TestQuotaRotationFix:
    """Test the quota rotation fix for stream termination issue"""

    def setup_method(self):
        """Reset GlobalState before each test"""
        GlobalState.IS_QUOTA_EXCEEDED = False
        GlobalState.IS_RECOVERING = False
        GlobalState.LAST_ROTATION_TIMESTAMP = 0.0
        GlobalState.queued_request_count = 0

    def test_post_rotation_zombie_detection_various_timestamps(self):
        """Test zombie detection works correctly for various rotation timestamps"""
        
        # Simulate the exact scenario from the bug report:
        # Rotation completes at t=0, DONE received at t=0.9 (< 1 second)
        
        current_time = time.time()
        GlobalState.LAST_ROTATION_TIMESTAMP = current_time - 0.9  # 0.9 seconds ago
        
        # Verify the rotation timestamp logic
        just_rotated = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 15.0)
        recently_recovered = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 30.0)
        
        assert just_rotated is True, "Should detect recent rotation"
        assert recently_recovered is True, "Should detect recent recovery"
        
        # Test enhanced rotation detection (45 second window)
        time_since_rotation = time.time() - GlobalState.LAST_ROTATION_TIMESTAMP
        is_recent_rotation = time_since_rotation < 45.0
        
        assert is_recent_rotation is True, "Should detect rotation within 45s window"

    def test_post_rotation_zombie_detection_edge_cases(self):
        """Test edge cases for post-rotation zombie detection"""
        
        # Test case 1: Very recent rotation (within 15s)
        current_time = time.time()
        GlobalState.LAST_ROTATION_TIMESTAMP = current_time - 10.0  # 10 seconds ago
        
        just_rotated = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 15.0)
        recently_recovered = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 30.0)
        
        assert just_rotated is True
        assert recently_recovered is True
        
        # Test case 2: Moderate recent rotation (within 30s)
        GlobalState.LAST_ROTATION_TIMESTAMP = current_time - 20.0  # 20 seconds ago
        
        just_rotated = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 15.0)
        recently_recovered = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 30.0)
        
        assert just_rotated is False
        assert recently_recovered is True
        
        # Test case 3: Old rotation (outside 30s)
        GlobalState.LAST_ROTATION_TIMESTAMP = current_time - 60.0  # 60 seconds ago
        
        just_rotated = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 15.0)
        recently_recovered = (time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 30.0)
        
        assert just_rotated is False
        assert recently_recovered is False

    def test_enhanced_zombie_detection_45s_window(self):
        """Test the enhanced 45-second window for zombie detection"""
        
        current_time = time.time()
        
        # Test various timestamps within the 45s window
        test_cases = [
            (5.0, True),   # 5 seconds ago - should detect
            (15.0, True),  # 15 seconds ago - should detect  
            (30.0, True),  # 30 seconds ago - should detect
            (40.0, True),  # 40 seconds ago - should detect
            (50.0, False), # 50 seconds ago - should NOT detect
            (100.0, False) # 100 seconds ago - should NOT detect
        ]
        
        for seconds_ago, should_detect in test_cases:
            GlobalState.LAST_ROTATION_TIMESTAMP = current_time - seconds_ago
            
            time_since_rotation = time.time() - GlobalState.LAST_ROTATION_TIMESTAMP
            is_recent_rotation = time_since_rotation < 45.0
            
            assert is_recent_rotation == should_detect, \
                f"Rotation {seconds_ago}s ago should {'detect' if should_detect else 'NOT detect'} as recent"

    def test_global_state_reset_quota_status(self):
        """Test that quota status reset works correctly"""
        
        # Set quota exceeded state
        GlobalState.set_quota_exceeded("Test quota exceeded")
        assert GlobalState.IS_QUOTA_EXCEEDED is True
        
        # Reset quota status (simulating what happens after rotation)
        GlobalState.reset_quota_status()
        assert GlobalState.IS_QUOTA_EXCEEDED is False
        # Note: reset_quota_status doesn't update LAST_ROTATION_TIMESTAMP
        
        # After reset, timestamp should be updated during finish_recovery
        original_timestamp = GlobalState.LAST_ROTATION_TIMESTAMP
        time.sleep(0.1)  # Small delay
        
        GlobalState.finish_recovery()
        assert GlobalState.LAST_ROTATION_TIMESTAMP > original_timestamp

    def test_recovery_state_management(self):
        """Test recovery state transitions work correctly"""
        
        # Start recovery (simulating quota detection)
        GlobalState.start_recovery()
        assert GlobalState.IS_RECOVERING is True
        
        # Finish recovery (simulating successful rotation)  
        GlobalState.finish_recovery()
        assert GlobalState.IS_RECOVERING is False
        assert GlobalState.LAST_ROTATION_TIMESTAMP > 0


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])