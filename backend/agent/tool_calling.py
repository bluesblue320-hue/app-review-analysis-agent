"""Controlled rule routing and DeepSeek tool-calling orchestration."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

from agent_workflow import run_agent
from backend.agent.deepseek_client import DeepSeekToolClient, ToolCallingError
from backend.agent.tool_definitions import deepseek_tool_definitions
from backend.agent.tool_executor import ToolCallTrace, ToolExecutionResult, ToolExecutor
from backend.core.config import settings
from backend.core.serialization import dataframe_to_records
from intent_router import GENERAL_INTENT, INTENT_RULES, detect_intent


RoutingMode = Literal["rule", "tool_calling", "rule_fallback"]
FAST_RULE_TOOLS = {
    "negative_review_analysis": ("analyze_negative_reviews", {}),
    "risk_review_analysis": ("find_high_risk_reviews", {}),
    "positive_review_analysis": ("analyze_positive_reviews", {}),
    "version_analysis": ("compare_versions", {}),
    "trend_analysis": ("analyze_sentiment_trend", {}),
    "general_analysis": ("get_review_metrics", {}),
}
COMPLEX_RULE_INTENTS = {"product_suggestion", "report_generation"}
FAST_GENERAL_KEYWORDS = ("多少", "平均", "占比", "指标", "概览", "概况", "评论数")
COMPLEX_QUESTION_KEYWORDS = (
    "综合",
    "同时",
    "以及",
    "并给",
    "对比",
    "建议",
    "报告",
    "诊断",
    "归因",
    "为什么",
    "原因",
)
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)*(?:%)?")
ORDERED_LIST_PREFIX = re.compile(r"(?m)^\s*\d+[.)、]\s*")


@dataclass(frozen=True)
class ControlledAgentResult:
    intent: str
    answer: str
    routing: RoutingMode
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class ControlledToolCallingAgent:
    def __init__(
        self,
        *,
        tool_client: DeepSeekToolClient | None = None,
        tool_executor: ToolExecutor | None = None,
        max_tool_calls: int | None = None,
    ) -> None:
        self._tool_client = tool_client or DeepSeekToolClient()
        self._tool_executor = tool_executor or ToolExecutor()
        configured_limit = max_tool_calls or settings.llm_max_tool_calls
        self._max_tool_calls = min(max(1, configured_limit), 3)

    def run(
        self,
        *,
        question: str,
        dataframe: pd.DataFrame,
        scope_label: str,
        ai_insights: dict[str, Any] | None = None,
    ) -> ControlledAgentResult:
        intent = detect_intent(question)
        if self._is_fast_rule_question(question, intent):
            return self._run_fast_rule(
                question=question,
                intent=intent,
                dataframe=dataframe,
                scope_label=scope_label,
                ai_insights=ai_insights,
            )
        return self._run_tool_calling(
            question=question,
            intent=intent,
            dataframe=dataframe,
            scope_label=scope_label,
            ai_insights=ai_insights,
        )

    @staticmethod
    def _is_fast_rule_question(question: str, intent: str) -> bool:
        matching_intents = [
            rule_intent
            for rule_intent, keywords in INTENT_RULES
            if any(keyword in question for keyword in keywords)
        ]
        if len(matching_intents) == 1:
            return intent in FAST_RULE_TOOLS and intent not in COMPLEX_RULE_INTENTS
        if not matching_intents and intent == GENERAL_INTENT:
            has_general_metric = any(
                keyword in question for keyword in FAST_GENERAL_KEYWORDS
            )
            has_complex_request = any(
                keyword in question for keyword in COMPLEX_QUESTION_KEYWORDS
            )
            return has_general_metric or (
                len(question.strip()) <= 24 and not has_complex_request
            )
        return False

    def _run_fast_rule(
        self,
        *,
        question: str,
        intent: str,
        dataframe: pd.DataFrame,
        scope_label: str,
        ai_insights: dict[str, Any] | None,
    ) -> ControlledAgentResult:
        tool_name, arguments = FAST_RULE_TOOLS[intent]
        execution = self._tool_executor.execute(
            tool_call_id="rule_1",
            name=tool_name,
            arguments=arguments,
            dataframe=dataframe,
            ai_insights=ai_insights,
        )
        if execution.trace.status != "success" or execution.output is None:
            return self._fallback(
                question,
                dataframe,
                scope_label,
                ai_insights,
                traces=[execution.trace],
                warning="规则分析工具执行失败，已降级到原规则工作流。",
            )
        output = execution.output
        return ControlledAgentResult(
            intent=intent,
            answer=self._scope_prefix(scope_label) + str(output["answer"]),
            routing="rule",
            tool_calls=[execution.trace],
            evidence={execution.tool_call_id: output},
            tables=dict(output.get("tables") or {}),
        )

    def _run_tool_calling(
        self,
        *,
        question: str,
        intent: str,
        dataframe: pd.DataFrame,
        scope_label: str,
        ai_insights: dict[str, Any] | None,
    ) -> ControlledAgentResult:
        definitions = deepseek_tool_definitions()
        try:
            assistant_message = self._tool_client.plan(
                question=question,
                scope_label=scope_label,
                tools=definitions,
            )
        except ToolCallingError as exc:
            return self._fallback(
                question,
                dataframe,
                scope_label,
                ai_insights,
                warning=f"模型规划失败（{type(exc).__name__}），已降级到原规则工作流。",
            )

        raw_calls = assistant_message.get("tool_calls") or []
        if not isinstance(raw_calls, list) or not raw_calls:
            return self._fallback(
                question,
                dataframe,
                scope_label,
                ai_insights,
                warning="模型未选择分析工具，已降级到原规则工作流。",
            )

        warnings: list[str] = []
        if len(raw_calls) > self._max_tool_calls:
            warnings.append(
                f"模型请求超过上限，仅执行前 {self._max_tool_calls} 个工具。"
            )
        selected_calls = raw_calls[: self._max_tool_calls]
        executions = [
            self._execute_model_call(call, index, dataframe, ai_insights)
            for index, call in enumerate(selected_calls, start=1)
        ]
        successful = [item for item in executions if item.output is not None]
        traces = [item.trace for item in executions]
        if not successful:
            return self._fallback(
                question,
                dataframe,
                scope_label,
                ai_insights,
                traces=traces,
                warnings=warnings,
                warning="模型选择的工具均未成功执行，已降级到原规则工作流。",
            )

        evidence = {item.tool_call_id: item.output for item in successful}
        tables = self._merge_tables(successful)
        tool_messages = [self._tool_message(item) for item in executions]
        try:
            answer = self._tool_client.synthesize(
                question=question,
                scope_label=scope_label,
                assistant_message={
                    **assistant_message,
                    "tool_calls": selected_calls,
                },
                tool_messages=tool_messages,
                tools=definitions,
            )
            if not self._numbers_are_grounded(answer, evidence):
                raise ValueError("模型回答包含工具结果中不存在的数字")
        except (ToolCallingError, ValueError) as exc:
            return self._fallback(
                question,
                dataframe,
                scope_label,
                ai_insights,
                traces=traces,
                warnings=warnings,
                warning=f"模型回答校验失败（{type(exc).__name__}），已降级到原规则工作流。",
            )

        return ControlledAgentResult(
            intent=intent,
            answer=self._scope_prefix(scope_label) + answer,
            routing="tool_calling",
            tool_calls=traces,
            evidence=evidence,
            tables=tables,
            warnings=warnings,
        )

    def _execute_model_call(
        self,
        call: Any,
        index: int,
        dataframe: pd.DataFrame,
        ai_insights: dict[str, Any] | None,
    ) -> ToolExecutionResult:
        call_id = f"call_{index}"
        name = ""
        arguments: Any = {}
        if isinstance(call, dict):
            call_id = str(call.get("id") or call_id)
            function = call.get("function")
            if isinstance(function, dict):
                name = str(function.get("name") or "")
                arguments = function.get("arguments")
        return self._tool_executor.execute(
            tool_call_id=call_id,
            name=name,
            arguments=arguments,
            dataframe=dataframe,
            ai_insights=ai_insights,
        )

    @staticmethod
    def _tool_message(execution: ToolExecutionResult) -> dict[str, Any]:
        if execution.output is not None:
            content = execution.output
        else:
            content = {
                "status": execution.trace.status,
                "error": execution.trace.error,
            }
        return {
            "role": "tool",
            "tool_call_id": execution.tool_call_id,
            "content": json.dumps(content, ensure_ascii=False, allow_nan=False),
        }

    @staticmethod
    def _merge_tables(
        executions: list[ToolExecutionResult],
    ) -> dict[str, list[dict[str, Any]]]:
        merged: dict[str, list[dict[str, Any]]] = {}
        for execution in executions:
            for name, records in (execution.output or {}).get("tables", {}).items():
                table_name = name
                if table_name in merged:
                    table_name = f"{execution.trace.name} - {name}"
                merged[table_name] = records
        return merged

    @staticmethod
    def _numbers_are_grounded(answer: str, evidence: dict[str, Any]) -> bool:
        evidence_text = json.dumps(evidence, ensure_ascii=False, allow_nan=False)
        cleaned_answer = ORDERED_LIST_PREFIX.sub("", answer)
        answer_numbers = {
            token.rstrip("%") for token in NUMBER_PATTERN.findall(cleaned_answer)
        }
        evidence_numbers = {
            token.rstrip("%") for token in NUMBER_PATTERN.findall(evidence_text)
        }
        return answer_numbers.issubset(evidence_numbers)

    @staticmethod
    def _scope_prefix(scope_label: str) -> str:
        return f"以下结论基于{scope_label}。\n\n"

    @staticmethod
    def _fallback(
        question: str,
        dataframe: pd.DataFrame,
        scope_label: str,
        ai_insights: dict[str, Any] | None,
        *,
        traces: list[ToolCallTrace] | None = None,
        warnings: list[str] | None = None,
        warning: str,
    ) -> ControlledAgentResult:
        result = run_agent(
            question=question,
            df=dataframe,
            ai_insights=ai_insights,
            scope=scope_label,
        )
        tables = {
            name: dataframe_to_records(table)
            for name, table in result["dataframes"].items()
            if isinstance(table, pd.DataFrame)
        }
        return ControlledAgentResult(
            intent=str(result["intent"]),
            answer=str(result["answer"]),
            routing="rule_fallback",
            tool_calls=traces or [],
            tables=tables,
            warnings=[*(warnings or []), warning],
        )
