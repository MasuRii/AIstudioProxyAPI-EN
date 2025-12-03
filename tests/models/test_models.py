from models.chat import (
    AudioInput,
    ChatCompletionRequest,
    FunctionCall,
    ImageURL,
    Message,
    MessageContentItem,
    ToolCall,
    URLRef,
    VideoInput,
)


def test_function_call_model():
    """Test FunctionCall model validation."""
    fc = FunctionCall(name="test_func", arguments='{"arg": 1}')
    assert fc.name == "test_func"
    assert fc.arguments == '{"arg": 1}'


def test_tool_call_model():
    """Test ToolCall model validation."""
    fc = FunctionCall(name="test_func", arguments='{"arg": 1}')
    tc = ToolCall(id="call_123", function=fc)
    assert tc.id == "call_123"
    assert tc.type == "function"
    assert tc.function == fc


def test_image_url_model():
    """Test ImageURL model validation."""
    img = ImageURL(url="http://example.com/image.png")
    assert img.url == "http://example.com/image.png"
    assert img.detail is None

    img_detail = ImageURL(url="http://example.com/image.png", detail="high")
    assert img_detail.detail == "high"


def test_audio_input_model():
    """Test AudioInput model validation."""
    audio = AudioInput(url="http://example.com/audio.mp3")
    assert audio.url == "http://example.com/audio.mp3"
    assert audio.data is None

    audio_data = AudioInput(data="base64data", format="mp3")
    assert audio_data.data == "base64data"
    assert audio_data.format == "mp3"


def test_video_input_model():
    """Test VideoInput model validation."""
    video = VideoInput(url="http://example.com/video.mp4")
    assert video.url == "http://example.com/video.mp4"


def test_url_ref_model():
    """Test URLRef model validation."""
    ref = URLRef(url="http://example.com/file.pdf")
    assert ref.url == "http://example.com/file.pdf"


def test_message_content_item_model():
    """Test MessageContentItem model validation."""
    # Text item
    text_item = MessageContentItem(type="text", text="Hello")
    assert text_item.type == "text"
    assert text_item.text == "Hello"

    # Image item
    img = ImageURL(url="http://example.com/img.png")
    img_item = MessageContentItem(type="image_url", image_url=img)
    assert img_item.type == "image_url"
    assert img_item.image_url == img

    # Input image item
    input_img_item = MessageContentItem(type="input_image", input_image=img)
    assert input_img_item.type == "input_image"
    assert input_img_item.input_image == img


def test_message_model():
    """Test Message model validation."""
    # Simple text message
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"

    # Message with list content
    item = MessageContentItem(type="text", text="Hello")
    msg_list = Message(role="user", content=[item])
    assert isinstance(msg_list.content, list)
    assert len(msg_list.content) == 1
    assert msg_list.content[0] == item

    # Message with tool calls
    fc = FunctionCall(name="func", arguments="{}")
    tc = ToolCall(id="1", function=fc)
    msg_tool = Message(role="assistant", tool_calls=[tc])
    assert msg_tool.tool_calls == [tc]


def test_chat_completion_request_model():
    """Test ChatCompletionRequest model validation."""
    msg = Message(role="user", content="Hello")
    req = ChatCompletionRequest(messages=[msg])
    assert req.messages == [msg]
    assert req.stream is False  # Default value

    req_stream = ChatCompletionRequest(messages=[msg], stream=True, temperature=0.7)
    assert req_stream.stream is True
    assert req_stream.temperature == 0.7
