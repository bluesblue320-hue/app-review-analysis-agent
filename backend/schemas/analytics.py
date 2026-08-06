"""Pydantic schemas for deterministic review analytics."""

from __future__ import annotations
from typing import Literal


from pydantic import Field, field_validator, model_validator

from backend.schemas.common import StrictModel


class ReviewFilters(StrictModel):
    rating_min: float = Field(default=1, ge=1, le=5)
    rating_max: float = Field(default=5, ge=1, le=5)
    sentiment_min: float = Field(default=0, ge=0, le=100)
    sentiment_max: float = Field(default=100, ge=0, le=100)
    categories: list[str] = Field(default_factory=list, max_length=100)
    keyword: str = Field(default="", max_length=200)
    high_risk_only: bool = False

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, categories: list[str]) -> list[str]:
        return list(dict.fromkeys(category.strip() for category in categories if category.strip()))

    @field_validator("keyword")
    @classmethod
    def normalize_keyword(cls, keyword: str) -> str:
        return keyword.strip()

    @model_validator(mode="after")
    def validate_ranges(self) -> "ReviewFilters":
        if self.rating_min > self.rating_max:
            raise ValueError("rating_min 不能大于 rating_max")
        if self.sentiment_min > self.sentiment_max:
            raise ValueError("sentiment_min 不能大于 sentiment_max")
        return self


class AnalyticsSummaryRequest(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=100)
    filters: ReviewFilters = Field(default_factory=ReviewFilters)
    insight_id: str | None = Field(default=None, min_length=1, max_length=100)

class ReviewSearchRequest(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=100)
    filters: ReviewFilters = Field(default_factory=ReviewFilters)
    view: Literal["all", "high_risk", "rating_sentiment_mismatch"] = "all"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)



class RatingDistributionItem(StrictModel):
    rating: int
    review_count: int


class SentimentDistributionItem(StrictModel):
    range: str
    review_count: int


class KeywordItem(StrictModel):
    keyword: str
    weight: float


class IssuePriorityItem(StrictModel):
    category: str
    priority_score: float
    severity: str
    review_count: int
    average_rating: float
    average_sentiment: float
    ai_severity: float
    ai_recommendation: str
    representative_review: str


class TrendItem(StrictModel):
    date: str
    average_sentiment: float
    average_rating: float
    review_count: int


class HighRiskReviewItem(StrictModel):
    rating: float
    sentiment: float
    category: str
    risk_label: str
    content: str


class ReviewPreviewItem(StrictModel):
    rating: float
    sentiment: float
    category: str
    risk_label: str
    content: str


class RatingSentimentMismatchItem(StrictModel):
    rating: float
    sentiment: float
    category: str
    risk_label: str
    content: str


class ReviewSearchResponse(StrictModel):
    items: list[ReviewPreviewItem]
    total: int
    offset: int
    limit: int
    next_offset: int | None = None


class AnalyticsSummaryResponse(StrictModel):
    sample_size: int
    average_rating: float
    negative_ratio: float
    average_sentiment: float
    high_risk_count: int
    rating_distribution: list[RatingDistributionItem]
    sentiment_distribution: list[SentimentDistributionItem]
    negative_keywords: list[KeywordItem]
    positive_keywords: list[KeywordItem]
    issue_priorities: list[IssuePriorityItem]
    trend: list[TrendItem]
    high_risk_reviews: list[HighRiskReviewItem]
    rating_sentiment_mismatches: list[RatingSentimentMismatchItem]
    rating_sentiment_mismatch_count: int
    reviews: list[ReviewPreviewItem]
    available_categories: list[str]
    scope_signature: str
    warnings: list[str] = Field(default_factory=list)
