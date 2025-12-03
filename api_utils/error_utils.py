from typing import Dict, Optional

from fastapi import HTTPException


def http_error(
    status_code: int, detail: str, headers: Optional[Dict[str, str]] = None
) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail=detail, headers=headers or None
    )


def client_cancelled(req_id: str, message: str = "Request cancelled.") -> HTTPException:
    return http_error(499, f"[{req_id}] {message}")


def client_disconnected(req_id: str, stage: str = "") -> HTTPException:
    suffix = f" during {stage}" if stage else ""
    return http_error(499, f"[{req_id}] Client disconnected{suffix}.")


def processing_timeout(
    req_id: str, message: str = "Processing timed out."
) -> HTTPException:
    return http_error(504, f"[{req_id}] {message}")


def bad_request(req_id: str, message: str) -> HTTPException:
    return http_error(400, f"[{req_id}] {message}")


def server_error(req_id: str, message: str) -> HTTPException:
    return http_error(500, f"[{req_id}] {message}")


def upstream_error(req_id: str, message: str) -> HTTPException:
    # 502 Bad Gateway for upstream/playwright failures
    return http_error(502, f"[{req_id}] {message}")


def service_unavailable(req_id: str, retry_after_seconds: int = 30) -> HTTPException:
    return http_error(
        503,
        f"[{req_id}] 服务当前不可用。请稍后重试。",
        headers={"Retry-After": str(retry_after_seconds)},
    )
