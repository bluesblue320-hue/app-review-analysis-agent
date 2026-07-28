"""Backend boundary for the existing DeepSeek insight function."""

from __future__ import annotations

from agent_workflow import dataframe_scope_signature
from ai_analysis import AiAnalysisError, analyze_reviews, load_ai_config
from backend.core.exceptions import AiServiceError, InvalidDatasetError
from backend.schemas.ai import AiConfigResponse, AiInsightsRequest, AiInsightsResponse
from backend.services.dataset_service import InMemoryDatasetStore
from backend.services.scope_service import ReviewScopeService


class AiInsightService:
    def __init__(self, store: InMemoryDatasetStore) -> None:
        self._scope_service = ReviewScopeService(store)

    @staticmethod
    def get_config() -> AiConfigResponse:
        config = load_ai_config()
        return AiConfigResponse(
            provider=config["provider"],
            model=config["model"],
            configured=bool(config["api_key"]),
        )

    def generate(self, request: AiInsightsRequest) -> AiInsightsResponse:
        dataframe = self._scope_service.get_dataframe(
            request.dataset_id,
            request.filters,
        )
        if dataframe.empty:
            raise InvalidDatasetError("当前筛选范围内没有可分析的评论。")
        try:
            insights = analyze_reviews(dataframe)
        except AiAnalysisError as exc:
            raise AiServiceError(str(exc)) from exc
        return AiInsightsResponse(
            insights=insights,
            sample_size=int(len(dataframe)),
            scope_signature=dataframe_scope_signature(dataframe),
        )
