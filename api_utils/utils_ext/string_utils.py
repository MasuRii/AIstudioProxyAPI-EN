import json
from typing import List, Optional

from models import Message


def extract_json_from_text(text: str) -> Optional[str]:
    """Attempt to extract the first JSON object string from plain text."""
    if not text:
        return None
    # Simple heuristic: find the first '{' and the last matching '}'
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1].strip()
            json.loads(candidate)
            return candidate
    except Exception:
        return None
    return None


def get_latest_user_text(messages: List[Message]) -> str:
    """Extract the text content of the most recent user message (concatenating multiple text segments)."""
    for msg in reversed(messages):
        if msg.role == "user":
            content = msg.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                parts: List[str] = []
                for it in content:
                    if isinstance(it, dict):
                        if it.get("type") == "text":
                            text_raw = it.get("text", "")
                            if isinstance(text_raw, str):
                                parts.append(text_raw)
                            else:
                                parts.append(str(text_raw))
                    elif hasattr(it, "type") and it.type == "text":
                        text_attr = getattr(it, "text", "")
                        if isinstance(text_attr, str):
                            parts.append(text_attr)
                        else:
                            parts.append(str(text_attr))
                return "\n".join(p for p in parts if p)
            else:
                return ""
    return ""
