"""Deterministic analytics assembled from the existing pandas functions."""

from __future__ import annotations

import pandas as pd

from agent_workflow import dataframe_scope_signature
from backend.core.config import settings
from backend.core.serialization import dataframe_to_records
from backend.schemas.analytics import (
    AnalyticsSummaryRequest,
    AnalyticsSummaryResponse,
    ReviewSearchRequest,
    ReviewSearchResponse,
)
from backend.services.cache_service import (
    CACHE_SCHEMA_VERSION,
    analytics_cache_key,
    cache_service,
)
from backend.services.dataset_service import InMemoryDatasetStore
from backend.services.insight_store import InMemoryInsightStore
from backend.services.repositories import (
    ANALYSIS_VERSION,
    compute_scope_signature,
)
from backend.services.scope_service import ReviewScopeService
from review_fields import (
    CATEGORY_COLUMN,
    CONTENT_COLUMN,
    RATING_COLUMN,
    RISK_LABEL_COLUMN,
    SENTIMENT_COLUMN,
    TOKEN_COLUMN,
)
from visual_analysis import (
    LOW_SENTIMENT,
    calculate_health_metrics,
    calculate_priority_table,
    extract_keyword_scores,
    is_high_risk_label,
    rating_distribution,
    sentiment_distribution,
    sentiment_trend,
)


class AnalyticsService:
    def __init__(
        self,
        store: InMemoryDatasetStore,
        insight_store: InMemoryInsightStore,
        cache=cache_service,
    ) -> None:
        self._store = store
        self._scope_service = ReviewScopeService(store)
        self._insight_store = insight_store
        self._cache = cache

    def build_summary(
        self,
        request: AnalyticsSummaryRequest,
    ) -> AnalyticsSummaryResponse:
        record = self._store.get(request.dataset_id)  # validates existence
        filtered = self._scope_service.apply_filters(record.dataframe, request.filters)
        content_hash = record.content_hash or dataframe_scope_signature(
            record.dataframe
        )
        scope_signature = compute_scope_signature(
            content_hash,
            request.filters.model_dump(),
            analysis_version=ANALYSIS_VERSION,
        )
        cache_key = analytics_cache_key(
            dataset_id=request.dataset_id,
            scope_signature=scope_signature,
            analysis_type="summary",
            insight_id=request.insight_id,
        )
        cached = self._cache.get(cache_key)
        if cached is not None and _valid_cache_payload(cached):
            return AnalyticsSummaryResponse.model_validate(cached["payload"])
        current_insights, insight_warning = self._insight_store.resolve(
            insight_id=request.insight_id,
            dataset_id=request.dataset_id,
            scope_signature=scope_signature,
            sample_size=len(filtered),
        )

        metrics = calculate_health_metrics(filtered)
        negative_reviews = filtered[filtered[RATING_COLUMN] <= 3]
        positive_reviews = filtered[filtered[RATING_COLUMN] >= 4]

        rating_records = self._renamed_records(
            rating_distribution(filtered),
            {RATING_COLUMN: "rating", "评论数": "review_count"},
        )
        sentiment_records = self._renamed_records(
            sentiment_distribution(filtered),
            {"情绪区间": "range", "评论数": "review_count"},
        )
        negative_keyword_records = self._renamed_records(
            extract_keyword_scores(negative_reviews[TOKEN_COLUMN], top_n=15),
            {"关键词": "keyword", "权重": "weight"},
        )
        positive_keyword_records = self._renamed_records(
            extract_keyword_scores(positive_reviews[TOKEN_COLUMN], top_n=15),
            {"关键词": "keyword", "权重": "weight"},
        )
        priority_records = self._renamed_records(
            calculate_priority_table(filtered, ai_insights=current_insights, top_n=5),
            {
                CATEGORY_COLUMN: "category",
                "优先级分数": "priority_score",
                "严重程度": "severity",
                "相关评论数": "review_count",
                "平均评分": "average_rating",
                "平均情绪指数": "average_sentiment",
                "AI严重度": "ai_severity",
                "AI建议": "ai_recommendation",
                "代表评论": "representative_review",
            },
        )
        trend_records = self._renamed_records(
            sentiment_trend(filtered),
            {
                "日期": "date",
                "平均情绪指数": "average_sentiment",
                "平均评分": "average_rating",
                "评论数": "review_count",
            },
        )

        high_risk = filtered[
            filtered[RISK_LABEL_COLUMN].apply(is_high_risk_label)
        ].copy()
        high_risk = high_risk.sort_values(
            [RATING_COLUMN, SENTIMENT_COLUMN],
            ascending=[True, True],
        ).head(settings.max_summary_review_rows)
        high_risk_records = self._renamed_records(
            high_risk[
                [
                    RATING_COLUMN,
                    SENTIMENT_COLUMN,
                    CATEGORY_COLUMN,
                    RISK_LABEL_COLUMN,
                    CONTENT_COLUMN,
                ]
            ],
            {
                RATING_COLUMN: "rating",
                SENTIMENT_COLUMN: "sentiment",
                CATEGORY_COLUMN: "category",
                RISK_LABEL_COLUMN: "risk_label",
                CONTENT_COLUMN: "content",
            },
        )
        rating_sentiment_mismatches = filtered[
            (filtered[RATING_COLUMN] >= 4)
            & (filtered[SENTIMENT_COLUMN] < LOW_SENTIMENT)
        ].copy()
        rating_sentiment_mismatch_count = int(len(rating_sentiment_mismatches))
        rating_sentiment_mismatches = rating_sentiment_mismatches.sort_values(
            [SENTIMENT_COLUMN, RATING_COLUMN],
            ascending=[True, False],
        ).head(settings.max_summary_review_rows)
        rating_sentiment_mismatch_records = self._renamed_records(
            rating_sentiment_mismatches[
                [
                    RATING_COLUMN,
                    SENTIMENT_COLUMN,
                    CATEGORY_COLUMN,
                    RISK_LABEL_COLUMN,
                    CONTENT_COLUMN,
                ]
            ],
            {
                RATING_COLUMN: "rating",
                SENTIMENT_COLUMN: "sentiment",
                CATEGORY_COLUMN: "category",
                RISK_LABEL_COLUMN: "risk_label",
                CONTENT_COLUMN: "content",
            },
        )
        review_records = self._renamed_records(
            filtered[
                [
                    RATING_COLUMN,
                    SENTIMENT_COLUMN,
                    CATEGORY_COLUMN,
                    RISK_LABEL_COLUMN,
                    CONTENT_COLUMN,
                ]
            ].head(settings.max_summary_review_rows),
            {
                RATING_COLUMN: "rating",
                SENTIMENT_COLUMN: "sentiment",
                CATEGORY_COLUMN: "category",
                RISK_LABEL_COLUMN: "risk_label",
                CONTENT_COLUMN: "content",
            },
        )
        available_categories = sorted(
            record.dataframe[CATEGORY_COLUMN].dropna().astype(str).unique().tolist()
        )

        response = AnalyticsSummaryResponse(
            sample_size=metrics["total_reviews"],
            average_rating=metrics["average_rating"],
            negative_ratio=metrics["negative_ratio"],
            average_sentiment=metrics["average_sentiment"],
            high_risk_count=metrics["high_risk_count"],
            rating_distribution=rating_records,
            sentiment_distribution=sentiment_records,
            negative_keywords=negative_keyword_records,
            positive_keywords=positive_keyword_records,
            issue_priorities=priority_records,
            trend=trend_records,
            high_risk_reviews=high_risk_records,
            rating_sentiment_mismatches=rating_sentiment_mismatch_records,
            rating_sentiment_mismatch_count=rating_sentiment_mismatch_count,
            reviews=review_records,
            available_categories=available_categories,
            scope_signature=scope_signature,
            warnings=[insight_warning] if insight_warning else [],
        )

        self._cache.set(
            cache_key,
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "payload": response.model_dump(mode="json"),
            },
            ttl_seconds=settings.cache_ttl_seconds,
        )
        return response

    def search_reviews(self, request: ReviewSearchRequest) -> ReviewSearchResponse:
        record = self._store.get(request.dataset_id)
        filtered = self._scope_service.apply_filters(record.dataframe, request.filters)
        if request.view == "high_risk":
            filtered = filtered[
                filtered[RISK_LABEL_COLUMN].apply(is_high_risk_label)
            ].sort_values([RATING_COLUMN, SENTIMENT_COLUMN], ascending=[True, True])
        elif request.view == "rating_sentiment_mismatch":
            filtered = filtered[
                (filtered[RATING_COLUMN] >= 4)
                & (filtered[SENTIMENT_COLUMN] < LOW_SENTIMENT)
            ].sort_values([SENTIMENT_COLUMN, RATING_COLUMN], ascending=[True, False])
        total = int(len(filtered))
        page = filtered.iloc[request.offset : request.offset + request.limit]
        items = self._renamed_records(
            page[
                [
                    RATING_COLUMN,
                    SENTIMENT_COLUMN,
                    CATEGORY_COLUMN,
                    RISK_LABEL_COLUMN,
                    CONTENT_COLUMN,
                ]
            ],
            {
                RATING_COLUMN: "rating",
                SENTIMENT_COLUMN: "sentiment",
                CATEGORY_COLUMN: "category",
                RISK_LABEL_COLUMN: "risk_label",
                CONTENT_COLUMN: "content",
            },
        )
        consumed = request.offset + len(items)
        return ReviewSearchResponse(
            items=items,
            total=total,
            offset=request.offset,
            limit=request.limit,
            next_offset=consumed if consumed < total else None,
        )

    def _renamed_records(
        self,
        dataframe: pd.DataFrame,
        columns: dict[str, str],
    ) -> list[dict[str, object]]:
        return dataframe_to_records(dataframe.rename(columns=columns))


def _valid_cache_payload(cached: dict) -> bool:
    """A cache entry is usable only when schema version matches and payload exists."""
    return (
        isinstance(cached, dict)
        and cached.get("schema_version") == CACHE_SCHEMA_VERSION
        and isinstance(cached.get("payload"), dict)
    )
