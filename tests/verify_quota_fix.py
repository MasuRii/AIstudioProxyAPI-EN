import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add repository root to sys.path
sys.path.append(os.getcwd())

import browser_utils.operations  # Import to ensure we can patch it
from api_utils.response_generators import gen_sse_from_aux_stream
from config.global_state import GlobalState
from models import ChatCompletionRequest, Message


# Mock ChatCompletionRequest
def create_mock_request():
    # Helper to create a dummy request object
    return ChatCompletionRequest(
        messages=[Message(role="user", content="test")],
        model="test-model"
    )

async def mock_use_stream_response(req_id, timeout=5.0, page=None, check_client_disconnected=None, enable_silence_detection=True):
    # Simulate empty stream that finishes immediately
    yield json.dumps({"done": True})

async def mock_check_quota_limit(page, req_id):
    print(f"DEBUG: mock_check_quota_limit called for {req_id}")
    # Simulate finding a quota error and setting the flag
    GlobalState.IS_QUOTA_EXCEEDED = True
    return

@pytest.mark.asyncio
async def test_quota_fix_logic():
    print("Starting test_quota_fix")
    
    # Reset GlobalState
    GlobalState.IS_QUOTA_EXCEEDED = False
    GlobalState.IS_RECOVERING = False
    
    # Mock dependencies
    mock_page = AsyncMock()
    mock_event = asyncio.Event()
    mock_check_disconnect = MagicMock()
    
    # Patch dependencies
    # 1. Patch use_stream_response where it is used in response_generators
    # 2. Patch check_quota_limit in browser_utils.operations so the import inside the function gets the mock
    with patch('api_utils.response_generators.use_stream_response', side_effect=mock_use_stream_response), \
         patch.object(browser_utils.operations, 'check_quota_limit', side_effect=mock_check_quota_limit):
            
            generator = gen_sse_from_aux_stream(
                req_id="test_req",
                request=create_mock_request(),
                model_name_for_stream="test-model",
                check_client_disconnected=mock_check_disconnect,
                event_to_set=mock_event,
                timeout=10.0,
                page=mock_page
            )
            
            items = []
            try:
                # Iterate through the generator
                # We expect it to yield heartbeats after setting the quota flag
                async for item in generator:
                    print(f"Received item: {item.strip()[:100]}...") # Print first 100 chars
                    items.append(item)
                    
                    if ": heartbeat" in item:
                        print("Verified: Received heartbeat.")
                        # We entered the holding pattern! Break loop to finish test.
                        break
                        
                    if "Model finished thinking but generated no code/text output" in item:
                        print("FAILURE: Received fallback text.")
                        break
                        
                    # Safety break to prevent infinite loops if logic is wrong
                    if len(items) > 20: 
                        print("FAILURE: Loop limit reached without heartbeat.")
                        break
                        
            except Exception as e:
                print(f"Exception during generation: {e}")
                import traceback
                traceback.print_exc()

            # --- Assertions ---
            print("\n--- Assertions ---")
            
            # 1. Assert GlobalState is updated
            if GlobalState.IS_QUOTA_EXCEEDED:
                print("PASS: GlobalState.IS_QUOTA_EXCEEDED is True")
            else:
                print("FAIL: GlobalState.IS_QUOTA_EXCEEDED is False")
                sys.exit(1)
            
            # 2. Assert NO fallback text
            has_fallback = any("Model finished thinking" in item for item in items)
            if not has_fallback:
                print("PASS: Fallback text was NOT sent")
            else:
                print("FAIL: Fallback text WAS sent")
                sys.exit(1)
            
            # 3. Assert heartbeat received
            has_heartbeat = any(": heartbeat" in item for item in items)
            if has_heartbeat:
                print("PASS: Heartbeat signal received")
            else:
                print("FAIL: Heartbeat signal NOT received")
                sys.exit(1)
            
            print("\nSUCCESS: All criteria met. Quota fix verified.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(test_quota_fix_logic())
    finally:
        loop.close()