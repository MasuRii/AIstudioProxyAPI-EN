import json
import logging
from typing import Any, Dict, List, Optional


def clean_and_parse_json_string(
    obj: Any, logger: Optional[logging.Logger] = None, req_id: str = ""
) -> Any:
    """Recursively parse JSON strings within a data structure.

    Handles:
    - Malformed double-encoded JSON (extra trailing '}' or ']')
    - Escaped string content (\\n, \\t, etc.)
    - "Extra data" JSON errors
    """
    if isinstance(obj, dict):
        return {
            k: clean_and_parse_json_string(v, logger, req_id) for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [clean_and_parse_json_string(i, logger, req_id) for i in obj]
    elif isinstance(obj, str):
        stripped = obj.strip()

        # Check if string contains control character escape sequences that need unescaping
        # This handles cases where diff content has literal \n or \t instead of actual newlines/tabs
        has_control_char_escapes = "\\n" in obj or "\\t" in obj
        has_intentional_escapes = '\\"' in obj or "\\\\" in obj

        if has_control_char_escapes and not has_intentional_escapes:
            try:
                # Use json.loads with quotes to properly unescape the string
                unescaped = json.loads(f'"{obj}"')
                if logger:
                    snippet = obj[:80] + "..." if len(obj) > 80 else obj
                    logger.debug(
                        f"[{req_id}] Unescaped control chars in string: "
                        f"{len(obj) - len(unescaped)} chars changed. Snippet: {snippet!r}"
                    )
                return unescaped
            except (json.JSONDecodeError, ValueError):
                pass

        if stripped and stripped[0] in ("{", "["):
            try:
                parsed = json.loads(obj)
                return clean_and_parse_json_string(parsed, logger, req_id)
            except json.JSONDecodeError as e:
                # Handle "Extra data" (e.g. {"key": "value"}} or [1, 2]]garbage)
                if e.msg.startswith("Extra data"):
                    try:
                        cleaned = obj[: e.pos]
                        parsed = json.loads(cleaned)
                        if logger:
                            logger.warning(
                                f"[{req_id}] Auto-corrected malformed JSON string (Extra data): "
                                f"truncated at pos {e.pos}"
                            )
                        return clean_and_parse_json_string(parsed, logger, req_id)
                    except Exception:
                        pass
            except ValueError:
                pass

            # Handle malformed JSON: array that doesn't end with ]
            # e.g., '[{"path": "..."}]}' instead of '[{"path": "..."}]'
            # We check startswith but NOT endswith to allow recovery even if it ends with "incorrect" bracket
            if stripped.startswith("["):
                try:
                    last_bracket = stripped.rfind("]")
                    if last_bracket > 0:
                        cleaned = stripped[: last_bracket + 1]
                        # Only try if we actually changed something
                        if len(cleaned) < len(stripped):
                            parsed = json.loads(cleaned)
                            if logger:
                                logger.warning(
                                    f"[{req_id}] Auto-corrected malformed JSON string (Array): "
                                    f"truncated {len(stripped) - len(cleaned)} extra chars"
                                )
                            return clean_and_parse_json_string(parsed, logger, req_id)
                except (json.JSONDecodeError, ValueError):
                    pass

            # Handle malformed JSON: object that doesn't end with }
            if stripped.startswith("{"):
                try:
                    last_brace = stripped.rfind("}")
                    if last_brace > 0:
                        cleaned = stripped[: last_brace + 1]
                        if len(cleaned) < len(stripped):
                            parsed = json.loads(cleaned)
                            if logger:
                                logger.warning(
                                    f"[{req_id}] Auto-corrected malformed JSON string (Object): "
                                    f"truncated {len(stripped) - len(cleaned)} extra chars"
                                )
                            return clean_and_parse_json_string(parsed, logger, req_id)
                except (json.JSONDecodeError, ValueError):
                    pass
    return obj
