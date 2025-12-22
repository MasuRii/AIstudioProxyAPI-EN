import argparse  # New import
import json
import logging
import sys  # New import
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import requests
from flask import Flask, jsonify, request


# Custom Log Handler, ensuring flush
class FlushingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            super().emit(record)
            self.flush()
        except Exception:
            self.handleError(record)


# Configure logging
log_format = "%(asctime)s [%(levelname)s] %(message)s"
formatter = logging.Formatter(log_format)

# Create a handler explicitly pointing to sys.stderr and using custom FlushingStreamHandler
# sys.stderr should be captured by gui_launcher.py's PIPE in subprocess
stderr_handler = FlushingStreamHandler(sys.stderr)
stderr_handler.setFormatter(formatter)
stderr_handler.setLevel(logging.INFO)

# Get root logger and add our handler
# This ensures all logs propagated to root logger (including Flask and Werkzeug, if they don't have specific handlers)
# will pass through this handler.
root_logger = logging.getLogger()
# Clear potential default handlers added by basicConfig or other libraries to avoid duplicate logs or unexpected output
if root_logger.hasHandlers():
    root_logger.handlers.clear()
root_logger.addHandler(stderr_handler)
root_logger.setLevel(logging.INFO)  # Ensure root logger level is set

logger = logging.getLogger(
    __name__
)  # Get logger named 'llm', inheriting root logger config

app = Flask(__name__)
# Flask's app.logger propagates to root logger by default.
# If needed, app.logger and werkzeug logger can be configured separately, but propagating to root is usually sufficient.
# Example:
# app.logger.handlers.clear() # Clear default handler possibly added by Flask
# app.logger.addHandler(stderr_handler)
# app.logger.setLevel(logging.INFO)
#
# werkzeug_logger = logging.getLogger('werkzeug')
# werkzeug_logger.handlers.clear()
# werkzeug_logger.addHandler(stderr_handler)
# werkzeug_logger.setLevel(logging.INFO)

# Enable model configuration: directly define enabled model names
# Users can add/remove model names, metadata is generated dynamically
ENABLED_MODELS = {
    "gemini-2.5-pro-preview-05-06",
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
}

# API Configuration
API_URL = ""  # Will be set in main function based on arguments
DEFAULT_MAIN_SERVER_PORT = 2048
# Please replace with your API Key (Do not share publicly)
API_KEY = "123456"

# Mock Ollama chat response database
OLLAMA_MOCK_RESPONSES = {
    "What is the capital of France?": "The capital of France is Paris.",
    "Tell me about AI.": "AI is the simulation of human intelligence in machines, enabling tasks like reasoning and learning.",
    "Hello": "Hi! How can I assist you today?",
}


@app.route("/", methods=["GET"])
def root_endpoint():
    """Mock Ollama root path, returns 'Ollama is running'"""
    logger.info("Received root path request")
    return "Ollama is running", 200


@app.route("/api/tags", methods=["GET"])
def tags_endpoint():
    """Mock Ollama /api/tags endpoint, dynamically generating enabled model list"""
    logger.info("Received /api/tags request")
    models = []
    for model_name in ENABLED_MODELS:
        # Derive family: extract prefix from model name (e.g. "gpt-4o" -> "gpt")
        family = (
            model_name.split("-")[0].lower()
            if "-" in model_name
            else model_name.lower()
        )
        # Special handling for known models
        if "llama" in model_name:
            family = "llama"
            format = "gguf"
            size = 1234567890
            parameter_size = "405B" if "405b" in model_name else "unknown"
            quantization_level = "Q4_0"
        elif "mistral" in model_name:
            family = "mistral"
            format = "gguf"
            size = 1234567890
            parameter_size = "unknown"
            quantization_level = "unknown"
        else:
            format = "unknown"
            size = 9876543210
            parameter_size = "unknown"
            quantization_level = "unknown"

        models.append(
            {
                "name": model_name,
                "model": model_name,
                "modified_at": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                "size": size,
                "digest": str(uuid.uuid4()),
                "details": {
                    "parent_model": "",
                    "format": format,
                    "family": family,
                    "families": [family],
                    "parameter_size": parameter_size,
                    "quantization_level": quantization_level,
                },
            }
        )
    logger.info(f"Returning {len(models)} models: {[m['name'] for m in models]}")
    return jsonify({"models": models}), 200


def generate_ollama_mock_response(prompt: str, model: str) -> Dict[str, Any]:
    """Generate mock Ollama chat response, conforming to /api/chat format"""
    response_content = OLLAMA_MOCK_RESPONSES.get(
        prompt, f"Echo: {prompt} (This is a response from the mock Ollama server.)"
    )

    return {
        "model": model,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "message": {"role": "assistant", "content": response_content},
        "done": True,
        "total_duration": 123456789,
        "load_duration": 1234567,
        "prompt_eval_count": 10,
        "prompt_eval_duration": 2345678,
        "eval_count": 20,
        "eval_duration": 3456789,
    }


def convert_api_to_ollama_response(
    api_response: Dict[str, Any], model: str
) -> Dict[str, Any]:
    """Convert API's OpenAI format response to Ollama format"""
    try:
        content = api_response["choices"][0]["message"]["content"]
        total_duration = api_response.get("usage", {}).get("total_tokens", 30) * 1000000
        prompt_tokens = api_response.get("usage", {}).get("prompt_tokens", 10)
        completion_tokens = api_response.get("usage", {}).get("completion_tokens", 20)

        return {
            "model": model,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "message": {"role": "assistant", "content": content},
            "done": True,
            "total_duration": total_duration,
            "load_duration": 1234567,
            "prompt_eval_count": prompt_tokens,
            "prompt_eval_duration": prompt_tokens * 100000,
            "eval_count": completion_tokens,
            "eval_duration": completion_tokens * 100000,
        }
    except KeyError as e:
        logger.error(f"Failed to convert API response: Missing key {str(e)}")
        return {"error": f"Invalid API response format: Missing key {str(e)}"}


def print_request_params(data: Dict[str, Any], endpoint: str) -> None:
    """Print request parameters"""
    model = data.get("model", "unspecified")
    temperature = data.get("temperature", "unspecified")
    stream = data.get("stream", False)

    messages_info = []
    for msg in data.get("messages", []):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        content_preview = content[:50] + "..." if len(content) > 50 else content
        messages_info.append(f"[{role}] {content_preview}")

    params_str = {
        "Endpoint": endpoint,
        "Model": model,
        "Temperature": temperature,
        "Stream": stream,
        "Message Count": len(data.get("messages", [])),
        "Messages Preview": messages_info,
    }

    logger.info(
        f"Request Parameters: {json.dumps(params_str, ensure_ascii=False, indent=2)}"
    )


@app.route("/api/chat", methods=["POST"])
def ollama_chat_endpoint():
    """Mock Ollama /api/chat endpoint, available for all models"""
    try:
        data = request.get_json()
        if not data or "messages" not in data:
            logger.error("Invalid request: Missing 'messages' field")
            return jsonify({"error": "Invalid request: Missing 'messages' field"}), 400

        messages = data.get("messages", [])
        if not messages or not isinstance(messages, list):
            logger.error("Invalid request: 'messages' must be a non-empty list")
            return jsonify(
                {"error": "Invalid request: 'messages' must be a non-empty list"}
            ), 400

        model = data.get("model", "llama3.2")
        user_message = next(
            (msg["content"] for msg in reversed(messages) if msg.get("role") == "user"),
            "",
        )
        if not user_message:
            logger.error("User message not found")
            return jsonify({"error": "User message not found"}), 400

        # Print request parameters
        print_request_params(data, "/api/chat")

        logger.info(f"Processing /api/chat request, model: {model}")

        # Remove model restriction, all models use API
        api_request = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": data.get("temperature", 0.7),
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }

        try:
            logger.info(f"Forwarding request to API: {API_URL}")
            response = requests.post(
                API_URL, json=api_request, headers=headers, timeout=300000
            )
            response.raise_for_status()
            api_response = response.json()
            ollama_response = convert_api_to_ollama_response(api_response, model)
            logger.info(f"Received response from API, model: {model}")
            return jsonify(ollama_response), 200
        except requests.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            # If API request fails, use mock response as fallback
            logger.info(f"Using mock response as fallback, model: {model}")
            response = generate_ollama_mock_response(user_message, model)
            return jsonify(response), 200

    except Exception as e:
        logger.error(f"/api/chat Server Error: {str(e)}")
        return jsonify({"error": f"Server Error: {str(e)}"}), 500


@app.route("/v1/chat/completions", methods=["POST"])
def api_chat_endpoint():
    """Forward to API's /v1/chat/completions endpoint and convert to Ollama format"""
    try:
        data = request.get_json()
        if not data or "messages" not in data:
            logger.error("Invalid request: Missing 'messages' field")
            return jsonify({"error": "Invalid request: Missing 'messages' field"}), 400

        messages = data.get("messages", [])
        if not messages or not isinstance(messages, list):
            logger.error("Invalid request: 'messages' must be a non-empty list")
            return jsonify(
                {"error": "Invalid request: 'messages' must be a non-empty list"}
            ), 400

        model = data.get("model", "grok-3")
        user_message = next(
            (msg["content"] for msg in reversed(messages) if msg.get("role") == "user"),
            "",
        )
        if not user_message:
            logger.error("User message not found")
            return jsonify({"error": "User message not found"}), 400

        # Print request parameters
        print_request_params(data, "/v1/chat/completions")

        logger.info(f"Processing /v1/chat/completions request, model: {model}")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }

        try:
            logger.info(f"Forwarding request to API: {API_URL}")
            response = requests.post(
                API_URL, json=data, headers=headers, timeout=300000
            )
            response.raise_for_status()
            api_response = response.json()
            ollama_response = convert_api_to_ollama_response(api_response, model)
            logger.info(f"Received response from API, model: {model}")
            return jsonify(ollama_response), 200
        except requests.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            return jsonify({"error": f"API request failed: {str(e)}"}), 500

    except Exception as e:
        logger.error(f"/v1/chat/completions Server Error: {str(e)}")
        return jsonify({"error": f"Server Error: {str(e)}"}), 500


def main():
    """Start mock server"""
    global API_URL  # Declare that we are modifying global variables

    parser = argparse.ArgumentParser(description="LLM Mock Service for AI Studio Proxy")
    parser.add_argument(
        "--main-server-port",
        type=int,
        default=DEFAULT_MAIN_SERVER_PORT,
        help=f"Port of the main AI Studio Proxy server (default: {DEFAULT_MAIN_SERVER_PORT})",
    )
    args = parser.parse_args()

    API_URL = f"http://localhost:{args.main_server_port}/v1/chat/completions"

    logger.info(f"Mock Ollama and API proxy server will forward requests to: {API_URL}")
    logger.info("Starting Mock Ollama and API proxy server at: http://localhost:11434")
    app.run(host="0.0.0.0", port=11434, debug=False)


if __name__ == "__main__":
    main()
