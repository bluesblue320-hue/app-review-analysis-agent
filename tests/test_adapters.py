"""Shared adapter contract tests for Direct and LangChain paths.

These tests drive both adapters through the same orchestrator behaviours the
fixed evaluation gate checks: single/multi tool, over-limit truncation,
illegal tools, invalid arguments, missing key, timeout, invalid JSON, no tool
call, fake numbers and unsupported absolute claims.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from backend.agent.adapters import build_adapter
from backend.agent.adapters.langchain_adapter import LangChainUnavailableError
from backend.agent.tool_calling import ControlledToolCallingAgent
from visual_analysis import prepare_dashboard_data


def _reviews() -> pd.DataFrame:
    return prepare_dashboard_data(
        pd.DataFrame(
            [
                {
                    "评分": 1,
                    "内容": "无故封号，客服不回复",
                    "版本": "2.0.0",
                    "时间": "2026-07-01",
                },
                {
                    "评分": 3,
                    "内容": "广告太多，推荐质量下降",
                    "版本": "2.0.0",
                    "时间": "2026-07-02",
                },
                {
                    "评分": 5,
                    "内容": "内容丰富，搜索体验很好",
                    "版本": "1.9.0",
                    "时间": "2026-07-03",
                },
            ]
        )
    )


def _call(call_id: str, name: str, arguments: str = "{}") -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


class FakeModelClient:
    """Deterministic model stand-in implementing the adapter's client contract."""

    def __init__(
        self,
        tool_calls: list[dict[str, Any]],
        answer: str | dict[str, Any] = "已根据工具结果完成分析。",
        *,
        plan_error: Exception | None = None,
        synthesize_error: Exception | None = None,
    ) -> None:
        self.tool_calls = tool_calls
        self.answer = answer
        self.plan_error = plan_error
        self.synthesize_error = synthesize_error
        self.plan_count = 0
        self.synthesis_messages: list[dict[str, Any]] = []

    def plan(self, **kwargs: Any) -> dict[str, Any]:
        self.plan_count += 1
        if self.plan_error is not None:
            raise self.plan_error
        return {"role": "assistant", "content": None, "tool_calls": self.tool_calls}

    def synthesize(self, **kwargs: Any) -> Any:
        self.synthesis_messages = kwargs["tool_messages"]
        if self.synthesize_error is not None:
            raise self.synthesize_error
        return self.answer


def _direct_adapter(client: FakeModelClient):
    adapter = build_adapter("direct")
    adapter._client = client
    return adapter


def _langchain_adapter(client: FakeModelClient):
    from evaluation.evaluate_agent import _LangChainMockAdapter

    return _LangChainMockAdapter(client)


@pytest.fixture(params=["direct", "langchain"])
def adapter_factory(request):
    return _direct_adapter if request.param == "direct" else _langchain_adapter


@pytest.fixture(params=["direct", "langchain"])
def adapter_name(request) -> str:
    return request.param


def _answer(text: str, evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "answer": text,
        "limitations": [],
        "evidence_call_ids": evidence_ids or [],
    }


def test_single_tool_call(adapter_factory) -> None:
    client = FakeModelClient(
        [_call("call_1", "get_review_metrics")],
        answer=_answer("当前平均评分为 3.0。", ["call_1"]),
    )
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "tool_calling"
    assert result.tool_calls[0].name == "get_review_metrics"
    assert result.tool_calls[0].status == "success"
    assert result.evidence_call_ids == ["call_1"]


def test_multiple_tool_calls(adapter_factory) -> None:
    client = FakeModelClient(
        [
            _call("call_1", "get_review_metrics"),
            _call("call_2", "analyze_negative_reviews"),
        ]
    )
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "tool_calling"
    assert {trace.name for trace in result.tool_calls} == {
        "get_review_metrics",
        "analyze_negative_reviews",
    }


def test_more_than_three_tool_calls_are_truncated(adapter_factory) -> None:
    calls = [_call(f"call_{index}", "get_review_metrics") for index in range(5)]
    client = FakeModelClient(calls)
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert len(result.tool_calls) <= 3
    assert any("超过上限" in warning for warning in result.warnings)


def test_illegal_tool_is_rejected_and_falls_back(adapter_factory) -> None:
    client = FakeModelClient([_call("call_1", "delete_dataset")])
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"
    assert result.tool_calls[0].status == "rejected"


def test_invalid_arguments_fail_pydantic_validation(adapter_factory) -> None:
    client = FakeModelClient(
        [_call("call_1", "analyze_negative_reviews", '{"top_n": 999}')]
    )
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.tool_calls[0].status == "failed"
    assert result.routing == "rule_fallback"


def test_missing_api_key_raises_unavailable(adapter_name) -> None:
    if adapter_name == "direct":
        from backend.agent.deepseek_client import ToolCallingUnavailable

        client = FakeModelClient([], plan_error=ToolCallingUnavailable("no key"))
    else:
        client = FakeModelClient([], plan_error=LangChainUnavailableError("no key"))
    agent = ControlledToolCallingAgent(
        adapter=_direct_adapter(client)
        if adapter_name == "direct"
        else _langchain_adapter(client)
    )
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"


def test_model_timeout_falls_back(adapter_factory) -> None:
    from backend.agent.deepseek_client import ToolCallingTimeout

    client = FakeModelClient([], plan_error=ToolCallingTimeout("slow"))
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"


def test_model_no_tool_calls_falls_back(adapter_factory) -> None:
    client = FakeModelClient([])
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"
    assert "未选择分析工具" in result.warnings[0]


def test_model_invalid_json_synthesis_falls_back(adapter_factory) -> None:
    from backend.agent.deepseek_client import ToolCallingResponseError

    client = FakeModelClient(
        [_call("call_1", "get_review_metrics")],
        synthesize_error=ToolCallingResponseError("bad json"),
    )
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"


def test_fake_number_in_answer_falls_back(adapter_factory) -> None:
    client = FakeModelClient(
        [_call("call_1", "get_review_metrics")],
        answer="当前差评占比 87.5%。",
    )
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"
    assert "校验失败" in result.warnings[0]


def test_unsupported_absolute_claim_falls_back(adapter_factory) -> None:
    client = FakeModelClient(
        [_call("call_1", "get_review_metrics")],
        answer="2.0.0 是最好的版本，直接推广。",
    )
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"


def test_structured_output_failure_falls_back(adapter_factory) -> None:
    client = FakeModelClient(
        [_call("call_1", "get_review_metrics")],
        answer="",
    )
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"


def test_tool_failure_falls_back(adapter_factory) -> None:
    client = FakeModelClient(
        [_call("call_1", "analyze_negative_reviews", '{"top_n": 999}')]
    )
    agent = ControlledToolCallingAgent(adapter=adapter_factory(client))
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"
    assert result.tool_calls[0].status == "failed"
