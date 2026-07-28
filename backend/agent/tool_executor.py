"""Validate and execute whitelisted read-only analysis tools."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, ValidationError

from agent_workflow import (
    run_general_analysis,
    run_negative_review_analysis,
    run_positive_review_analysis,
    run_product_suggestion,
    run_risk_review_analysis,
    run_trend_analysis,
    run_version_analysis,
)
from backend.agent.tool_definitions import ALLOWED_TOOL_NAMES, TOOL_REGISTRY
from backend.core.serialization import dataframe_to_records
from review_fields import (
    CATEGORY_COLUMN,
    CONTENT_COLUMN,
    RATING_COLUMN,
    RISK_LABEL_COLUMN,
    SENTIMENT_COLUMN,
    VERSION_COLUMN,
)
from visual_analysis import calculate_priority_table, is_high_risk_label, prepare_dashboard_data


logger = logging.getLogger(__name__)


class ToolCallTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any]
    status: Literal["success", "failed", "rejected"]
    duration_ms: int
    error: str | None = None


@dataclass(frozen=True)
class ToolExecutionResult:
    trace: ToolCallTrace
    output: dict[str, Any] | None
    tool_call_id: str


class ToolExecutor:
    def execute(
        self,
        *,
        tool_call_id: str,
        name: str,
        arguments: str | dict[str, Any] | None,
        dataframe: pd.DataFrame,
        ai_insights: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        started_at = perf_counter()
        parsed_arguments: dict[str, Any] = {}

        if name not in ALLOWED_TOOL_NAMES:
            return self._result(
                tool_call_id,
                name,
                parsed_arguments,
                "rejected",
                started_at,
                error="工具名称不在白名单中。",
            )

        try:
            parsed_arguments = self._parse_arguments(arguments)
            validated = TOOL_REGISTRY[name].arguments_model.model_validate(parsed_arguments)
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            return self._result(
                tool_call_id,
                name,
                parsed_arguments,
                "failed",
                started_at,
                error=f"工具参数校验失败：{exc}",
            )

        try:
            output = self._dispatch(
                name,
                validated.model_dump(),
                dataframe.copy(deep=True),
                ai_insights,
            )
        except Exception as exc:  # execution boundary must not crash the Agent
            logger.exception("Analysis tool failed: name=%s", name)
            return self._result(
                tool_call_id,
                name,
                validated.model_dump(),
                "failed",
                started_at,
                error=f"工具执行失败：{type(exc).__name__}",
            )

        return self._result(
            tool_call_id,
            name,
            validated.model_dump(),
            "success",
            started_at,
            output=output,
        )

    @staticmethod
    def _parse_arguments(
        arguments: str | dict[str, Any] | None,
    ) -> dict[str, Any]:
        if arguments in (None, ""):
            return {}
        if isinstance(arguments, dict):
            return arguments
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise TypeError("工具参数必须是 JSON 对象")
        return parsed

    def _dispatch(
        self,
        name: str,
        arguments: dict[str, Any],
        dataframe: pd.DataFrame,
        ai_insights: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if name == "get_review_metrics":
            result = run_general_analysis("基础指标", dataframe, ai_insights=ai_insights)
            return self._workflow_output(result, len(prepare_dashboard_data(dataframe)))

        if name == "analyze_negative_reviews":
            prepared = prepare_dashboard_data(dataframe)
            result = run_negative_review_analysis("差评分析", prepared, ai_insights=ai_insights)
            result["dataframes"]["差评关键词"] = result["dataframes"]["差评关键词"].head(
                arguments["top_n"]
            )
            sample_size = int((prepared[RATING_COLUMN] <= 3).sum())
            return self._workflow_output(result, sample_size)

        if name == "analyze_positive_reviews":
            prepared = prepare_dashboard_data(dataframe)
            result = run_positive_review_analysis("好评分析", prepared)
            result["dataframes"]["好评关键词"] = result["dataframes"]["好评关键词"].head(
                arguments["top_n"]
            )
            sample_size = int((prepared[RATING_COLUMN] >= 4).sum())
            return self._workflow_output(result, sample_size)

        if name == "find_high_risk_reviews":
            prepared = prepare_dashboard_data(dataframe)
            result = run_risk_review_analysis("高风险评论", prepared)
            sample_size = int(
                prepared[RISK_LABEL_COLUMN].apply(is_high_risk_label).sum()
            )
            return self._workflow_output(result, sample_size)

        if name == "compare_versions":
            prepared = prepare_dashboard_data(dataframe)
            versions = arguments["versions"]
            if versions and VERSION_COLUMN in prepared.columns:
                prepared = prepared[
                    prepared[VERSION_COLUMN].astype(str).isin(versions)
                ].copy()
            result = run_version_analysis("版本对比", prepared)
            return self._workflow_output(result, len(prepared))

        if name == "analyze_sentiment_trend":
            prepared = prepare_dashboard_data(dataframe)
            result = run_trend_analysis("趋势分析", prepared)
            return self._workflow_output(result, len(prepared))

        if name == "calculate_issue_priority":
            prepared = prepare_dashboard_data(dataframe)
            result = run_product_suggestion(
                "产品优化建议",
                prepared,
                ai_insights=ai_insights,
            )
            result["dataframes"]["问题优先级"] = calculate_priority_table(
                prepared,
                ai_insights=ai_insights,
                top_n=arguments["top_n"],
            )
            return self._workflow_output(result, len(prepared))

        if name == "retrieve_representative_reviews":
            return self._representative_reviews(dataframe, arguments)

        raise ValueError(f"未实现的工具：{name}")

    @staticmethod
    def _representative_reviews(
        dataframe: pd.DataFrame,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        prepared = prepare_dashboard_data(dataframe)
        selected = prepared
        review_type = arguments["review_type"]
        if review_type == "negative":
            selected = selected[selected[RATING_COLUMN] <= 3]
        elif review_type == "positive":
            selected = selected[selected[RATING_COLUMN] >= 4]
        elif review_type == "high_risk":
            selected = selected[selected[RISK_LABEL_COLUMN].apply(is_high_risk_label)]
        if arguments["category"]:
            selected = selected[selected[CATEGORY_COLUMN] == arguments["category"]]

        selected = selected.sort_values(
            [RATING_COLUMN, SENTIMENT_COLUMN],
            ascending=[True, True],
        )
        columns = [
            RATING_COLUMN,
            SENTIMENT_COLUMN,
            CATEGORY_COLUMN,
            RISK_LABEL_COLUMN,
            CONTENT_COLUMN,
        ]
        records = dataframe_to_records(selected[columns].head(arguments["limit"]))
        return {
            "answer": f"返回 {len(records)} 条代表评论。",
            "sample_size": int(len(selected)),
            "tables": {"代表评论": records},
        }

    @staticmethod
    def _workflow_output(
        result: dict[str, Any],
        sample_size: int,
    ) -> dict[str, Any]:
        return {
            "answer": str(result["answer"]),
            "sample_size": int(sample_size),
            "tables": {
                name: dataframe_to_records(table)
                for name, table in result["dataframes"].items()
                if isinstance(table, pd.DataFrame)
            },
        }

    @staticmethod
    def _result(
        tool_call_id: str,
        name: str,
        arguments: dict[str, Any],
        status: Literal["success", "failed", "rejected"],
        started_at: float,
        *,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ToolExecutionResult:
        duration_ms = max(0, round((perf_counter() - started_at) * 1000))
        return ToolExecutionResult(
            trace=ToolCallTrace(
                name=name,
                arguments=arguments,
                status=status,
                duration_ms=duration_ms,
                error=error,
            ),
            output=output,
            tool_call_id=tool_call_id,
        )
