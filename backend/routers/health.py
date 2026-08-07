"""Service health and readiness endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from backend.core.config import settings
from backend.schemas.common import HealthResponse, ReadyResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Liveness: process is alive."""
    return HealthResponse(status="ok", service=settings.service_name)


def _alembic_head() -> str:
    """Return the migration head revision from alembic scripts."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(settings.alembic_config_path))
    config.set_main_option("script_location", str(settings.alembic_script_location))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if not heads:
        return ""
    return sorted(heads)[0]


def _current_revision(database_url: str) -> str:
    """Return the revision currently applied to the database."""
    from alembic.runtime.migration import MigrationContext
    from backend.storage.database import get_database_runtime

    runtime = get_database_runtime(database_url)
    with runtime.engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current = context.get_current_revision()
    return current or ""


@router.get("/ready", response_model=ReadyResponse)
def ready_check() -> Response:
    """Readiness: store reachable and, for database storage, migrated to head.

    Rules:
    - database unreachable            -> 503
    - database storage, migration    -> 503 when revision != head
    - Redis unavailable               -> degraded (still 200)
    - memory storage                  -> no Alembic requirement
    """
    storage_backend = settings.storage_backend
    redis_state = "ok"

    from backend.services.cache_service import cache_service

    try:
        if not cache_service.ready():
            redis_state = "degraded"
    except Exception:
        redis_state = "degraded"

    if storage_backend == "database":
        from backend.services.dataset_service import dataset_store

        try:
            database_ready = bool(dataset_store.ready())
        except Exception:
            database_ready = False
        if not database_ready:
            return _ready_response(
                ReadyResponse(
                    status="not_ready",
                    service=settings.service_name,
                    database="error",
                    migration="unknown",
                    redis=redis_state,
                ),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            head = _alembic_head()
            current = _current_revision(settings.database_url)
        except Exception:
            logger.exception("migration check failed")
            return _ready_response(
                ReadyResponse(
                    status="not_ready",
                    service=settings.service_name,
                    database="ok",
                    migration="unknown",
                    redis=redis_state,
                ),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not head or current != head:
            logger.warning(
                "database migration behind: current=%s head=%s", current, head
            )
            return _ready_response(
                ReadyResponse(
                    status="not_ready",
                    service=settings.service_name,
                    database="ok",
                    migration="behind",
                    redis=redis_state,
                ),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if redis_state == "degraded":
            return _ready_response(
                ReadyResponse(
                    status="degraded",
                    service=settings.service_name,
                    database="ok",
                    migration="head",
                    redis="degraded",
                )
            )
        return _ready_response(
            ReadyResponse(
                status="ok",
                service=settings.service_name,
                database="ok",
                migration="head",
                redis="ok",
            )
        )

    # Memory storage: no database / migration requirement.
    if redis_state == "degraded":
        return _ready_response(
            ReadyResponse(
                status="degraded",
                service=settings.service_name,
                database="n/a",
                migration="n/a",
                redis="degraded",
            )
        )
    return _ready_response(
        ReadyResponse(
            status="ok",
            service=settings.service_name,
            database="n/a",
            migration="n/a",
            redis="ok",
        )
    )


def _ready_response(payload: ReadyResponse, status_code: int = 200) -> Response:
    return Response(
        content=payload.model_dump_json(),
        media_type="application/json",
        status_code=status_code,
    )
