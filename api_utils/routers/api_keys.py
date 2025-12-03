import logging

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..dependencies import get_logger


class ApiKeyRequest(BaseModel):
    key: str


class ApiKeyTestRequest(BaseModel):
    key: str


async def get_api_keys(logger: logging.Logger = Depends(get_logger)):
    from .. import auth_utils

    try:
        auth_utils.initialize_keys()
        keys_info = [{"value": key, "status": "有效"} for key in auth_utils.API_KEYS]
        return JSONResponse(
            content={"success": True, "keys": keys_info, "total_count": len(keys_info)}
        )
    except Exception as e:
        logger.error(f"获取API密钥列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def add_api_key(
    request: ApiKeyRequest, logger: logging.Logger = Depends(get_logger)
):
    from .. import auth_utils

    key_value = request.key.strip()
    if not key_value or len(key_value) < 8:
        raise HTTPException(status_code=400, detail="无效的API密钥格式。")

    auth_utils.initialize_keys()
    if key_value in auth_utils.API_KEYS:
        raise HTTPException(status_code=400, detail="该API密钥已存在。")

    try:
        key_file_path = auth_utils.KEY_FILE_PATH
        with open(key_file_path, "a+", encoding="utf-8") as f:
            f.seek(0)
            if f.read():
                f.write("\n")
            f.write(key_value)

        auth_utils.initialize_keys()
        logger.info(f"API密钥已添加: {key_value[:4]}...{key_value[-4:]}")
        return JSONResponse(
            content={
                "success": True,
                "message": "API密钥添加成功",
                "key_count": len(auth_utils.API_KEYS),
            }
        )
    except Exception as e:
        logger.error(f"添加API密钥失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def test_api_key(
    request: ApiKeyTestRequest, logger: logging.Logger = Depends(get_logger)
):
    from .. import auth_utils

    key_value = request.key.strip()
    if not key_value:
        raise HTTPException(status_code=400, detail="API密钥不能为空。")

    auth_utils.initialize_keys()
    is_valid = auth_utils.verify_api_key(key_value)
    logger.info(
        f"API密钥测试: {key_value[:4]}...{key_value[-4:]} - {'有效' if is_valid else '无效'}"
    )
    return JSONResponse(
        content={
            "success": True,
            "valid": is_valid,
            "message": "密钥有效" if is_valid else "密钥无效或不存在",
        }
    )


async def delete_api_key(
    request: ApiKeyRequest, logger: logging.Logger = Depends(get_logger)
):
    from .. import auth_utils

    key_value = request.key.strip()
    if not key_value:
        raise HTTPException(status_code=400, detail="API密钥不能为空。")

    auth_utils.initialize_keys()
    if key_value not in auth_utils.API_KEYS:
        raise HTTPException(status_code=404, detail="API密钥不存在。")

    try:
        key_file_path = auth_utils.KEY_FILE_PATH
        with open(key_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        with open(key_file_path, "w", encoding="utf-8") as f:
            f.writelines(line for line in lines if line.strip() != key_value)

        auth_utils.initialize_keys()
        logger.info(f"API密钥已删除: {key_value[:4]}...{key_value[-4:]}")
        return JSONResponse(
            content={
                "success": True,
                "message": "API密钥删除成功",
                "key_count": len(auth_utils.API_KEYS),
            }
        )
    except Exception as e:
        logger.error(f"删除API密钥失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
