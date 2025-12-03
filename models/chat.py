from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

from config import MODEL_NAME


class FunctionCall(BaseModel):
    name: str
    arguments: str


class ToolCall(BaseModel):
    id: str
    type: str = "function"
    function: FunctionCall


class ImageURL(BaseModel):
    url: str
    # OpenAI 兼容: detail 可为 'auto' | 'low' | 'high'
    detail: Optional[str] = None


class AudioInput(BaseModel):
    # 允许 url 或 data 二选一
    url: Optional[str] = None
    data: Optional[str] = None  # Base64 或 data:URL
    format: Optional[str] = None  # 如 'wav', 'mp3'
    mime_type: Optional[str] = None  # 如 'audio/wav'


class VideoInput(BaseModel):
    url: Optional[str] = None
    data: Optional[str] = None
    format: Optional[str] = None
    mime_type: Optional[str] = None


class URLRef(BaseModel):
    url: str


class MessageContentItem(BaseModel):
    type: str
    text: Optional[str] = None
    image_url: Optional[ImageURL] = None
    # 新增对 input_image 的支持（OpenAI 兼容）
    input_image: Optional[ImageURL] = None
    # 扩展支持通用 file_url/media_url 以及直接 url 字段，保持兼容 OpenAI 风格
    file_url: Optional[URLRef] = None
    media_url: Optional[URLRef] = None
    url: Optional[str] = None
    # 扩展支持 input_audio/input_video
    input_audio: Optional[AudioInput] = None
    input_video: Optional[VideoInput] = None


class Message(BaseModel):
    role: str
    content: Union[str, List[MessageContentItem], None] = None
    name: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    # 兼容第三方客户端在消息级传附件的用法（非标准但常见）
    attachments: Optional[List[Any]] = None
    images: Optional[List[Any]] = None
    files: Optional[List[Any]] = None
    media: Optional[List[Any]] = None


class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = MODEL_NAME
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    top_p: Optional[float] = None
    reasoning_effort: Optional[Union[str, int]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    seed: Optional[int] = None
    response_format: Optional[Union[str, Dict[str, Any]]] = None
    # 兼容第三方客户端的顶层附件字段（非标准 OpenAI，但常见）
    attachments: Optional[List[Any]] = None
    # MCP per-request endpoint（可选），用于工具调用回退到 MCP 服务
    mcp_endpoint: Optional[str] = None
