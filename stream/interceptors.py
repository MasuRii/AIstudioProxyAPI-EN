import json
import logging
import re
import sys
import zlib
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import unquote

from config.global_state import GlobalState
from config.settings import FUNCTION_CALLING_DEBUG
from logging_utils.fc_debug import get_fc_logger
from logging_utils.grid_logger import GridFormatter

# FC debug logger for wire format parsing
fc_logger = get_fc_logger()


class HttpInterceptor:
    """
    Class to intercept and process HTTP requests and responses
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self.logger = logging.getLogger("http_interceptor")
        self.response_buffer = ""  # Persistent buffer for accumulating response data
        self.setup_logging()

    @staticmethod
    def setup_logging():
        """Set up logging configuration with colored output"""
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(
            GridFormatter(show_tree=False, colorize=True, burst_suppression=False)
        )
        console_handler.setLevel(logging.INFO)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)

        logging.getLogger("asyncio").setLevel(logging.ERROR)
        logging.getLogger("websockets").setLevel(logging.ERROR)
        # Silence http_interceptor by default (too verbose)
        logging.getLogger("http_interceptor").setLevel(logging.WARNING)

    @staticmethod
    def should_intercept(host: str, path: str):
        """
        Determine if the request should be intercepted based on host and path
        """
        # Check if the endpoint contains GenerateContent
        if "GenerateContent" in path or "generateContent" in path:
            return True

        # Check for jserror logging endpoint
        if "jserror" in path:
            return True

        return False

    async def process_request(
        self, request_data: Union[int, bytes], host: str, path: str
    ) -> Union[int, bytes]:
        """
        Process the request data before sending to the server
        """
        if not self.should_intercept(host, path):
            return request_data

        # Log the request
        self.logger.debug(f"[Network] Intercepted request: {host}{path}")

        # Check for Quota Exceeded errors in jserror requests
        if "jserror" in path:
            try:
                decoded_path = unquote(path)
                if any(
                    keyword in decoded_path
                    for keyword in [
                        "exceeded quota",
                        "RESOURCE_EXHAUSTED",
                        "Failed to generate content",
                    ]
                ):
                    self.logger.critical(
                        f"🚨 CRITICAL: Detected Quota Exceeded error in network traffic! URL: {path}"
                    )

                    from api_utils.server_state import state

                    model_id = state.current_ai_studio_model_id
                    GlobalState.set_quota_exceeded(
                        message=decoded_path, model_id=model_id or ""
                    )
            except Exception as e:
                self.logger.error(f"Error parsing jserror path: {e}")

        return request_data

    async def process_response(
        self,
        response_data: Union[int, bytes],
        host: str,
        path: str,
        headers: Dict[Any, Any],
    ) -> Dict[str, Any]:
        """
        Process the response data before sending to the client using persistent buffering
        """
        try:
            # Handle chunked encoding
            decoded_data, is_done = self._decode_chunked(bytes(response_data))
            # Handle gzip encoding
            decoded_data = self._decompress_zlib_stream(decoded_data)

            # Convert to string and accumulate in persistent buffer
            try:
                decoded_str = decoded_data.decode("utf-8")
                self.response_buffer += decoded_str
            except UnicodeDecodeError:
                # Not UTF-8 data, return empty result
                return {"reason": "", "body": "", "function": [], "done": is_done}

            # Try to parse complete JSON objects from the buffer
            result = self.parse_response_from_buffer(is_done)
            return result
        except Exception as e:
            self.logger.debug(f"Error processing response: {e}")
            return {"reason": "", "body": "", "function": [], "done": False}

    def parse_response_from_buffer(self, is_done=False):
        """
        Parse complete JSON objects from the persistent response buffer.
        """
        resp = {"reason": "", "body": "", "function": [], "done": is_done}

        try:
            # Check buffer size to prevent memory leaks
            if len(self.response_buffer) > 10 * 1024 * 1024:  # 10MB limit
                self.logger.warning(
                    "Response buffer exceeded 10MB, clearing to prevent memory leak"
                )
                self.response_buffer = ""
                return resp

            # Look for complete JSON objects in the buffer
            pattern = rb'\[\[\[null,.*?]],"model"]'

            # Convert buffer to bytes for pattern matching
            buffer_bytes = self.response_buffer.encode("utf-8")
            matches = list(re.finditer(pattern, buffer_bytes))

            # Debug: Log match count when processing is done
            if is_done and matches and FUNCTION_CALLING_DEBUG:
                self.logger.debug(
                    f"[FC:Wire] Found {len(matches)} wire format matches in buffer"
                )

            if matches:
                # Process all complete matches found in buffer
                for match in matches:
                    try:
                        json_data = json.loads(match.group(0))
                        payload = json_data[0][0]

                        # Debug: Log payload structure for function call detection
                        if len(payload) >= 10 and FUNCTION_CALLING_DEBUG:
                            self.logger.debug(
                                f"[FC:Wire] Payload len={len(payload)}, [1]={payload[1]}, "
                                f"has [10]={len(payload) > 10 and isinstance(payload[10], list)}"
                            )

                        if len(payload) == 2:  # body
                            resp["body"] += payload[1]
                        elif (
                            len(payload) == 11
                            and payload[1] is None
                            and isinstance(payload[10], list)
                        ):  # function
                            array_tool_calls = payload[10]
                            func_name = array_tool_calls[0]
                            raw_args = array_tool_calls[1]
                            # Log raw wire format for debugging
                            if FUNCTION_CALLING_DEBUG:
                                self.logger.debug(
                                    f"[FC:Wire] Raw args for '{func_name}': {json.dumps(raw_args)[:500]}"
                                )
                            params = self.parse_toolcall_params(raw_args)
                            # Log warning if params are empty for tracking potential parse failures
                            if not params:
                                if FUNCTION_CALLING_DEBUG:
                                    self.logger.warning(
                                        f"[FC:Wire] Function '{func_name}' parsed with empty args - "
                                        f"may indicate wire format parsing failure. Raw: {array_tool_calls[1][:200] if array_tool_calls[1] else 'None'}..."
                                    )
                                    fc_logger.log_wire_parse(
                                        req_id="",
                                        func_name=func_name,
                                        params=params,
                                        success=False,
                                    )
                            else:
                                if FUNCTION_CALLING_DEBUG:
                                    fc_logger.log_wire_parse(
                                        req_id="",
                                        func_name=func_name,
                                        params=params,
                                        success=True,
                                    )
                            resp["function"].append(
                                {"name": func_name, "params": params}
                            )
                        elif len(payload) > 2:  # reason
                            resp["reason"] += payload[1]

                    except (json.JSONDecodeError, IndexError, TypeError) as e:
                        self.logger.debug(f"Failed to parse JSON chunk: {e}")
                        continue

                # Remove processed data from buffer
                last_match_end = matches[-1].end()
                if last_match_end < len(buffer_bytes):
                    remaining_bytes = buffer_bytes[last_match_end:]
                    self.response_buffer = remaining_bytes.decode(
                        "utf-8", errors="ignore"
                    )
                else:
                    self.response_buffer = ""
            else:
                self.logger.debug("Buffering incomplete JSON data...")

        except UnicodeDecodeError as e:
            self.logger.debug(f"Unicode decode error in buffer parsing: {e}")
            self.response_buffer = ""
        except Exception as e:
            self.logger.debug(f"Error in buffer parsing: {e}")

        return resp

    def _unwrap_to_param_list(
        self, args: Any, max_depth: int = 10
    ) -> Optional[List[Any]]:
        """Unwrap nested lists until we find the actual parameter list.

        A parameter list is a list where each element is a [name, value] tuple
        and the name (first element) is a string.

        Args:
            args: The nested structure to unwrap.
            max_depth: Maximum unwrap depth to prevent infinite loops.

        Returns:
            The parameter list, or None if not found.
        """
        current = args
        for _ in range(max_depth):
            if not isinstance(current, list) or len(current) == 0:
                return None

            # Check if current is already a param list
            # A param list is a list of [string_name, value] tuples
            first_elem = current[0]
            if isinstance(first_elem, list) and len(first_elem) >= 2:
                # Check if first element of first tuple is a string (param name)
                if isinstance(first_elem[0], str):
                    # This is the param list!
                    return current

            # Not a param list yet, unwrap one level
            if isinstance(current[0], list):
                current = current[0]
            else:
                # Can't unwrap further
                return None

        self.logger.warning(f"Max unwrap depth reached for args: {args}")
        return None

    def parse_toolcall_params(self, args: Any) -> Dict[str, Any]:
        """Parse function call parameters from AI Studio's wire format.

        AI Studio uses a type-length encoding:
        - Length 1: null
        - Length 2: number/integer
        - Length 3: string
        - Length 4: boolean
        - Length 5: object (nested structure)
        - Length 6: array

        The wire format has variable nesting levels. We unwrap until we find
        the actual parameter tuples (where first element is a string).
        """
        try:
            # Unwrap nested lists until we find the parameter list
            # A parameter list is a list of [name, value] tuples where name is a string
            params = self._unwrap_to_param_list(args)
            if params is None:
                self.logger.warning(f"Could not find param list in args: {args}")
                return {}

            func_params = {}
            for param in params:
                param_name = param[0]
                param_value = param[1]

                # Debug: log raw param_value structure
                self.logger.debug(
                    f"Parsing param '{param_name}': type={type(param_value).__name__}, "
                    f"len={len(param_value) if isinstance(param_value, list) else 'N/A'}, "
                    f"value={str(param_value)[:100]}"
                )

                if isinstance(param_value, list):
                    if len(param_value) == 1:  # null
                        func_params[param_name] = None
                    elif len(param_value) == 2:  # number and integer
                        func_params[param_name] = param_value[1]
                    elif len(param_value) == 3:  # string
                        func_params[param_name] = param_value[2]
                    elif len(param_value) == 4:  # boolean
                        func_params[param_name] = param_value[3] == 1
                    elif len(param_value) == 5:  # object
                        func_params[param_name] = self.parse_toolcall_params(
                            param_value[4]
                        )
                    elif len(param_value) == 6:  # array
                        # Arrays are at index 5, containing list of encoded items
                        array_items = param_value[5]
                        if isinstance(array_items, list):
                            func_params[param_name] = self._parse_array_items(
                                array_items
                            )
                        else:
                            func_params[param_name] = []
                    else:
                        # Unknown type - log and store raw value
                        self.logger.debug(
                            f"Unknown param type length {len(param_value)} for {param_name}"
                        )
                        func_params[param_name] = param_value
                else:
                    # Non-list value - store directly
                    self.logger.debug(
                        f"Non-list param value for {param_name}: {type(param_value)}"
                    )
                    func_params[param_name] = param_value
            return func_params
        except Exception as e:
            self.logger.debug(f"Error parsing toolcall params: {e}")
            raise e

    def _parse_array_items(self, array_items: List[Any]) -> List[Any]:
        """Parse array items from AI Studio's wire format.

        Each item in the array follows the same type encoding as parameters.
        The wire format uses variable nesting levels, so we must handle:
        - Direct type-encoded items: [null], [null, num], [null, null, str], etc.
        - Wrapped items: [[...actual item...]] - extra nesting layer
        - Object items with param lists inside
        """
        self.logger.debug(
            f"_parse_array_items input (len={len(array_items)}): {array_items[:3] if len(array_items) > 3 else array_items}"
        )
        result = []
        for i, item in enumerate(array_items):
            self.logger.debug(f"  Array item[{i}] raw: {item}")
            parsed = self._parse_single_array_item(item)
            self.logger.debug(f"  Array item[{i}] parsed: {parsed}")
            result.append(parsed)
        return result

    def _parse_single_array_item(self, item: Any) -> Any:
        """Parse a single array item, handling variable nesting depth.

        This method recursively unwraps nested structures until it finds
        a recognizable type-encoded value or a parameter list (object).
        """
        if not isinstance(item, list):
            return item

        if len(item) == 0:
            return None

        # PRIORITY CHECK: Is this a param list (object)?
        # A param list is [[name, value], [name, value], ...]
        # This must be checked BEFORE length-based type decoding
        if self._looks_like_param_list(item):
            return self.parse_toolcall_params([item])

        # Check for type-encoded values based on structure
        # Type-encoded values have None/value patterns at specific positions

        # Length 1: Could be null OR a wrapper containing nested data
        if len(item) == 1:
            inner = item[0]
            # If inner is a list, this is a wrapper - unwrap and recurse
            if isinstance(inner, list):
                return self._parse_single_array_item(inner)
            # If inner is None or non-list, this is a null value
            return None

        # Length 2: number/integer - [null, value]
        if len(item) == 2:
            if item[0] is None and item[1] is not None:
                return item[1]
            # Could be a 2-element wrapper or 2-element param list (already handled above)
            if isinstance(item[0], list):
                return self._parse_single_array_item(item[0])
            return item[1]

        # Length 3: string - [null, null, value]
        if len(item) == 3:
            if item[0] is None and item[1] is None:
                return item[2]
            # Could be wrapper
            if isinstance(item[0], list):
                return self._parse_single_array_item(item[0])
            return item[2]

        # Length 4: boolean - [null, null, null, 0|1]
        if len(item) == 4:
            if item[0] is None and item[1] is None and item[2] is None:
                return item[3] == 1
            # Could be wrapper
            if isinstance(item[0], list):
                return self._parse_single_array_item(item[0])
            return item[3] == 1

        # Length 5: object - [null, null, null, null, params]
        if len(item) == 5:
            if item[4] is not None:
                return self.parse_toolcall_params(item[4])
            return {}

        # Length 6: nested array - [null, null, null, null, null, items]
        if len(item) == 6:
            nested_items = item[5]
            if isinstance(nested_items, list):
                return self._parse_array_items(nested_items)
            return []

        # Unknown structure - try to unwrap first element if it's a list
        if isinstance(item[0], list):
            return self._parse_single_array_item(item[0])

        # Fallback: return as-is
        self.logger.debug(
            f"Unknown array item structure (len={len(item)}): {item[:3]}..."
        )
        return item

    def _looks_like_param_list(self, data: Any) -> bool:
        """Check if data looks like a parameter list (list of [name, value] tuples).

        A param list is a list where elements are [string_name, encoded_value] tuples.
        """
        if not isinstance(data, list) or len(data) == 0:
            return False

        # Check first element - should be a list with string as first element
        first = data[0]
        if isinstance(first, list) and len(first) >= 2:
            if isinstance(first[0], str):
                return True

        return False

    @staticmethod
    def _decompress_zlib_stream(compressed_stream: Union[bytearray, bytes]) -> bytes:
        decompressor = zlib.decompressobj(wbits=zlib.MAX_WBITS | 32)
        decompressed = decompressor.decompress(compressed_stream)
        return decompressed

    @staticmethod
    def _decode_chunked(response_body: bytes) -> Tuple[bytes, bool]:
        chunked_data = bytearray()
        while True:
            length_crlf_idx = response_body.find(b"\r\n")
            if length_crlf_idx == -1:
                break

            hex_length = response_body[:length_crlf_idx]
            try:
                length = int(hex_length, 16)
            except ValueError as e:
                logging.error(f"Parsing chunked length failed: {e}")
                break

            if length == 0:
                length_crlf_idx = response_body.find(b"0\r\n\r\n")
                if length_crlf_idx != -1:
                    return bytes(chunked_data), True

            if length + 2 > len(response_body):
                break

            chunked_data.extend(
                response_body[length_crlf_idx + 2 : length_crlf_idx + 2 + length]
            )
            if length_crlf_idx + 2 + length + 2 > len(response_body):
                break

            response_body = response_body[length_crlf_idx + 2 + length + 2 :]
        return bytes(chunked_data), False
