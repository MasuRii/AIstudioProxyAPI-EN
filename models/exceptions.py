import time
from typing import Any, List, Optional

from fastapi import HTTPException


class AIStudioProxyError(Exception):
    """Base exception for AIStudio Proxy errors."""
    def __init__(
        self, 
        message: str, 
        req_id: Optional[str] = None, 
        http_status: int = 500, 
        retry_after: Optional[int] = None,
        **kwargs: Any
    ):
        self.message = message
        self.req_id = req_id
        self.http_status = http_status
        self.retry_after = retry_after
        self.timestamp = time.time()
        self.context = kwargs
        
        # Format message with req_id if present for string representation
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if self.req_id:
            return f"[{self.req_id}] {self.message}"
        return self.message

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} message='{self.message}' req_id='{self.req_id}' http_status={self.http_status} context={self.context}>"

    def to_http_exception(self) -> HTTPException:
        headers = {}
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        
        return HTTPException(
            status_code=self.http_status,
            detail=str(self),
            headers=headers if headers else None
        )

# Browser Errors
class BrowserError(AIStudioProxyError):
    def __init__(self, message: str, http_status: int = 503, retry_after: int = 30, **kwargs):
        super().__init__(message, http_status=http_status, retry_after=retry_after, **kwargs)

class BrowserInitError(BrowserError):
    pass

class PageNotReadyError(BrowserError):
    pass

class BrowserCrashedError(BrowserError):
    def __init__(self, message: str = "Browser crashed unexpectedly", **kwargs):
        super().__init__(message, **kwargs)

class SelectorNotFoundError(BrowserError):
    def __init__(self, selector: str, message: str = "Selector not found", **kwargs):
        super().__init__(f"{message}: {selector}", selector=selector, **kwargs)

# Model Errors
class ModelError(AIStudioProxyError):
    def __init__(self, message: str, http_status: int = 422, **kwargs):
        super().__init__(message, http_status=http_status, **kwargs)

class InvalidModelError(ModelError):
    def __init__(self, model_id: str, available_models: Optional[List[str]] = None, message: str = "Invalid model", **kwargs):
        msg = f"{message}: {model_id}"
        if available_models:
            msg += f" (Available: {', '.join(available_models)})"
        super().__init__(msg, model_id=model_id, available_models=available_models, **kwargs)

class ModelSwitchError(ModelError):
    def __init__(self, target_model: str, current_model: str, message: str = "Failed to switch model", **kwargs):
        super().__init__(f"{message} from {current_model} to {target_model}", target_model=target_model, current_model=current_model, **kwargs)

class ModelListError(ModelError):
    pass

# Client Errors
class ClientDisconnectedError(Exception):
    """Client disconnected exception (kept simple for backward compatibility but with extra fields)."""
    def __init__(self, message: str = "Client disconnected", stage: str = "", req_id: Optional[str] = None, http_status: int = 499):
        self.message = message
        self.stage = stage
        self.req_id = req_id
        self.http_status = http_status
        super().__init__(message)

# Validation Errors
class ValidationError(AIStudioProxyError):
    def __init__(self, message: str, http_status: int = 400, **kwargs):
        super().__init__(message, http_status=http_status, **kwargs)

class MissingParameterError(ValidationError):
    def __init__(self, parameter: str, message: str = "Missing parameter", **kwargs):
        super().__init__(f"{message}: {parameter}", parameter=parameter, **kwargs)

class InvalidParameterError(ValidationError):
    def __init__(self, parameter: str, value: Any, reason: str, message: str = "Invalid parameter", **kwargs):
        super().__init__(f"{message} {parameter}={value}: {reason}", parameter=parameter, value=value, reason=reason, **kwargs)

# Stream Errors
class StreamError(AIStudioProxyError):
    def __init__(self, message: str, http_status: int = 502, **kwargs):
        super().__init__(message, http_status=http_status, **kwargs)

class ProxyConnectionError(StreamError):
    def __init__(self, proxy_url: str, message: str = "Failed to connect to proxy", **kwargs):
        super().__init__(f"{message}: {proxy_url}", proxy_url=proxy_url, **kwargs)

class StreamTimeoutError(StreamError):
    def __init__(self, timeout_seconds: float, message: str = "Stream timed out", **kwargs):
        super().__init__(f"{message} after {timeout_seconds}s", timeout_seconds=timeout_seconds, **kwargs)

# Resource Errors
class ResourceError(AIStudioProxyError):
    def __init__(self, message: str, http_status: int = 503, retry_after: int = 60, **kwargs):
        super().__init__(message, http_status=http_status, retry_after=retry_after, **kwargs)

class QueueFullError(ResourceError):
    def __init__(self, queue_size: int, message: str = "Queue full", **kwargs):
        super().__init__(f"{message} (size: {queue_size})", queue_size=queue_size, **kwargs)

# Upstream Errors
class UpstreamError(AIStudioProxyError):
    def __init__(self, message: str, http_status: int = 502, retry_after: int = 10, **kwargs):
        super().__init__(message, http_status=http_status, retry_after=retry_after, **kwargs)

class AIStudioError(UpstreamError):
    def __init__(self, error_message: str, status_code: int, message: str = "AI Studio error", **kwargs):
        super().__init__(f"{message}: {error_message} (Status: {status_code})", ai_studio_status=status_code, error_message=error_message, **kwargs)

class QuotaExceededError(UpstreamError):
    def __init__(self, message: str = "Quota exceeded", retry_after: int = 3600, **kwargs):
        super().__init__(message, retry_after=retry_after, **kwargs)

class EmptyResponseError(UpstreamError):
    def __init__(self, message: str = "Received empty response", **kwargs):
        super().__init__(message, **kwargs)

class QuotaExceededRetry(Exception):
    pass

# Timeout Errors
class TimeoutError(AIStudioProxyError):
    def __init__(self, message: str, http_status: int = 504, **kwargs):
        super().__init__(message, http_status=http_status, **kwargs)

class ResponseTimeoutError(TimeoutError):
    def __init__(self, timeout_seconds: float, message: str = "Response timed out", **kwargs):
        super().__init__(f"{message} after {timeout_seconds}s", timeout_seconds=timeout_seconds, **kwargs)

class ProcessingTimeoutError(TimeoutError):
    def __init__(self, timeout_seconds: Optional[float] = None, message: str = "Processing timeout", **kwargs):
        msg = message
        if timeout_seconds:
            msg += f" after {timeout_seconds}s"
        super().__init__(msg, timeout_seconds=timeout_seconds, **kwargs)

# Configuration Errors
class ConfigurationError(AIStudioProxyError):
    def __init__(self, message: str, http_status: int = 500, **kwargs):
        super().__init__(message, http_status=http_status, **kwargs)

class MissingConfigError(ConfigurationError):
    def __init__(self, config_key: str, message: str = "Missing configuration", **kwargs):
        super().__init__(f"{message}: {config_key}", config_key=config_key, **kwargs)

class InvalidConfigError(ConfigurationError):
    def __init__(self, config_key: str, value: Any, reason: str, message: str = "Invalid configuration", **kwargs):
        super().__init__(f"{message} {config_key}={value}: {reason}", config_key=config_key, value=value, reason=reason, **kwargs)