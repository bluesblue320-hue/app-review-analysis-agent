"""Deterministic analytics assembled from the existing pandas functions."""

from __future__ import annotations

import pandas as pd

from agent_workflow import dataframe_scope_signature, match_ai_insights
from backend.core.config import settings
from backend.core.serialization import dataframe_to_records
from backend.schemas.analytics import AnalyticsSummaryRequest, AnalyticsSummaryResponse
from backend.services.dataset_service import InMemoryDatasetStore
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
    calculate_health_metrics,
    calculate_priority_table,
    extract_keyword_scores,
    is_high_risk_label,
    rating_distribution,
    sentiment_distribution,
    sentiment_trend,
)


class AnalyticsService:
    def __init__(self, store: InMemoryDatasetStore) -> None:
        self._store = store
        self._scope_service = ReviewScopeService(store)

    def build_summary(
        self,
        request: AnalyticsSummaryRequest,
    ) -> AnalyticsSummaryResponse:
        record = self._store.get(request.dataset_id)
        filtered = self._scope_service.get_dataframe(
            request.dataset_id,
            request.filters,
        )
        current_insights = match_ai_insights(
            request.ai_insights,
            request.ai_scope_signature,
            filtered,
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

        return AnalyticsSummaryResponse(
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
            reviews=review_records,
            available_categories=available_categories,
            scope_signature=dataframe_scope_signature(filtered),
        )

    @staticmethod
    def _renamed_records(
        dataframe: pd.DataFrame,
        columns: dict[str, str],
    ) -> list[dict[str, object]]:
        return dataframe_to_records(dataframe.rename(columns=columns))
