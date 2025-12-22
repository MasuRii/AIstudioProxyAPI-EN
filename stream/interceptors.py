import json
import logging
import re
import sys
import zlib
from typing import Any, Dict, Tuple, Union
from urllib.parse import unquote

from config.global_state import GlobalState
from logging_utils.grid_logger import GridFormatter


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

            if matches:
                # Process all complete matches found in buffer
                for match in matches:
                    try:
                        json_data = json.loads(match.group(0))
                        payload = json_data[0][0]

                        if len(payload) == 2:  # body
                            resp["body"] += payload[1]
                        elif (
                            len(payload) == 11
                            and payload[1] is None
                            and type(payload[10]) == list
                        ):  # function
                            array_tool_calls = payload[10]
                            func_name = array_tool_calls[0]
                            params = self.parse_toolcall_params(array_tool_calls[1])
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

    def parse_toolcall_params(self, args: Any) -> Dict[str, Any]:
        try:
            params = args[0]
            func_params = {}
            for param in params:
                param_name = param[0]
                param_value = param[1]

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
            return func_params
        except Exception as e:
            raise e

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
