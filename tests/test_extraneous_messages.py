import pytest
import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api_utils.response_generators import gen_sse_from_aux_stream
from models import ChatCompletionRequest, Message

# Mock use_stream_response to yield sequence including messages after done
async def mock_use_stream_response_generator(req_id, timeout=5.0, page=None, check_client_disconnected=None, enable_silence_detection=True):
    # 1. Normal body message
    yield '{"reason": "", "body": "Hello", "done": false}'
    # 2. Done message
    yield '{"reason": "", "body": " world", "done": true}'
    # 3. EXTRANEOUS message (should be ignored)
    yield '{"reason": "", "body": " EXTRA", "done": false}'

@pytest.mark.anyio
async def test_extraneous_messages_ignored():
    req_id = "test_req_id"
    request = ChatCompletionRequest(
        messages=[Message(role="user", content="Hello")],
        model="test-model"
    )
    check_client_disconnected = MagicMock()
    event_to_set = asyncio.Event()
    
    # We mock api_utils.response_generators.use_stream_response 
    # because that's what gen_sse_from_aux_stream imports/uses (via the module scope usually, 
    # but gen_sse_from_aux_stream imports it from .utils)
    # Let's patch where it is defined or imported.
    # gen_sse_from_aux_stream imports use_stream_response from .utils
    
    with patch('api_utils.response_generators.use_stream_response', side_effect=mock_use_stream_response_generator):
        gen = gen_sse_from_aux_stream(
            req_id,
            request,
            "test-model",
            check_client_disconnected,
            event_to_set,
            timeout=1.0,
            page=None
        )
        
        chunks = []
        async for chunk in gen:
            chunks.append(chunk)
            
        full_content = ""
        for chunk in chunks:
            if "data: " in chunk and "[DONE]" not in chunk:
                data_str = chunk.replace("data: ", "").strip()
                try:
                    data = json.loads(data_str)
                    delta = data['choices'][0]['delta']
                    if 'content' in delta and delta['content']:
                        full_content += delta['content']
                except:
                    pass
        
        print(f"Full content received: '{full_content}'")
        
        # If the fix is working, " EXTRA" should NOT be in full_content.
        # If the fix is NOT working (current state), " EXTRA" WILL be in full_content.
        assert "EXTRA" not in full_content, f"Extraneous content found in response: {full_content}"
