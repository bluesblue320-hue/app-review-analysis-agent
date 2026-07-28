"""Whitelisted read-only tool definitions and Pydantic arguments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyArguments(ToolArguments):
    pass


class KeywordAnalysisArguments(ToolArguments):
    top_n: int = Field(default=15, ge=1, le=30)


class CompareVersionsArguments(ToolArguments):
    versions: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("versions")
    @classmethod
    def normalize_versions(cls, versions: list[str]) -> list[str]:
        normalized = [version.strip() for version in versions if version.strip()]
        return list(dict.fromkeys(normalized))


class IssuePriorityArguments(ToolArguments):
    top_n: int = Field(default=5, ge=1, le=10)


class RepresentativeReviewsArguments(ToolArguments):
    review_type: Literal["all", "negative", "positive", "high_risk"] = "all"
    category: str | None = Field(default=None, max_length=50)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("category")
    @classmethod
    def normalize_category(cls, category: str | None) -> str | None:
        if category is None:
            return None
        return category.strip() or None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments_model: type[ToolArguments]

    def as_deepseek_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arguments_model.model_json_schema(),
            },
        }


TOOL_SPECS = (
    ToolSpec(
        "get_review_metrics",
        "获取当前评论范围的评论数、平均评分、差评占比、平均情绪和高风险数量。",
        EmptyArguments,
    ),
    ToolSpec(
        "analyze_negative_reviews",
        "分析 1-3 星差评，返回差评占比、关键词、问题优先级和典型差评。",
        KeywordAnalysisArguments,
    ),
    ToolSpec(
        "analyze_positive_reviews",
        "分析 4-5 星好评，返回好评占比和正向关键词。",
        KeywordAnalysisArguments,
    ),
    ToolSpec(
        "find_high_risk_reviews",
        "查找低星、极端负面或高星低情绪的高风险评论。",
        EmptyArguments,
    ),
    ToolSpec(
        "compare_versions",
        "比较指定版本或数据中的全部版本，返回评论数、评分、情绪和差评占比。",
        CompareVersionsArguments,
    ),
    ToolSpec(
        "analyze_sentiment_trend",
        "按日期分析平均评分、平均情绪和评论数量趋势。",
        EmptyArguments,
    ),
    ToolSpec(
        "calculate_issue_priority",
        "计算问题类别优先级并返回确定性排序、严重度和代表评论。",
        IssuePriorityArguments,
    ),
    ToolSpec(
        "retrieve_representative_reviews",
        "按评论类型和问题类别检索有限数量的代表评论。",
        RepresentativeReviewsArguments,
    ),
)

TOOL_REGISTRY = {spec.name: spec for spec in TOOL_SPECS}
ALLOWED_TOOL_NAMES = frozenset(TOOL_REGISTRY)


def deepseek_tool_definitions() -> list[dict[str, object]]:
    return [spec.as_deepseek_tool() for spec in TOOL_SPECS]
