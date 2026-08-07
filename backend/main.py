"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.config import settings
from backend.core.exceptions import AppError
from backend.core.lifecycle import application_lifespan
from backend.core.middleware import request_context_middleware
from backend.routers import agent, ai, analytics, datasets, health
from backend.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Build an error response whose body and header share the request ID."""
    request_id = getattr(request.state, "request_id", "") or ""
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=message),
        request_id=request_id,
    )
    response = JSONResponse(status_code=status_code, content=payload.model_dump())
    response.headers["X-Request-ID"] = request_id
    return response


def create_app() -> FastAPI:
    application = FastAPI(
        title="App Review Analysis Agent API",
        version="1.0.0",
        lifespan=application_lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )
    application.middleware("http")(request_context_middleware)
    application.include_router(health.router, prefix=settings.api_prefix)
    application.include_router(datasets.router, prefix=settings.api_prefix)
    application.include_router(analytics.router, prefix=settings.api_prefix)
    application.include_router(ai.router, prefix=settings.api_prefix)
    application.include_router(agent.router, prefix=settings.api_prefix)

    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.info(
            "API request rejected: path=%s code=%s",
            request.url.path,
            exc.code,
        )
        return _error_response(request, exc.status_code, exc.code, exc.message)

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        first_error = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first_error.get("loc", ()))
        detail = str(first_error.get("msg", "请求参数校验失败"))
        message = f"{location}: {detail}" if location else detail
        logger.info("API validation failed: path=%s", request.url.path)
        return _error_response(request, 422, "validation_error", message)

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        logger.info(
            "HTTP error: path=%s status=%s",
            request.url.path,
            exc.status_code,
        )
        return _error_response(request, exc.status_code, "http_error", str(exc.detail))

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error: path=%s", request.url.path)
        return _error_response(request, 500, "internal_error", "服务暂时无法完成请求。")

    return application


app = create_app()
