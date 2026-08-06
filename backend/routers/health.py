"""Service health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from backend.core.config import settings
from backend.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@router.get("/ready", response_model=HealthResponse)
def ready_check() -> HealthResponse:
    """Readiness: backend store reachable.

    A non-200 status is returned when the store is unreachable so
    orchestrators do not route traffic to an unprepared instance.
    """
    from backend.services.dataset_service import dataset_store

    try:
        ready = bool(dataset_store.ready())
    except Exception:
        ready = False
    if not ready:
        body = f'{{"status": "not_ready", "service": "{settings.service_name}"}}'
        return Response(
            content=body,
            media_type="application/json",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return HealthResponse(status="ok", service=settings.service_name)
