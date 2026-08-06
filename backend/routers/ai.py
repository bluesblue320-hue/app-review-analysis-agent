"""Existing AI insight endpoints; no Tool Calling is performed."""

from fastapi import APIRouter

from backend.schemas.ai import AiConfigResponse, AiInsightsRequest, AiInsightsResponse
from backend.services.ai_service import AiInsightService
from backend.services.dataset_service import dataset_store
from backend.services.insight_store import insight_store


router = APIRouter(prefix="/ai", tags=["ai"])
ai_service = AiInsightService(dataset_store, insight_store)


@router.get("/config", response_model=AiConfigResponse)
def ai_config() -> AiConfigResponse:
    return ai_service.get_config()


@router.post("/insights", response_model=AiInsightsResponse)
def generate_ai_insights(request: AiInsightsRequest) -> AiInsightsResponse:
    return ai_service.generate(request)
