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
        keys_info = [{"value": key, "status": "Valid"} for key in auth_utils.API_KEYS]
        return JSONResponse(
            content={"success": True, "keys": keys_info, "total_count": len(keys_info)}
        )
    except Exception as e:
        logger.error(f"Failed to get API key list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def add_api_key(
    request: ApiKeyRequest, logger: logging.Logger = Depends(get_logger)
):
    from .. import auth_utils

    key_value = request.key.strip()
    if not key_value or len(key_value) < 8:
        raise HTTPException(status_code=400, detail="Invalid API key format.")

    auth_utils.initialize_keys()
    if key_value in auth_utils.API_KEYS:
        raise HTTPException(status_code=400, detail="API key already exists.")

    try:
        key_file_path = auth_utils.KEY_FILE_PATH
        with open(key_file_path, "a+", encoding="utf-8") as f:
            f.seek(0)
            if f.read():
                f.write("\n")
            f.write(key_value)

        auth_utils.initialize_keys()
        logger.info(f"API key added: {key_value[:4]}...{key_value[-4:]}")
        return JSONResponse(
            content={
                "success": True,
                "message": "API key added successfully",
                "key_count": len(auth_utils.API_KEYS),
            }
        )
    except Exception as e:
        logger.error(f"Failed to add API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def test_api_key(
    request: ApiKeyTestRequest, logger: logging.Logger = Depends(get_logger)
):
    from .. import auth_utils

    key_value = request.key.strip()
    if not key_value:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")

    auth_utils.initialize_keys()
    is_valid = auth_utils.verify_api_key(key_value)
    logger.info(
        f"API key test: {key_value[:4]}...{key_value[-4:]} - {'Valid' if is_valid else 'Invalid'}"
    )
    return JSONResponse(
        content={
            "success": True,
            "valid": is_valid,
            "message": "Key valid" if is_valid else "Key invalid or non-existent",
        }
    )


async def delete_api_key(
    request: ApiKeyRequest, logger: logging.Logger = Depends(get_logger)
):
    from .. import auth_utils

    key_value = request.key.strip()
    if not key_value:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")

    auth_utils.initialize_keys()
    if key_value not in auth_utils.API_KEYS:
        raise HTTPException(status_code=404, detail="API key does not exist.")

    try:
        key_file_path = auth_utils.KEY_FILE_PATH
        with open(key_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        with open(key_file_path, "w", encoding="utf-8") as f:
            f.writelines(line for line in lines if line.strip() != key_value)

        auth_utils.initialize_keys()
        logger.info(f"API key deleted: {key_value[:4]}...{key_value[-4:]}")
        return JSONResponse(
            content={
                "success": True,
                "message": "API key deleted successfully",
                "key_count": len(auth_utils.API_KEYS),
            }
        )
    except Exception as e:
        logger.error(f"Failed to delete API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))
