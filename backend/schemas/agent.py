"""Schemas for the controlled analysis Agent API."""

from typing import Any, Literal

from pydantic import Field, field_validator

from backend.schemas.analytics import ReviewFilters
from backend.schemas.common import StrictModel


class AgentQueryRequest(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=1000)
    filters: ReviewFilters = Field(default_factory=ReviewFilters)
    scope: Literal["full", "filtered"] = "filtered"
    ai_insights: dict[str, Any] | None = None
    ai_scope_signature: str | None = Field(default=None, max_length=128)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, question: str) -> str:
        normalized = question.strip()
        if not normalized:
            raise ValueError("问题不能为空")
        return normalized


class ToolCallRecord(StrictModel):
    name: str
    arguments: dict[str, Any]
    status: Literal["success", "failed", "rejected"]
    duration_ms: int = Field(ge=0)
    error: str | None = None


class AgentQueryResponse(StrictModel):
    intent: str
    answer: str
    scope: Literal["full", "filtered"]
    scope_label: str
    sample_size: int
    scope_signature: str
    tables: dict[str, list[dict[str, Any]]]
    routing: Literal["rule", "tool_calling", "rule_fallback"]
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
