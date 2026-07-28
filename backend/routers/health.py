"""Service health endpoint."""

from fastapi import APIRouter

from backend.core.config import settings
from backend.schemas.common import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)
