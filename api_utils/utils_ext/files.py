import base64
import binascii
import hashlib
import logging
import os
import re
from typing import Any, Dict, List, Optional, cast
from urllib.parse import unquote, urlparse

from logging_utils import set_request_id


def _extension_for_mime(mime_type: str) -> str:
    mime_type = (mime_type or "").lower()
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "image/bmp": ".bmp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/ogg": ".ogv",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/webm": ".weba",
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "application/x-zip-compressed": ".zip",
        "application/json": ".json",
        "text/plain": ".txt",
        "text/markdown": ".md",
        "text/html": ".html",
    }
    return mapping.get(
        mime_type, f".{mime_type.split('/')[-1]}" if "/" in mime_type else ".bin"
    )


def extract_data_url_to_local(
    data_url: str, req_id: Optional[str] = None
) -> Optional[str]:
    from config import UPLOAD_FILES_DIR

    logger = logging.getLogger("AIStudioProxyServer")

    output_dir = (
        UPLOAD_FILES_DIR if req_id is None else os.path.join(UPLOAD_FILES_DIR, req_id)
    )

    match = re.match(r"^data:(?P<mime>[^;]+);base64,(?P<data>.*)$", data_url)
    if not match:
        logger.error(
            "Error: data:URL format is incorrect or does not contain base64 data."
        )
        return None

    mime_type = match.group("mime")
    encoded_data = match.group("data")

    try:
        decoded_bytes = base64.b64decode(encoded_data)
    except binascii.Error as e:
        logger.error(f"Error: Base64 decoding failed - {e}")
        return None

    md5_hash = hashlib.md5(decoded_bytes).hexdigest()
    file_extension = _extension_for_mime(mime_type)
    output_filepath = os.path.join(output_dir, f"{md5_hash}{file_extension}")

    os.makedirs(output_dir, exist_ok=True)

    if os.path.exists(output_filepath):
        logger.info(f"File already exists, skipping save: {output_filepath}")
        return output_filepath

    try:
        with open(output_filepath, "wb") as f:
            f.write(decoded_bytes)
        logger.info(f"Saved data:URL to: {output_filepath}")
        return output_filepath
    except IOError as e:
        logger.error(f"Error: Failed to save file - {e}")
        return None


def save_blob_to_local(
    raw_bytes: bytes,
    mime_type: Optional[str] = None,
    fmt_ext: Optional[str] = None,
    req_id: Optional[str] = None,
) -> Optional[str]:
    from config import UPLOAD_FILES_DIR

    logger = logging.getLogger("AIStudioProxyServer")

    output_dir = (
        UPLOAD_FILES_DIR if req_id is None else os.path.join(UPLOAD_FILES_DIR, req_id)
    )
    md5_hash = hashlib.md5(raw_bytes).hexdigest()
    ext = None
    if fmt_ext:
        fmt_ext = fmt_ext.strip(". ")
        ext = f".{fmt_ext}" if fmt_ext else None
    if not ext and mime_type:
        ext = _extension_for_mime(mime_type)
    if not ext:
        ext = ".bin"
    os.makedirs(output_dir, exist_ok=True)
    output_filepath = os.path.join(output_dir, f"{md5_hash}{ext}")
    if os.path.exists(output_filepath):
        logger.info(f"File already exists, skipping save: {output_filepath}")
        return output_filepath
    try:
        with open(output_filepath, "wb") as f:
            f.write(raw_bytes)
        logger.info(f"Saved binary to: {output_filepath}")
        return output_filepath
    except IOError as e:
        logger.error(f"Error: Failed to save binary - {e}")
        return None


def collect_and_validate_attachments(
    request: Any, req_id: str, initial_image_list: List[str]
) -> List[str]:
    """
    Collect and validate attachments in the request (including top-level and message-level), merged into image_list.
    """
    logger = logging.getLogger("AIStudioProxyServer")

    # 1. Validate initial list
    valid_images: List[str] = []
    for p in initial_image_list:
        if p and os.path.isabs(p) and os.path.exists(p):
            valid_images.append(p)

    set_request_id(req_id)
    if len(valid_images) != len(initial_image_list):
        logger.warning(
            f"Filtered out non-existent attachment paths: {set(initial_image_list) - set(valid_images)}"
        )

    image_list: List[str] = valid_images

    # 2. Collect from request
    def _process_attachments_list(items_list: List[Any], container_desc: str):
        for it in items_list:
            url_value: Optional[str] = None
            if isinstance(it, str):
                url_value = it
            elif isinstance(it, dict):
                typed_it: Dict[str, Any] = cast(Dict[str, Any], it)
                url_raw: Any = typed_it.get("url") or typed_it.get("path")
                if isinstance(url_raw, str):
                    url_value = url_raw
            if not url_value:
                continue
            url_value = url_value.strip()
            if not url_value:
                continue

            if url_value.startswith("data:"):
                fp = extract_data_url_to_local(url_value, req_id=req_id)
                if fp:
                    image_list.append(fp)
            elif url_value.startswith("file:"):
                parsed = urlparse(url_value)
                lp = unquote(parsed.path)
                if os.path.exists(lp):
                    image_list.append(lp)
                else:
                    logger.warning(
                        f"{container_desc} attachment file URL does not exist: {lp}"
                    )
            elif os.path.isabs(url_value) and os.path.exists(url_value):
                image_list.append(url_value)

    try:
        # Top-level attachments
        top_level_atts = getattr(request, "attachments", None)
        if isinstance(top_level_atts, list) and len(top_level_atts) > 0:
            _process_attachments_list(top_level_atts, "request.attachments")

        # Message-level attachments/images/files/media
        messages = getattr(request, "messages", None)
        if isinstance(messages, list):
            for i, msg in enumerate(messages):
                for field in ["attachments", "images", "files", "media"]:
                    items = getattr(msg, field, None)
                    if isinstance(items, list) and len(items) > 0:
                        _process_attachments_list(items, f"message[{i}].{field}")

    except Exception as e:
        logger.error(f"Error collecting attachments: {e}")

    return image_list
