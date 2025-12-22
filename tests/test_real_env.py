#!/usr/bin/env python3
"""
Test script to verify the fix works with the actual .env file structure.
"""

import os
import sys


def test_real_env_loading():
    """Test that the fix works with real .env values."""

    print("Testing with real .env file values...")
    print("=" * 60)

    # Set environment variables to match your .env file
    os.environ['DEBUG_LOGS_ENABLED'] = 'true'
    os.environ['TRACE_LOGS_ENABLED'] = 'true'
    os.environ['AUTO_SAVE_AUTH'] = 'true'
    os.environ['LAUNCH_MODE'] = 'normal'
    os.environ['SERVER_LOG_LEVEL'] = 'DEBUG'

    try:
        # Import and test the launcher config
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from launcher.config import parse_args

        # Test 1: No CLI args - should use .env values
        original_argv = sys.argv.copy()
        sys.argv = ['launch_camoufox.py']

        args = parse_args()

        print("=== Test Results ===")
        print(f"DEBUG_LOGS_ENABLED: {args.debug_logs} (expected: True)")
        print(f"TRACE_LOGS_ENABLED: {args.trace_logs} (expected: True)")
        print(f"AUTO_SAVE_AUTH: {args.auto_save_auth} (expected: True)")
        print(f"debug_logs_from_cli: {getattr(args, 'debug_logs_from_cli', False)} (expected: False)")
        print(f"trace_logs_from_cli: {getattr(args, 'trace_logs_from_cli', False)} (expected: False)")
        print(f"auto_save_auth_from_cli: {getattr(args, 'auto_save_auth_from_cli', False)} (expected: False)")

        # Verify the fix worked
        success = True
        if not args.debug_logs:
            print("ERROR: debug_logs should be True")
            success = False
        if not args.trace_logs:
            print("ERROR: trace_logs should be True")
            success = False
        if not args.auto_save_auth:
            print("ERROR: auto_save_auth should be True")
            success = False
        if getattr(args, 'debug_logs_from_cli', True):
            print("ERROR: debug_logs_from_cli should be False")
            success = False
        if getattr(args, 'trace_logs_from_cli', True):
            print("ERROR: trace_logs_from_cli should be False")
            success = False
        if getattr(args, 'auto_save_auth_from_cli', True):
            print("ERROR: auto_save_auth_from_cli should be False")
            success = False

        sys.argv = original_argv

        if success:
            print("\nSUCCESS: .env file values are correctly respected!")
            return True
        else:
            print("\nFAILED: .env file values are not being respected.")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_real_env_loading()

    print("\n" + "=" * 60)
    if success:
        print("FIX CONFIRMED: Your .env file settings will now be respected!")
    else:
        print("FIX FAILED: The configuration override issue still exists.")
        sys.exit(1)
