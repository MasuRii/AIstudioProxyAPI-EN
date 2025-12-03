from typing import Any, Dict, List, Optional


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    chinese_chars = sum(
        1
        for char in text
        if "\u4e00" <= char <= "\u9fff"
        or "\u3000" <= char <= "\u303f"
        or "\uff00" <= char <= "\uffef"
    )
    non_chinese_chars = len(text) - chinese_chars
    chinese_tokens = chinese_chars / 1.5
    english_tokens = non_chinese_chars / 4.0
    return max(1, int(chinese_tokens + english_tokens))


def calculate_usage_stats(
    messages: List[Dict[str, Any]],
    response_content: str,
    reasoning_content: Optional[str] = None,
) -> Dict[str, int]:
    prompt_text = ""
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        prompt_text += f"{role}: {content}\n"
    prompt_tokens = estimate_tokens(prompt_text)

    completion_text = response_content or ""
    if reasoning_content:
        completion_text += reasoning_content
    completion_tokens = estimate_tokens(completion_text)
    total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
