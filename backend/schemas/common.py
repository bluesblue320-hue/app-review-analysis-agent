"""Common API response schemas."""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorDetail(StrictModel):
    code: str
    message: str


class ErrorResponse(StrictModel):
    error: ErrorDetail
    request_id: str = ""


class HealthResponse(StrictModel):
    status: str
    service: str


class ReadyResponse(StrictModel):
    """Readiness detail: store, migration head and cache state.

    ``status`` is "ok" when fully ready, "degraded" when the service can
    still serve requests but a non-critical dependency (Redis) is down.
    """

    status: str
    service: str
    database: str
    migration: str
    redis: str
