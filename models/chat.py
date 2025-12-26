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
    # OpenAI compatible: detail can be 'auto' | 'low' | 'high'
    detail: Optional[str] = None


class AudioInput(BaseModel):
    # Allow either url or data
    url: Optional[str] = None
    data: Optional[str] = None  # Base64 or data:URL
    format: Optional[str] = None  # e.g., 'wav', 'mp3'
    mime_type: Optional[str] = None  # e.g., 'audio/wav'


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
    # Added support for input_image (OpenAI compatible)
    input_image: Optional[ImageURL] = None
    # Extended support for general file_url/media_url and direct url field, maintaining OpenAI style
    file_url: Optional[URLRef] = None
    media_url: Optional[URLRef] = None
    url: Optional[str] = None
    # Extended support for input_audio/input_video
    input_audio: Optional[AudioInput] = None
    input_video: Optional[VideoInput] = None


class Message(BaseModel):
    role: str
    content: Union[str, List[MessageContentItem], None] = None
    name: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    # Compatible with third-party clients passing attachments at message level (non-standard but common)
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
    # Compatible with third-party clients' top-level attachments field (non-standard OpenAI, but common)
    attachments: Optional[List[Any]] = None
    # MCP per-request endpoint (optional), used for tool calling fallback to MCP service
    mcp_endpoint: Optional[str] = None
    parallel_tool_calls: Optional[bool] = True
