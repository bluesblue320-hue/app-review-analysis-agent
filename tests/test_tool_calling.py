from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
import requests

from backend.agent.deepseek_client import DeepSeekToolClient, ToolCallingTimeout
from backend.agent.tool_calling import ControlledToolCallingAgent
from visual_analysis import prepare_dashboard_data


def _reviews() -> pd.DataFrame:
    return prepare_dashboard_data(
        pd.DataFrame(
            [
                {
                    "评分": 1,
                    "内容": "无故封号，人工客服不回复",
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


class FakeToolClient:
    def __init__(
        self,
        tool_calls: list[dict[str, Any]],
        answer: str = "已根据工具结果完成分析。",
    ) -> None:
        self.tool_calls = tool_calls
        self.answer = answer
        self.plan_count = 0
        self.synthesis_messages: list[dict[str, Any]] = []

    def plan(self, **kwargs: Any) -> dict[str, Any]:
        self.plan_count += 1
        return {"role": "assistant", "content": None, "tool_calls": self.tool_calls}

    def synthesize(self, **kwargs: Any) -> str:
        self.synthesis_messages = kwargs["tool_messages"]
        return self.answer


class TimeoutToolClient:
    def plan(self, **kwargs: Any) -> dict[str, Any]:
        raise ToolCallingTimeout("mock timeout")


def test_simple_question_uses_rule_tool_without_deepseek() -> None:
    client = FakeToolClient([])
    agent = ControlledToolCallingAgent(tool_client=client)

    result = agent.run(
        question="哪个版本问题最多？",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )

    assert result.routing == "rule"
    assert client.plan_count == 0
    assert result.tool_calls[0].name == "compare_versions"
    assert result.tool_calls[0].status == "success"


def test_short_general_question_stays_on_fast_rule_route() -> None:
    client = FakeToolClient([])
    agent = ControlledToolCallingAgent(tool_client=client)

    result = agent.run(
        question="看看当前数据",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )

    assert result.routing == "rule"
    assert client.plan_count == 0
    assert result.tool_calls[0].name == "get_review_metrics"


def test_complex_question_executes_single_mocked_tool_call() -> None:
    client = FakeToolClient(
        [_call("call_metrics", "get_review_metrics")],
        answer="当前共有 3 条有效评论。",
    )
    agent = ControlledToolCallingAgent(tool_client=client)

    result = agent.run(
        question="请综合判断当前评论表现并给出结论",
        dataframe=_reviews(),
        scope_label="当前筛选结果",
    )

    assert result.routing == "tool_calling"
    assert [trace.name for trace in result.tool_calls] == ["get_review_metrics"]
    assert result.tool_calls[0].status == "success"
    assert result.evidence["call_metrics"]["sample_size"] == 3
    assert client.synthesis_messages[0]["tool_call_id"] == "call_metrics"


def test_complex_question_executes_multiple_mocked_tool_calls() -> None:
    client = FakeToolClient(
        [
            _call("call_negative", "analyze_negative_reviews", '{"top_n": 5}'),
            _call("call_versions", "compare_versions"),
        ]
    )
    agent = ControlledToolCallingAgent(tool_client=client)

    result = agent.run(
        question="综合比较差评问题和版本表现",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )

    assert result.routing == "tool_calling"
    assert [trace.status for trace in result.tool_calls] == ["success", "success"]
    assert set(result.evidence) == {"call_negative", "call_versions"}
    assert "差评关键词" in result.tables
    assert "版本分析" in result.tables


def test_illegal_tool_is_rejected_and_falls_back_to_rules() -> None:
    client = FakeToolClient([_call("call_bad", "delete_dataset")])
    agent = ControlledToolCallingAgent(tool_client=client)

    result = agent.run(
        question="请综合诊断这些评论",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )

    assert result.routing == "rule_fallback"
    assert result.tool_calls[0].name == "delete_dataset"
    assert result.tool_calls[0].status == "rejected"
    assert "白名单" in (result.tool_calls[0].error or "")


def test_invalid_tool_arguments_fail_pydantic_validation() -> None:
    client = FakeToolClient(
        [_call("call_bad_args", "analyze_negative_reviews", '{"top_n": 999}')]
    )
    agent = ControlledToolCallingAgent(tool_client=client)

    result = agent.run(
        question="请综合诊断这些评论",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )

    assert result.routing == "rule_fallback"
    assert result.tool_calls[0].status == "failed"
    assert "参数校验失败" in (result.tool_calls[0].error or "")


def test_model_timeout_falls_back_without_real_request() -> None:
    agent = ControlledToolCallingAgent(tool_client=TimeoutToolClient())

    result = agent.run(
        question="请综合诊断这些评论",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )

    assert result.routing == "rule_fallback"
    assert result.tool_calls == []
    assert any("ToolCallingTimeout" in warning for warning in result.warnings)


def test_more_than_three_model_calls_are_truncated() -> None:
    client = FakeToolClient(
        [
            _call("call_1", "get_review_metrics"),
            _call("call_2", "analyze_negative_reviews"),
            _call("call_3", "compare_versions"),
            _call("call_4", "find_high_risk_reviews"),
        ]
    )
    agent = ControlledToolCallingAgent(tool_client=client, max_tool_calls=3)

    result = agent.run(
        question="请综合分析差评、版本和整体风险",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )

    assert result.routing == "tool_calling"
    assert len(result.tool_calls) == 3
    assert all(trace.name != "find_high_risk_reviews" for trace in result.tool_calls)
    assert any("仅执行前 3 个工具" in warning for warning in result.warnings)


def test_ungrounded_number_in_model_answer_triggers_rule_fallback() -> None:
    client = FakeToolClient(
        [_call("call_metrics", "get_review_metrics")],
        answer="当前共有 999 条有效评论。",
    )
    agent = ControlledToolCallingAgent(tool_client=client)

    result = agent.run(
        question="请综合判断当前评论表现",
        dataframe=_reviews(),
        scope_label="完整上传数据",
    )

    assert result.routing == "rule_fallback"
    assert any("回答校验失败" in warning for warning in result.warnings)


def test_deepseek_client_converts_mocked_requests_timeout() -> None:
    def timeout_post(*args: Any, **kwargs: Any) -> Any:
        raise requests.Timeout("mock timeout")

    client = DeepSeekToolClient(
        post_func=timeout_post,
        config_loader=lambda: {
            "provider": "deepseek",
            "model": "mock-model",
            "api_key": "mock-key",
            "base_url": "https://example.invalid/chat",
        },
        timeout_seconds=1,
    )

    with pytest.raises(ToolCallingTimeout):
        client.plan(question="复杂问题", scope_label="完整上传数据", tools=[])
