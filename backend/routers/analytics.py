"""Deterministic analytics endpoints."""

from fastapi import APIRouter

from backend.schemas.analytics import AnalyticsSummaryRequest, AnalyticsSummaryResponse
from backend.services.analytics_service import AnalyticsService
from backend.services.dataset_service import dataset_store


router = APIRouter(prefix="/analytics", tags=["analytics"])
analytics_service = AnalyticsService(dataset_store)


@router.post("/summary", response_model=AnalyticsSummaryResponse)
def analytics_summary(
    request: AnalyticsSummaryRequest,
) -> AnalyticsSummaryResponse:
    return analytics_service.build_summary(request)
