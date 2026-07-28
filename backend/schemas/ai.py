"""Schemas for the existing DeepSeek insight workflow."""

from typing import Any

from pydantic import Field

from backend.schemas.analytics import ReviewFilters
from backend.schemas.common import StrictModel


class AiConfigResponse(StrictModel):
    provider: str
    model: str
    configured: bool


class AiInsightsRequest(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=100)
    filters: ReviewFilters = Field(default_factory=ReviewFilters)


class AiInsightsResponse(StrictModel):
    insights: dict[str, Any]
    sample_size: int
    scope_signature: str
