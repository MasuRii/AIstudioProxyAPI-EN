import json

def convert_to_gemini_schema(openai_tools):
    """
    Converts OpenAI tool definitions to Gemini AI Studio JSON format.
    """
    gemini_tools = []
    if not openai_tools:
        return "[]"
        
    for tool in openai_tools:
        if tool.get("type") == "function":
            fn = tool.get("function", {})
            gemini_tool = {
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {})
            }
            gemini_tools.append(gemini_tool)
            
    return json.dumps(gemini_tools, indent=2)