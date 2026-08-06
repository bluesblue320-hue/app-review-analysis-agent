"""Authentication, request IDs and privacy-safe request logging."""

from __future__ import annotations

import json
import logging
import re
import time
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.security import bearer_token_is_valid


logger = logging.getLogger("backend.requests")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
PUBLIC_PATHS = {
    f"{settings.api_prefix}/health",
    f"{settings.api_prefix}/ready",
}


async def request_context_middleware(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else uuid4().hex
    )
    request.state.request_id = request_id
    started = time.perf_counter()

    if request.url.path not in PUBLIC_PATHS and not bearer_token_is_valid(
        request.headers.get("Authorization"),
        settings.access_token,
    ):
        response = JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "unauthorized",
                    "message": "缺少或使用了无效的访问口令。",
                },
                "request_id": request_id,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
            ensure_ascii=False,
        )
    )
    return response
