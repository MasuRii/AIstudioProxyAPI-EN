import unittest
import json
from api_utils.utils_ext.function_calling import (
    SchemaConverter,
    ResponseFormatter,
    ParsedFunctionCall,
    SchemaConversionError,
)


class TestFunctionCallingCore(unittest.TestCase):
    def setUp(self):
        self.converter = SchemaConverter()
        self.formatter = ResponseFormatter()

    def test_schema_converter_basic(self):
        """Test basic conversion of OpenAI tool definition to Gemini format."""
        openai_tool = {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            },
        }
        expected = {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        }
        result = self.converter.convert_tool(openai_tool)
        self.assertEqual(result, expected)

    def test_schema_converter_strips_unsupported_fields(self):
        """Test that SchemaConverter strips 'strict' and other unsupported fields."""
        openai_tool = {
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state",
                        }
                    },
                    "required": ["location"],
                    "strict": True,
                },
                "strict": True,
            },
        }
        result = self.converter.convert_tool(openai_tool)
        self.assertNotIn("strict", result)
        self.assertNotIn("strict", result["parameters"])
        self.assertEqual(result["name"], "get_weather")
        self.assertEqual(
            result["parameters"]["properties"]["location"]["type"], "string"
        )

    def test_schema_converter_invalid_input(self):
        """Test SchemaConverter handles invalid inputs gracefully."""
        # Not a dict
        with self.assertRaises(SchemaConversionError):
            self.converter.convert_tool("not a dict")

        # Missing function field
        with self.assertRaises(SchemaConversionError):
            self.converter.convert_tool({"type": "function"})

        # Wrong type
        with self.assertRaises(SchemaConversionError):
            self.converter.convert_tool({"type": "code_interpreter", "function": {}})

    def test_response_formatter_format_tool_call(self):
        """Test formatting a single ParsedFunctionCall to OpenAI tool_call format."""
        parsed_call = ParsedFunctionCall(
            name="get_weather", arguments={"location": "San Francisco, CA"}
        )
        call_id = "call_abc123"

        result = self.formatter.format_tool_call(parsed_call, call_id=call_id)

        self.assertEqual(result["id"], call_id)
        self.assertEqual(result["type"], "function")
        self.assertEqual(result["function"]["name"], "get_weather")
        # OpenAI expects arguments as a JSON string
        self.assertEqual(
            json.loads(result["function"]["arguments"]),
            {"location": "San Francisco, CA"},
        )

    def test_response_formatter_auto_id_generation(self):
        """Test that ResponseFormatter generates unique IDs if not provided."""
        parsed_call = ParsedFunctionCall(name="test_func", arguments={})
        result1 = self.formatter.format_tool_call(parsed_call)
        result2 = self.formatter.format_tool_call(parsed_call)

        self.assertTrue(result1["id"].startswith("call_"))
        self.assertTrue(result2["id"].startswith("call_"))
        self.assertNotEqual(result1["id"], result2["id"])

    def test_response_formatter_format_tool_calls(self):
        """Test formatting multiple parsed calls at once."""
        parsed_calls = [
            ParsedFunctionCall(name="func1", arguments={"a": 1}),
            ParsedFunctionCall(name="func2", arguments={"b": 2}),
        ]
        results = self.formatter.format_tool_calls(parsed_calls)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["function"]["name"], "func1")
        self.assertEqual(results[1]["function"]["name"], "func2")

    def test_response_formatter_streaming_chunks(self):
        """Test that format_streaming_chunks produces valid delta chunks."""
        parsed_call = ParsedFunctionCall(
            name="get_weather", arguments={"location": "SF"}
        )
        # Use small chunk size to force multiple chunks
        chunks = self.formatter.format_streaming_chunks(
            index=0, parsed_call=parsed_call, chunk_size=5
        )

        # At least 1 metadata chunk + N argument chunks
        self.assertGreater(len(chunks), 2)

        # First chunk should have index, id, type, and function name
        self.assertEqual(chunks[0]["index"], 0)
        self.assertIn("id", chunks[0])
        self.assertEqual(chunks[0]["type"], "function")
        self.assertEqual(chunks[0]["function"]["name"], "get_weather")
        self.assertNotIn("arguments", chunks[0]["function"])

        # Subsequent chunks should have arguments fragments
        self.assertIn("arguments", chunks[1]["function"])

        # Combine all argument fragments
        combined_args = ""
        for chunk in chunks:
            if "function" in chunk and "arguments" in chunk["function"]:
                combined_args += chunk["function"]["arguments"]

        self.assertEqual(json.loads(combined_args), {"location": "SF"})


if __name__ == "__main__":
    unittest.main()
