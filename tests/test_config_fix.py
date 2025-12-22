#!/usr/bin/env python3
"""
Test script to verify that the configuration override fix works correctly.
This script tests that .env file settings are respected when not explicitly overridden by command line arguments.
"""

import os
import sys
import tempfile


def test_config_fix():
    """Test that environment variables from .env are respected."""
    
    # Create a temporary .env file with test values
    env_content = """
DEBUG_LOGS_ENABLED=true
TRACE_LOGS_ENABLED=true
AUTO_SAVE_AUTH=true
LAUNCH_MODE=normal
SERVER_LOG_LEVEL=DEBUG
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write(env_content)
        temp_env_path = f.name
    
    try:
        # Test 1: Check if launcher reads .env values correctly when no CLI args provided
        print("=== Test 1: Reading .env values without CLI overrides ===")
        
        # Set environment variables to simulate .env file loading
        os.environ['DEBUG_LOGS_ENABLED'] = 'true'
        os.environ['TRACE_LOGS_ENABLED'] = 'true'
        os.environ['AUTO_SAVE_AUTH'] = 'true'
        os.environ['LAUNCH_MODE'] = 'normal'
        os.environ['SERVER_LOG_LEVEL'] = 'DEBUG'
        
        # Test the argument parsing by importing the launcher config
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        try:
            from launcher.config import parse_args
            
            # Test without CLI args - should use .env defaults
            original_argv = sys.argv.copy()
            sys.argv = ['launch_camoufox.py']
            
            args = parse_args()
            
            print(f"DEBUG_LOGS_ENABLED from config: {args.debug_logs}")
            print(f"TRACE_LOGS_ENABLED from config: {args.trace_logs}")
            print(f"AUTO_SAVE_AUTH from config: {args.auto_save_auth}")
            print(f"debug_logs_from_cli flag: {getattr(args, 'debug_logs_from_cli', 'NOT SET')}")
            print(f"trace_logs_from_cli flag: {getattr(args, 'trace_logs_from_cli', 'NOT SET')}")
            print(f"auto_save_auth_from_cli flag: {getattr(args, 'auto_save_auth_from_cli', 'NOT SET')}")
            
            # Verify the fix: args should reflect .env values when no CLI args provided
            assert args.debug_logs == True, f"Expected debug_logs=True, got {args.debug_logs}"
            assert args.trace_logs == True, f"Expected trace_logs=True, got {args.trace_logs}"
            assert args.auto_save_auth == True, f"Expected auto_save_auth=True, got {args.auto_save_auth}"
            assert getattr(args, 'debug_logs_from_cli', False) == False, "debug_logs_from_cli should be False"
            assert getattr(args, 'trace_logs_from_cli', False) == False, "trace_logs_from_cli should be False"
            assert getattr(args, 'auto_save_auth_from_cli', False) == False, "auto_save_auth_from_cli should be False"
            
            print("OK Test 1 PASSED: .env values correctly loaded")
            
        except Exception as e:
            print(f"X Test 1 FAILED: {e}")
            return False
        finally:
            sys.argv = original_argv
            if 'launcher.config' in sys.modules:
                del sys.modules['launcher.config']
        
        # Test 2: Check if CLI args override .env values
        print("\n=== Test 2: CLI args override .env values ===")
        
        try:
            # Reset the module to force re-import
            if 'launcher.config' in sys.modules:
                del sys.modules['launcher.config']
            
            # Test with CLI args - should override .env defaults
            original_argv = sys.argv.copy()
            sys.argv = ['launch_camoufox.py', '--debug-logs', '--trace-logs', '--auto-save-auth']
            
            args = parse_args()
            
            print(f"DEBUG_LOGS_ENABLED from config: {args.debug_logs}")
            print(f"TRACE_LOGS_ENABLED from config: {args.trace_logs}")
            print(f"AUTO_SAVE_AUTH from config: {args.auto_save_auth}")
            print(f"debug_logs_from_cli flag: {getattr(args, 'debug_logs_from_cli', 'NOT SET')}")
            print(f"trace_logs_from_cli flag: {getattr(args, 'trace_logs_from_cli', 'NOT SET')}")
            print(f"auto_save_auth_from_cli flag: {getattr(args, 'auto_save_auth_from_cli', 'NOT SET')}")
            
            # Verify CLI override: args should be True and CLI flags should be True
            assert args.debug_logs == True, f"Expected debug_logs=True, got {args.debug_logs}"
            assert args.trace_logs == True, f"Expected trace_logs=True, got {args.trace_logs}"
            assert args.auto_save_auth == True, f"Expected auto_save_auth=True, got {args.auto_save_auth}"
            assert getattr(args, 'debug_logs_from_cli', False) == True, "debug_logs_from_cli should be True"
            assert getattr(args, 'trace_logs_from_cli', False) == True, "trace_logs_from_cli should be True"
            assert getattr(args, 'auto_save_auth_from_cli', False) == True, "auto_save_auth_from_cli should be True"
            
            print("OK Test 2 PASSED: CLI args correctly override .env values")
            
        except Exception as e:
            print(f"X Test 2 FAILED: {e}")
            return False
        finally:
            sys.argv = original_argv
            if 'launcher.config' in sys.modules:
                del sys.modules['launcher.config']
        
        return True
        
    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_env_path)
        except:
            pass

if __name__ == "__main__":
    print("Testing configuration override fix...")
    print("=" * 60)
    
    success = test_config_fix()
    
    print("\n" + "=" * 60)
    if success:
        print("ALL TESTS PASSED! Configuration fix is working correctly.")
        print("\nSummary of the fix:")
        print("- .env file values are now respected when no CLI args are provided")
        print("- CLI arguments still properly override .env values when specified")
        print("- The launcher distinguishes between defaults and explicit user settings")
    else:
        print("TESTS FAILED! Configuration fix needs more work.")
        sys.exit(1)