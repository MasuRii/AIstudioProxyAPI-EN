import json
import zlib

import pytest

from stream.interceptors import HttpInterceptor


class TestHttpInterceptor:
    @pytest.fixture
    def interceptor(self):
        return HttpInterceptor()

    def test_should_intercept(self):
        """Test path-based interception logic for GenerateContent endpoints."""
        assert (
            HttpInterceptor.should_intercept("example.com", "/v1/GenerateContent")
            is True
        )
        assert (
            HttpInterceptor.should_intercept("example.com", "/generateContent") is True
        )
        assert HttpInterceptor.should_intercept("example.com", "/other/path") is False

    @pytest.mark.asyncio
    async def test_process_request_intercept(self, interceptor):
        data = b"some data"
        # Should return data as is but log it
        result = await interceptor.process_request(
            data, "example.com", "/GenerateContent"
        )
        assert result == data

    @pytest.mark.asyncio
    async def test_process_request_no_intercept(self, interceptor):
        data = b"some data"
        result = await interceptor.process_request(data, "example.com", "/other")
        assert result == data

    def test_decode_chunked_simple(self):
        """Test decoding complete chunked transfer encoding."""
        # Format: length\r\nchunk\r\n0\r\n\r\n
        chunk1 = b"Hello"
        chunk2 = b"World"
        data = (
            hex(len(chunk1))[2:].encode()
            + b"\r\n"
            + chunk1
            + b"\r\n"
            + hex(len(chunk2))[2:].encode()
            + b"\r\n"
            + chunk2
            + b"\r\n"
            + b"0\r\n\r\n"
        )

        decoded, is_done = HttpInterceptor._decode_chunked(data)
        assert decoded == b"HelloWorld"
        assert is_done is True

    def test_decode_chunked_partial(self):
        """Test decoding partial/incomplete chunked data."""
        # Partial chunk
        chunk1 = b"Hello"
        data = hex(len(chunk1))[2:].encode() + b"\r\n" + chunk1 + b"\r\n"

        # In the current implementation, if it doesn't find the end or next chunk properly,
        # it might behave differently.
        # The implementation loops.

        decoded, is_done = HttpInterceptor._decode_chunked(data)
        assert decoded == b"Hello"
        assert is_done is False

    def test_decompress_zlib_stream(self):
        """Test gzip decompression of stream data."""
        original_data = b"Hello World Repeated " * 10
        compressor = zlib.compressobj(wbits=zlib.MAX_WBITS | 16)  # gzip
        compressed_data = compressor.compress(original_data) + compressor.flush()

        decompressed = HttpInterceptor._decompress_zlib_stream(compressed_data)
        assert decompressed == original_data

    def test_parse_response_body(self, interceptor):
        """Test parsing response body content from stream."""
        # Mock response structure based on regex: [[[null,.*?]],\"model\"]
        # Payload len=2 -> body: [payload_id, "body_content"]
        # Actually payload is [payload_id, "body_content"] directly inside the structure matched?
        # If structure is [[[null, "body"]], "model"]
        # json_data = [[[None, "body"]], "model"]
        # json_data[0][0] = [None, "body"] -> payload
        # payload[1] = "body" -> works.

        # Valid match
        valid_json = '"Hello "'
        match_str = f'[[[null,{valid_json}]],"model"]'

        # Another valid match
        valid_json2 = '"World"'
        match_str2 = f'[[[null,{valid_json2}]],"model"]'

        data = match_str + match_str2

        # Use the buffer-based API
        interceptor.response_buffer = data
        result = interceptor.parse_response_from_buffer()
        assert result["body"] == "Hello World"
        assert result["reason"] == ""
        assert result["function"] == []

    def test_parse_response_reasoning(self, interceptor):
        """Test parsing reasoning/thinking content from stream."""
        # Payload len > 2 -> reason: [payload_id, "reasoning", ...]
        # payload = [None, "reasoning", "extra"]

        valid_json = '"Thinking...", "extra"'
        match_str = f'[[[null,{valid_json}]],"model"]'

        # Use the buffer-based API
        interceptor.response_buffer = match_str
        result = interceptor.parse_response_from_buffer()
        assert result["reason"] == "Thinking..."
        assert result["body"] == ""

    def test_parse_response_function(self, interceptor):
        """Test parsing function call parameters from stream."""
        # Payload len 11, index 1 is None, index 10 is list -> function
        # array_tool_calls = [func_name, params]
        # params format: [ [param_name, [type_indicator, value...]] ]

        # Let's verify string param: [name, [1, 2, "value"]] (len 3)

        # args passed to parse_toolcall_params expects [[param1, param2]]
        # So params_raw needs to be the list containing the list of params.
        # But wait, parse_toolcall_params takes 'args' and does params = args[0].
        # So args is [[p1, p2]].
        # So params_raw should be [[p1, p2]].

        params_raw = [[["arg1", [1, 2, "value1"]]]]

        tool_calls = ["my_func", params_raw]

        # Payload: 11 elements. index 1 is None. index 10 is tool_calls.
        # We need to construct the JSON string representing [null, null, ..., tool_calls]
        # Since we use valid_json inside [[[null, valid_json]]], valid_json should be the rest of the array elements.
        # [[[null, null, null, ..., tool_calls]], "model"]
        # payload = [null, null, ..., tool_calls]

        # So valid_json should be "null, null, ..., tool_calls_json"

        tool_calls_json = json.dumps(tool_calls)
        valid_json = "null," * 9 + tool_calls_json

        match_str = f'[[[null,{valid_json}]],"model"]'

        # Use the buffer-based API
        interceptor.response_buffer = match_str
        result = interceptor.parse_response_from_buffer()
        assert len(result["function"]) == 1
        assert result["function"][0]["name"] == "my_func"
        assert result["function"][0]["params"]["arg1"] == "value1"

    def test_parse_toolcall_params_types(self, interceptor):
        """Test parsing tool call parameters with various types (null, number, string, bool, object)."""
        # Test various parameter types
        # Object type needs extra nesting for the value [1, 2, 3, 4, [params]]
        args = [
            [
                ["p_null", [1]],  # len 1
                ["p_num", [1, 123]],  # len 2
                ["p_str", [1, 2, "abc"]],  # len 3
                ["p_bool_true", [1, 2, 3, 1]],  # len 4, val 1
                ["p_bool_false", [1, 2, 3, 0]],  # len 4, val 0
                [
                    "p_obj",
                    [1, 2, 3, 4, [[["inner", [1, 2, "val"]]]]],
                ],  # len 5, recursive, wrapped in extra list
            ]
        ]

        params = interceptor.parse_toolcall_params(args)

        assert params["p_null"] is None
        assert params["p_num"] == 123
        assert params["p_str"] == "abc"
        assert params["p_bool_true"] is True
        assert params["p_bool_false"] is False
        assert params["p_obj"] == {"inner": "val"}

    @pytest.mark.asyncio
    async def test_process_response_integration(self, interceptor):
        # Combine chunking, compression, and parsing

        # Create response data
        valid_json = '"Integrated"'
        match_str = f'[[[null,{valid_json}]],"model"]'
        response_body = match_str.encode()

        # Compress
        compressor = zlib.compressobj(wbits=zlib.MAX_WBITS | 16)
        compressed = compressor.compress(response_body) + compressor.flush()

        # Chunk
        chunked = (
            hex(len(compressed))[2:].encode()
            + b"\r\n"
            + compressed
            + b"\r\n"
            + b"0\r\n\r\n"
        )

        # Process
        result = await interceptor.process_response(
            chunked, "example.com", "/GenerateContent", {}
        )

        assert result["body"] == "Integrated"
        assert result["done"] is True

    @pytest.mark.asyncio
    async def test_process_request_exception(self, interceptor):
        # Mocking logger to verify exception logging if needed,
        # but the method catches exception and logs it, then returns data.
        # We can force an exception by passing an object that fails on decoding if logic used it,
        # but process_request logic is simple.
        # Let's mock log method to raise exception? No, that would crash test.
        # process_request does:
        # try:
        #    if ...
        # except Exception as e:
        #    logger.error(...)
        #    return data

        # We can force exception by making data.decode() fail if it were used,
        # but the current implementation might not decode if not needed.
        # Actually it doesn't decode explicitly in the try block shown in snippet unless I check file.
        # Let's check the file content first.
        # But wait, I can just pass an invalid type to process_request if it expects bytes.

        # If I pass an int, bytes operation might fail.
        result = await interceptor.process_request(123, "host", "path")
        assert result == 123  # Should return original data on error

    @pytest.mark.asyncio
    async def test_process_response_exception(self, interceptor):
        # Similar to process_request
        result = await interceptor.process_response(123, "host", "path", {})
        assert result == {"body": "", "reason": "", "function": [], "done": False}

    def test_decode_chunked_invalid_size(self):
        """Test chunked decoding with invalid hex size value."""
        # Invalid hex size
        data = b"ZZ\r\nData\r\n0\r\n\r\n"
        decoded, is_done = HttpInterceptor._decode_chunked(data)
        # Should catch ValueError and return b"" and False
        assert decoded == b""
        assert is_done is False

    def test_decode_chunked_exception(self):
        """Test chunked decoding handles malformed structure gracefully."""
        # Malformed structure that causes index error or other exception
        data = b"5\r\nHe"  # incomplete
        decoded, is_done = HttpInterceptor._decode_chunked(data)
        assert decoded == b""
        assert is_done is False


"""
High-quality tests for stream/interceptors.py - Edge cases and exception paths.

Focus: Hit uncovered lines (62-64, 78-79, 98-99, 139-140, 177) with targeted tests.
Strategy: Trigger exception paths and boundary conditions not covered by main test file.
"""


class TestHttpInterceptorEdgeCases:
    @pytest.fixture
    def interceptor(self):
        return HttpInterceptor()

    @pytest.mark.asyncio
    async def test_process_response_handles_invalid_chunking(self, interceptor):
        """
        Test scenario: process_response handles invalid chunked data gracefully
        Expected: Returns empty result dict (exceptions are caught internally)
        """
        # Create data that looks like valid chunked data but decompression will fail
        fake_chunk = b"not compressed data"
        chunked = (
            hex(len(fake_chunk))[2:].encode()
            + b"\r\n"
            + fake_chunk
            + b"\r\n"
            + b"0\r\n\r\n"
        )

        # process_response catches exceptions and returns empty result
        result = await interceptor.process_response(
            chunked, "example.com", "/GenerateContent", {}
        )
        assert result == {"body": "", "reason": "", "function": [], "done": False}

    @pytest.mark.asyncio
    async def test_process_response_handles_decompression_error(self, interceptor):
        """
        Test scenario: handles decompression failure gracefully
        Expected: Returns empty result dict (exceptions are caught internally)
        """
        # Create valid chunked data but with invalid compressed content
        invalid_compressed = b"not a valid zlib stream"
        chunked = (
            hex(len(invalid_compressed))[2:].encode()
            + b"\r\n"
            + invalid_compressed
            + b"\r\n"
            + b"0\r\n\r\n"
        )

        # process_response catches exceptions and returns empty result
        result = await interceptor.process_response(
            chunked, "example.com", "/GenerateContent", {}
        )
        assert result == {"body": "", "reason": "", "function": [], "done": False}

    def test_parse_response_with_malformed_json(self, interceptor):
        """
        Test scenario: data matched by regex is not valid JSON
        Expected: json.loads fails, continue to skip (lines 98-99)
        """
        # Create string that matches regex but has malformed JSON
        # Regex: rb'\[\[\[null,.*?]],"model"]'
        malformed_match = '[[[null,{not valid json}]],"model"]'  # Malformed JSON
        valid_match = '[[[null,"valid"]],"model"]'

        # Combine data: malformed first, then valid
        # Use buffer-based API
        interceptor.response_buffer = malformed_match + valid_match
        result = interceptor.parse_response_from_buffer()

        # Only the valid part should be parsed
        assert result["body"] == "valid"
        # Malformed JSON should be skipped and not affect the result

    def test_parse_response_with_multiple_malformed_json(self, interceptor):
        """
        Test scenario: all matches are invalid JSON
        Expected: return empty result (lines 98-99 all continue)
        """
        # Multiple strings that match regex but have invalid JSON
        malformed1 = '[[[null,invalid}]],"model"]'  # Not valid JSON
        malformed2 = '[[[null,{broken],"model"]'  # Malformed

        # Use buffer-based API
        interceptor.response_buffer = malformed1 + malformed2
        result = interceptor.parse_response_from_buffer()

        # All should be skipped, return empty values
        assert result["body"] == ""
        assert result["reason"] == ""
        assert result["function"] == []

    def test_parse_toolcall_params_with_invalid_structure(self, interceptor):
        """
        Test scenario: parse_toolcall_params encounters invalid parameter structure
        Expected: raises exception (lines 139-140)
        """
        # 传入格式错误的 args (期望是嵌套列表,但只给字符串)
        invalid_args = "not a list"

        with pytest.raises(Exception):
            interceptor.parse_toolcall_params(invalid_args)

    def test_parse_toolcall_params_with_malformed_nested_structure(self, interceptor):
        """
        Test scenario: nested object parameter format error
        Expected: raises exception during recursive call (lines 139-140)
        """
        # 外层格式正确,但嵌套对象的参数格式错误
        malformed_args = [
            [
                [
                    "p_obj",
                    [1, 2, 3, 4, "should be list not string"],  # 第5个元素应该是列表
                ]
            ]
        ]

        with pytest.raises(Exception):
            interceptor.parse_toolcall_params(malformed_args)

    def test_parse_toolcall_params_with_index_error(self, interceptor):
        """
        Test scenario: parameter list index out of bounds
        Expected: IndexError is raised (lines 139-140)
        """
        # args[0] 期望是参数列表,但 args 为空
        invalid_args = []

        with pytest.raises(Exception):
            interceptor.parse_toolcall_params(invalid_args)

    def test_decode_chunked_edge_case_truncated_end(self):
        """
        Test scenario: chunked data truncated at the end (line 177)
        Expected: detects length_crlf_idx + 2 + length + 2 > len(response_body), break
        """
        # 创建一个完整的块,但最后的 \r\n 被截断
        chunk = b"Hello"
        length_hex = hex(len(chunk))[2:].encode()

        # 正常应该是: length_hex + \r\n + chunk + \r\n
        # 但我们只提供到 chunk 结尾,缺少最后的 \r\n
        data = length_hex + b"\r\n" + chunk  # 缺少最后的 \r\n

        decoded, is_done = HttpInterceptor._decode_chunked(data)

        # 应该解析出 Hello, 但 is_done 为 False (因为没有遇到 0\r\n\r\n)
        assert decoded == b"Hello"
        assert is_done is False

    def test_decode_chunked_edge_case_partial_final_chunk(self):
        """
        Test scenario: last chunk data incomplete (line 177)
        Expected: length + 2 > len(response_body), break
        """
        # 声明一个10字节的块,但只提供5字节数据
        declared_length = 10
        actual_data = b"12345"  # 只有5字节

        data = (
            hex(declared_length)[2:].encode() + b"\r\n" + actual_data
        )  # 没有后续的 \r\n 和数据

        decoded, is_done = HttpInterceptor._decode_chunked(data)

        # 因为 length(10) + 2 > len(response_body), 会在 line 170-171 break
        assert decoded == b""
        assert is_done is False

    def test_decode_chunked_zero_length_chunk_without_final_marker(self):
        """
        Test scenario: encounter zero-length chunk but no 0\r\n\r\n marker
        Expected: return chunked_data, is_done=False
        """
        # 正常的零长度块应该是 0\r\n\r\n
        # 但这里只有 0\r\n (缺少后续的 \r\n)
        data = b"0\r\n"

        decoded, is_done = HttpInterceptor._decode_chunked(data)

        # 应该识别到 length=0, 但没找到 0\r\n\r\n, 所以 is_done=False
        assert decoded == b""
        assert is_done is False

    def test_decode_chunked_multiple_chunks_with_truncation(self):
        """
        Test scenario: multiple chunks, last one truncated (line 177)
        Expected: previous chunks parsed, last one discarded
        """
        chunk1 = b"First"
        chunk2 = b"Second"

        # 第一个块完整
        data = hex(len(chunk1))[2:].encode() + b"\r\n" + chunk1 + b"\r\n"

        # 第二个块声明了长度,但数据不完整
        data += hex(len(chunk2))[2:].encode() + b"\r\n" + b"Sec"  # 只有3字节,不是6

        decoded, is_done = HttpInterceptor._decode_chunked(data)

        # 第一个块应该被解析
        assert decoded == b"First"
        # 第二个块因为数据不足而被跳过
        assert is_done is False

    def test_decode_chunked_chunk_exactly_at_buffer_end(self):
        """
        Test scenario: chunk data exactly at buffer end, no end marker
        Expected: parse chunk, but is_done=False
        """
        chunk = b"Exact"
        data = hex(len(chunk))[2:].encode() + b"\r\n" + chunk + b"\r\n"

        # 没有 0\r\n\r\n 结束标记
        decoded, is_done = HttpInterceptor._decode_chunked(data)

        assert decoded == b"Exact"
        assert is_done is False

    @pytest.mark.asyncio
    async def test_process_request_with_non_intercepted_path(self, interceptor):
        """
        Test scenario: request path should not be intercepted
        Expected: return original data directly, does not enter try-except block
        """
        data = b"regular request data"
        result = await interceptor.process_request(data, "example.com", "/api/other")

        assert result == data

    @pytest.mark.asyncio
    async def test_process_request_with_intercepted_path_returns_data(
        self, interceptor
    ):
        """
        Test scenario: request on intercepted path processed normally
        Expected: returns original data (try block executes)
        """
        data = b'{"key": "value"}'
        result = await interceptor.process_request(
            data, "example.com", "/GenerateContent"
        )

        assert result == data

    def test_parse_response_with_json_array_parsing_error(self, interceptor):
        """
        Test scenario: JSON parsing successful but structure not as expected (json_data[0][0] indexing fails)
        Expected: except catches IndexError/TypeError, continue
        """
        # Matches regex, but structure is wrong: json_data is not the expected nested structure
        invalid_structure = '[[],"model"]'  # json_data[0][0] will fail

        # Use buffer-based API
        interceptor.response_buffer = invalid_structure
        result = interceptor.parse_response_from_buffer()

        # Should be skipped, return empty values
        assert result["body"] == ""

    def test_parse_response_empty_matches(self, interceptor):
        """
        Test scenario: no data matching regex
        Expected: return empty result
        """
        # Use buffer-based API
        interceptor.response_buffer = "no matching pattern here"
        result = interceptor.parse_response_from_buffer()

        assert result["body"] == ""
        assert result["reason"] == ""
        assert result["function"] == []


"""
Coverage tests for stream/interceptors.py - Exception paths

Targets:
- Lines 78-79: process_response exception handler
- Lines 98-99: parse_response json.loads exception
- Lines 139-140: parse_toolcall_params exception handler
- Line 177: _decode_chunked final break condition
"""

from unittest.mock import patch


class TestInterceptorExceptionPaths:
    @pytest.fixture
    def interceptor(self):
        return HttpInterceptor()

    @pytest.mark.asyncio
    async def test_process_response_handles_exception(self, interceptor):
        """
        Test scenario: internal method in process_response raises exception
        Expected: exception is caught and empty result returned
        """
        # Mock _decode_chunked to raise exception
        with patch.object(
            interceptor,
            "_decode_chunked",
            side_effect=ValueError("Decoding failed"),
        ):
            # process_response catches exceptions and returns empty result
            result = await interceptor.process_response(b"data", "host", "/path", {})
            assert result == {"body": "", "reason": "", "function": [], "done": False}

    def test_parse_response_invalid_json(self, interceptor):
        """
        Test scenario: regex match successful but JSON parsing fails
        Expected: catch exception and continue (lines 98-99)
        """
        # Create data that matches regex but has invalid JSON
        # Pattern: rb'\[\[\[null,.*?]],"model"]'
        # Valid match format but invalid JSON inside
        invalid_match = '[[[null,"unclosed string]],"model"]'

        # Use buffer-based API
        interceptor.response_buffer = invalid_match
        result = interceptor.parse_response_from_buffer()

        # Should skip invalid match and return empty result
        assert result["body"] == ""
        assert result["reason"] == ""
        assert result["function"] == []

    def test_parse_toolcall_params_exception(self, interceptor):
        """
        Test scenario: parse_toolcall_params raises exception during parameter parsing
        Expected: exception is re-raised (lines 139-140)
        """
        # Pass malformed args that cause exception during parsing
        # Expected structure: [[param1, param2, ...]]
        # Malformed: missing nested list
        malformed_args = None  # This will cause args[0] to raise TypeError

        with pytest.raises(TypeError):
            interceptor.parse_toolcall_params(malformed_args)

    def test_decode_chunked_final_break(self):
        """
        Test scenario: _decode_chunked exits at final break condition
        Expected: cover the break statement at line 177
        """
        # Create chunked data where:
        # length_crlf_idx + 2 + length + 2 > len(response_body)
        # This happens when we have a chunk header but incomplete trailing CRLF

        chunk_data = b"Hello"
        # Format: hex_length\r\ndata
        # Missing trailing \r\n after data
        data = hex(len(chunk_data))[2:].encode() + b"\r\n" + chunk_data

        # This should trigger the break at line 177
        # because after reading the chunk, there's no trailing CRLF
        decoded, is_done = HttpInterceptor._decode_chunked(data)

        # Should have decoded the chunk but not be done
        assert decoded == b"Hello"
        assert is_done is False


class TestInterceptorEdgeCases:
    @pytest.fixture
    def interceptor(self):
        return HttpInterceptor()

    def test_parse_response_malformed_payload_access(self, interceptor):
        """
        Test scenario: IndexError during payload access
        Expected: exception is caught, continue processing (lines 98-99)
        """
        # Create valid JSON but with unexpected structure
        # This will pass json.loads but fail on payload access
        malformed_json = json.dumps([[[]]])  # Missing expected payload structure
        match_str = f'[[{malformed_json}],"model"]'

        # Use buffer-based API
        interceptor.response_buffer = match_str
        result = interceptor.parse_response_from_buffer()

        # Should handle gracefully and return empty result
        assert result["body"] == ""
        assert result["reason"] == ""
        assert result["function"] == []

    def test_parse_toolcall_params_index_error(self, interceptor):
        """
        Test scenario: parse_toolcall_params encounters IndexError accessing args[0]
        Expected: exception is re-raised (lines 139-140)
        """
        # Pass empty list (args[0] will raise IndexError)
        with pytest.raises(IndexError):
            interceptor.parse_toolcall_params([])
