import requests
import json
import sys
import time


def verify_native_fc_e2e():
    """
    E2E verification script for Native Function Calling.

    This script connects to a running local proxy and sends a request with tool definitions
    to verify that the proxy correctly handles the request and returns tool calls.
    """
    base_url = "http://127.0.0.1:2048"
    chat_url = f"{base_url}/v1/chat/completions"
    health_url = f"{base_url}/health"

    print(f"--- Native Function Calling E2E Verification ---")

    # 1. Check if proxy is running
    print(f"Checking proxy health at {health_url}...")
    try:
        health_resp = requests.get(health_url, timeout=5)
        if health_resp.status_code == 200:
            print(f"Proxy is UP. Status: {health_resp.json().get('status', 'Unknown')}")
        else:
            print(f"Proxy health check failed with status {health_resp.status_code}.")
            print(
                "Please ensure the proxy server is running before executing this script."
            )
            return
    except requests.exceptions.ConnectionError:
        print(f"CRITICAL: Could not connect to proxy at {base_url}.")
        print("Please start the proxy server (e.g., python server.py) first.")
        return
    except Exception as e:
        print(f"Warning: Health check failed with error: {e}")
        # Continue anyway, health check might not be implemented exactly as expected

    # 2. Prepare request with tools
    headers = {"Content-Type": "application/json", "Authorization": "Bearer any-key"}

    payload = {
        "model": "gemini-3-flash-preview",
        "messages": [
            {"role": "user", "content": "What is the weather in Tokyo and Paris?"}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather in a given location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA",
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                            },
                        },
                        "required": ["location"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
    }

    print(f"\nSending request to {chat_url}...")
    print(f"Tools defined: {[t['function']['name'] for t in payload['tools']]}")

    start_time = time.time()
    try:
        response = requests.post(chat_url, headers=headers, json=payload, timeout=60)
        duration = time.time() - start_time

        print(f"Response received in {duration:.2f}s (Status: {response.status_code})")

        if response.status_code == 200:
            data = response.json()
            message = data["choices"][0]["message"]

            if "tool_calls" in message:
                tool_calls = message["tool_calls"]
                print(f"\nSUCCESS: Received {len(tool_calls)} tool call(s)")
                for i, call in enumerate(tool_calls):
                    func_name = call["function"]["name"]
                    args = call["function"]["arguments"]
                    print(f"  Call #{i + 1}: {func_name}({args})")

                # Verify format
                if all(k in tool_calls[0] for k in ["id", "type", "function"]):
                    print("  Format verification: PASSED (OpenAI compatible)")
                else:
                    print("  Format verification: FAILED (Missing required fields)")
            else:
                print("\nFAILURE: No tool calls received.")
                if "content" in message and message["content"]:
                    print(f"  Assistant Content: {message['content']}")
                else:
                    print("  Response was empty.")
        else:
            print(f"\nERROR: Request failed with status {response.status_code}")
            print(f"Response: {response.text}")

    except requests.exceptions.Timeout:
        print(f"\n❌ ERROR: Request timed out after 60s.")
    except Exception as e:
        print(f"\n❌ ERROR: An unexpected error occurred: {e}")


if __name__ == "__main__":
    verify_native_fc_e2e()
