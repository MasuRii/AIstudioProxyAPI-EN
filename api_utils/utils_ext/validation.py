from typing import Dict, List, Optional

from models import Message


def validate_chat_request(
    messages: List[Message], req_id: str
) -> Dict[str, Optional[str]]:
    if not messages:
        raise ValueError(f"[{req_id}] 无效请求: 'messages' 数组缺失或为空。")

    if not any(msg.role != "system" for msg in messages):
        raise ValueError(
            f"[{req_id}] 无效请求: 所有消息都是系统消息。至少需要一条用户或助手消息。"
        )

    return {"error": None, "warning": None}
