"""Backend boundary for the existing DeepSeek insight function."""

from __future__ import annotations

from typing import Any

from ai_analysis import AiAnalysisError, analyze_reviews, load_ai_config
from backend.core.exceptions import AiServiceError, InvalidDatasetError
from backend.core.serialization import to_json_value
from backend.schemas.ai import AiConfigResponse, AiInsightsRequest, AiInsightsResponse
from backend.services.dataset_service import InMemoryDatasetStore
from backend.services.insight_store import InMemoryInsightStore
from backend.services.repositories import (
    ANALYSIS_VERSION,
    InsightRepository,
    compute_insight_fingerprint,
    compute_scope_signature,
)
from backend.services.scope_service import ReviewScopeService


class AiInsightService:
    def __init__(
        self,
        store: InMemoryDatasetStore,
        insight_store: InMemoryInsightStore,
    ) -> None:
        self._scope_service = ReviewScopeService(store)
        self._insight_store: InsightRepository = insight_store

    @staticmethod
    def get_config() -> AiConfigResponse:
        config = load_ai_config()
        return AiConfigResponse(
            provider=config["provider"],
            model=config["model"],
            configured=bool(config["api_key"]),
        )

    def generate(self, request: AiInsightsRequest) -> AiInsightsResponse:
        dataset = self._scope_service._store.get(request.dataset_id)
        dataframe = self._scope_service.get_dataframe(
            request.dataset_id,
            request.filters,
        )
        if dataframe.empty:
            raise InvalidDatasetError("当前筛选范围内没有可分析的评论。")

        content_hash = dataset.content_hash or compute_content_hash_from_frame(
            dataset.dataframe
        )
        scope_signature = compute_scope_signature(
            content_hash,
            request.filters.model_dump(),
            analysis_version=ANALYSIS_VERSION,
        )
        fingerprint = compute_insight_fingerprint(
            dataset_id=request.dataset_id,
            scope_signature=scope_signature,
            sample_size=len(dataframe),
            analysis_version=ANALYSIS_VERSION,
        )

        existing = self._insight_store.find_by_fingerprint(fingerprint)
        if existing is not None:
            return AiInsightsResponse(
                insight_id=existing.insight_id,
                insights=existing.insights,
                sample_size=int(len(dataframe)),
                scope_signature=scope_signature,
            )

        try:
            insights = analyze_reviews(dataframe)
        except AiAnalysisError as exc:
            raise AiServiceError(str(exc)) from exc
        insights = to_json_value(insights)
        if not isinstance(insights, dict):
            raise AiServiceError("AI 返回结构异常，请稍后重试。")

        record = self._insight_store.create(
            dataset_id=request.dataset_id,
            scope_signature=scope_signature,
            sample_size=len(dataframe),
            insights=insights,
            analysis_version=ANALYSIS_VERSION,
        )
        return AiInsightsResponse(
            insight_id=record.insight_id,
            insights=record.insights,
            sample_size=int(len(dataframe)),
            scope_signature=scope_signature,
        )


def compute_content_hash_from_frame(dataframe: Any) -> str:
    """Content hash of the full dataset frame for scope-signature stability."""
    from backend.services.repositories import compute_content_hash

    columns = tuple(str(column) for column in dataframe.columns)
    return compute_content_hash(dataframe, columns)
