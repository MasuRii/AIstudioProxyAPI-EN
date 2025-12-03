import base64
import binascii
import hashlib
import os
import re
from typing import Optional


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
    from server import logger

    output_dir = (
        UPLOAD_FILES_DIR if req_id is None else os.path.join(UPLOAD_FILES_DIR, req_id)
    )

    match = re.match(r"^data:(?P<mime>[^;]+);base64,(?P<data>.*)$", data_url)
    if not match:
        logger.error("错误: data:URL 格式不正确或不包含 base64 数据。")
        return None

    mime_type = match.group("mime")
    encoded_data = match.group("data")

    try:
        decoded_bytes = base64.b64decode(encoded_data)
    except binascii.Error as e:
        logger.error(f"错误: Base64 解码失败 - {e}")
        return None

    md5_hash = hashlib.md5(decoded_bytes).hexdigest()
    file_extension = _extension_for_mime(mime_type)
    output_filepath = os.path.join(output_dir, f"{md5_hash}{file_extension}")

    os.makedirs(output_dir, exist_ok=True)

    if os.path.exists(output_filepath):
        logger.info(f"文件已存在，跳过保存: {output_filepath}")
        return output_filepath

    try:
        with open(output_filepath, "wb") as f:
            f.write(decoded_bytes)
        logger.info(f"已保存 data:URL 到: {output_filepath}")
        return output_filepath
    except IOError as e:
        logger.error(f"错误: 保存文件失败 - {e}")
        return None


def save_blob_to_local(
    raw_bytes: bytes,
    mime_type: Optional[str] = None,
    fmt_ext: Optional[str] = None,
    req_id: Optional[str] = None,
) -> Optional[str]:
    from config import UPLOAD_FILES_DIR
    from server import logger

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
        logger.info(f"文件已存在，跳过保存: {output_filepath}")
        return output_filepath
    try:
        with open(output_filepath, "wb") as f:
            f.write(raw_bytes)
        logger.info(f"已保存二进制到: {output_filepath}")
        return output_filepath
    except IOError as e:
        logger.error(f"错误: 保存二进制失败 - {e}")
        return None
