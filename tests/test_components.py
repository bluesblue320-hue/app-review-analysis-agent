"""Stage 6: Streamlit component pure-function tests."""

from __future__ import annotations

from frontend.components import (
    filters_payload,
    keyword_dataframe,
    priority_dataframe,
    review_dataframe,
)


class TestFiltersPayload:
    def test_builds_payload_from_widget_values(self) -> None:
        payload = filters_payload(
            rating_range=(1, 5),
            sentiment_range=(0, 100),
            selected_categories=["功能", "账号"],
            keyword_query=" 封号 ",
            high_risk_only=True,
        )
        assert payload["rating_min"] == 1
        assert payload["rating_max"] == 5
        assert payload["sentiment_min"] == 0
        assert payload["sentiment_max"] == 100
        assert payload["categories"] == ["功能", "账号"]
        assert payload["keyword"] == "封号"
        assert payload["high_risk_only"] is True

    def test_empty_categories_and_keyword(self) -> None:
        payload = filters_payload(
            rating_range=(2, 4),
            sentiment_range=(10, 90),
            selected_categories=[],
            keyword_query="",
            high_risk_only=False,
        )
        assert payload["categories"] == []
        assert payload["keyword"] == ""


class TestDataframeHelpers:
    def test_review_dataframe_renames_api_fields(self) -> None:
        frame = review_dataframe(
            [
                {
                    "rating": 1,
                    "sentiment": 5,
                    "category": "账号",
                    "risk_label": "高风险",
                    "content": "无故封号",
                    "version": "2.0.0",
                }
            ]
        )
        assert list(frame.columns) == [
            "评分",
            "情绪指数",
            "问题类型",
            "风险标签",
            "内容",
            "版本",
        ]
        assert frame.iloc[0]["评分"] == 1

    def test_review_dataframe_empty(self) -> None:
        assert review_dataframe([]).empty

    def test_keyword_dataframe_renames(self) -> None:
        frame = keyword_dataframe([{"keyword": "封号", "weight": 0.9}])
        assert list(frame.columns) == ["关键词", "权重"]

    def test_priority_dataframe_renames(self) -> None:
        frame = priority_dataframe(
            [
                {
                    "category": "账号",
                    "priority_score": 9.0,
                    "severity": "high",
                    "review_count": 5,
                    "average_rating": 1.2,
                    "average_sentiment": 8.0,
                    "ai_severity": 0.8,
                    "ai_recommendation": "建议",
                    "representative_review": "代表",
                }
            ]
        )
        assert "问题类型" in frame.columns
        assert "优先级分数" in frame.columns
        assert frame.iloc[0]["问题类型"] == "账号"
