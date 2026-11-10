from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "Bad request"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details or {}
        super().__init__(self.message)


class BadRequest(AppError):
    status_code = 400
    code = "BAD_REQUEST"


class Unauthenticated(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"
    message = "Authentication required"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "Permission denied"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "Resource conflict"


class TooManyRequests(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests"


class ServiceUnavailable(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
    message = "Service temporarily unavailable"


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
    details: Any | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            }
        },
    )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request_id=_request_id(request),
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        from fastapi.encoders import jsonable_encoder

        return error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            request_id=_request_id(request),
            details=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("database integrity error", extra={"request_id": _request_id(request)})
        return error_response(
            status_code=409,
            code="CONFLICT",
            message="Resource conflict",
            request_id=_request_id(request),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled exception",
            extra={"request_id": _request_id(request)},
        )
        return error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Internal server error",
            request_id=_request_id(request),
        )
