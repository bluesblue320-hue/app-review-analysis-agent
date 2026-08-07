"""Backend boundary for the existing DeepSeek insight function."""

from __future__ import annotations

import logging
import time
from typing import Any

from ai_analysis import AiAnalysisError, analyze_reviews, load_ai_config
from backend.core.exceptions import (
    AiServiceError,
    InsightGenerationInProgressError,
    InvalidDatasetError,
)
from backend.core.serialization import to_json_value
from backend.schemas.ai import AiConfigResponse, AiInsightsRequest, AiInsightsResponse
from backend.services.cache_service import InsightLock, insight_lock, insight_lock_key
from backend.services.dataset_service import InMemoryDatasetStore
from backend.services.insight_store import InMemoryInsightStore
from backend.services.repositories import (
    ANALYSIS_VERSION,
    InsightRepository,
    compute_insight_fingerprint,
    compute_scope_signature,
)
from backend.services.scope_service import ReviewScopeService

logger = logging.getLogger(__name__)

# How long a caller waits for the generating request to finish before
# answering with 409 insight_generation_in_progress.
LOCK_WAIT_SECONDS = 15.0
LOCK_POLL_INTERVAL_SECONDS = 0.2


class AiInsightService:
    def __init__(
        self,
        store: InMemoryDatasetStore,
        insight_store: InMemoryInsightStore,
        lock: InsightLock | None = None,
    ) -> None:
        self._scope_service = ReviewScopeService(store)
        self._insight_store: InsightRepository = insight_store
        # Dependency-injected so tests can supply a dedicated lock without
        # mutating module-level state shared across requests.
        self._lock: InsightLock = lock if lock is not None else insight_lock

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
        ai_config = load_ai_config()
        provider = ai_config["provider"]
        model_name = ai_config["model"]
        sample_size = int(len(dataframe))
        fingerprint = compute_insight_fingerprint(
            dataset_id=request.dataset_id,
            scope_signature=scope_signature,
            sample_size=sample_size,
            analysis_version=ANALYSIS_VERSION,
            provider=provider,
            model_name=model_name,
        )

        # 1. Reuse an unexpired record for the same fingerprint, if any.
        record = self._insight_store.get_by_fingerprint(fingerprint)
        if record is not None and not record.is_expired:
            return self._response(record, scope_signature, sample_size)

        lock_key = insight_lock_key(request.dataset_id, scope_signature)
        with self._lock.hold(lock_key) as lease:
            if not lease.acquired:
                # Another request holds the lease and is generating. Bounded
                # wait, then reuse the result or answer generation-in-progress.
                # Never call the model from a second request.
                return self._wait_for_generation(
                    fingerprint=fingerprint,
                    scope_signature=scope_signature,
                    sample_size=sample_size,
                    wait_seconds=LOCK_WAIT_SECONDS,
                )

            # Re-check after acquiring the lease: the concurrent holder may
            # have finished and persisted while we waited for the lock.
            record = self._insight_store.get_by_fingerprint(
                fingerprint, include_expired=True
            )
            if record is not None and not record.is_expired:
                return self._response(record, scope_signature, sample_size)

            try:
                insights = analyze_reviews(dataframe)
            except AiAnalysisError as exc:
                raise AiServiceError(str(exc)) from exc
            insights = to_json_value(insights)
            if not isinstance(insights, dict):
                raise AiServiceError("AI 返回结构异常，请稍后重试。")

            if record is not None and record.is_expired:
                # Same fingerprint expired: refresh the original record in
                # place, keeping its insight_id.
                refreshed = self._insight_store.refresh_expired(
                    fingerprint=fingerprint,
                    insights=insights,
                    provider=provider,
                    model_name=model_name,
                )
                return self._response(refreshed, scope_signature, sample_size)

            record = self._insight_store.create(
                dataset_id=request.dataset_id,
                scope_signature=scope_signature,
                sample_size=sample_size,
                insights=insights,
                analysis_version=ANALYSIS_VERSION,
                provider=provider,
                model_name=model_name,
            )
            return self._response(record, scope_signature, sample_size)

    def _wait_for_generation(
        self,
        *,
        fingerprint: str,
        scope_signature: str,
        sample_size: int,
        wait_seconds: float,
    ) -> AiInsightsResponse:
        """Bounded wait for the generating request, then reuse or 409."""
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            record = self._insight_store.get_by_fingerprint(fingerprint)
            if record is not None and not record.is_expired:
                return self._response(record, scope_signature, sample_size)
            time.sleep(LOCK_POLL_INTERVAL_SECONDS)
        logger.info(
            "insight generation still in progress after %ss; returning 409",
            wait_seconds,
        )
        raise InsightGenerationInProgressError(
            "相同范围内的 AI 洞察正在生成中，请稍后重试。"
        )

    @staticmethod
    def _response(
        record: Any,
        scope_signature: str,
        sample_size: int,
    ) -> AiInsightsResponse:
        return AiInsightsResponse(
            insight_id=record.insight_id,
            insights=record.insights,
            sample_size=sample_size,
            scope_signature=scope_signature,
        )


def compute_content_hash_from_frame(dataframe: Any) -> str:
    """Content hash of the full dataset frame for scope-signature stability."""
    from backend.services.repositories import compute_content_hash

    columns = tuple(str(column) for column in dataframe.columns)
    return compute_content_hash(dataframe, columns)
