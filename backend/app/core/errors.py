from typing import Any, Dict, Optional
from fastapi import status


class OpsPilotException(Exception):
    """Base exception for OpsPilot application errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}


class AuthenticationError(OpsPilotException):
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            retryable=False,
            details=details,
        )


class AuthorizationError(OpsPilotException):
    def __init__(self, message: str = "Access forbidden", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="AUTHORIZATION_FAILED",
            status_code=status.HTTP_403_FORBIDDEN,
            retryable=False,
            details=details,
        )


ForbiddenError = AuthorizationError


class NotFoundError(OpsPilotException):
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} with identifier '{identifier}' was not found.",
            code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            retryable=False,
            details={"resource": resource, "identifier": str(identifier)},
        )


class ConflictError(OpsPilotException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="RESOURCE_CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            retryable=False,
            details=details,
        )


class ValidationError(OpsPilotException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="VALIDATION_FAILED",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            retryable=False,
            details=details,
        )


class DocumentProcessingError(OpsPilotException):
    def __init__(self, message: str, retryable: bool = True, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="DOCUMENT_PROCESSING_FAILED",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            retryable=retryable,
            details=details,
        )


class AIProviderError(OpsPilotException):
    def __init__(self, message: str, provider: str, retryable: bool = True, details: Optional[Dict[str, Any]] = None):
        full_details = details or {}
        full_details["provider"] = provider
        super().__init__(
            message=message,
            code="AI_PROVIDER_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            retryable=retryable,
            details=full_details,
        )


class StorageError(OpsPilotException):
    def __init__(self, message: str, retryable: bool = False, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="STORAGE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            retryable=retryable,
            details=details,
        )


class RateLimitExceededError(OpsPilotException):
    def __init__(
        self,
        message: str = "Rate limit exceeded. Please retry later.",
        retry_after_seconds: int = 60,
        details: Optional[Dict[str, Any]] = None,
    ):
        full_details = details or {}
        full_details["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            retryable=True,
            details=full_details,
        )
