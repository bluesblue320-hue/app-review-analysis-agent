"""Unit tests for the LangChain DeepSeek adapter helpers and error paths."""

from __future__ import annotations

from typing import Any

import pytest

from backend.agent.adapters import (
    AgentAnswer,
    AgentPlan,
    AgentPlanRequest,
    SynthesisRequest,
)
from backend.agent.adapters.langchain_adapter import (
    LangChainAdapterError,
    LangChainDeepSeekAdapter,
    LangChainUnavailableError,
    _as_ai_tool_calls,
    _assistant_message,
    _extract_tool_calls,
    _parse_answer,
    _safe_parse_arguments,
)


class FakeAIMessage:
    def __init__(
        self,
        content: Any = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class FakeChatModel:
    def __init__(
        self,
        plan_response: Any,
        synthesize_response: Any = None,
        *,
        bind_tools_raises: Exception | None = None,
        invoke_raises: Exception | None = None,
    ) -> None:
        self.plan_response = plan_response
        self.synthesize_response = synthesize_response or FakeAIMessage()
        self.bind_tools_raises = bind_tools_raises
        self.invoke_raises = invoke_raises
        self.bound_tools: list[Any] | None = None
        self.invoked_messages: list[Any] = []

    def bind_tools(self, tools: list[Any]):
        if self.bind_tools_raises is not None:
            raise self.bind_tools_raises
        self.bound_tools = tools
        outer = self

        class _Bound:
            def invoke(self, messages: list[Any]):
                outer.invoked_messages = messages
                if outer.invoke_raises is not None:
                    raise outer.invoke_raises
                return outer.plan_response

        return _Bound()

    def invoke(self, messages: list[Any], **kwargs: Any):
        self.invoked_messages = messages
        if self.invoke_raises is not None:
            raise self.invoke_raises
        return self.synthesize_response


def _adapter(chat_model: Any) -> LangChainDeepSeekAdapter:
    adapter = LangChainDeepSeekAdapter(chat_model=chat_model)
    return adapter


# --- plan_tools ---


def test_plan_tools_extracts_normalized_tool_calls() -> None:
    chat = FakeChatModel(
        FakeAIMessage(
            content=None,
            tool_calls=[
                {
                    "id": "call_lc",
                    "name": "get_review_metrics",
                    "args": {},
                }
            ],
        )
    )
    adapter = _adapter(chat)
    plan = adapter.plan_tools(
        AgentPlanRequest(
            question="综合对比各版本指标？",
            scope_label="完整上传数据",
            tools=[{"type": "function", "function": {"name": "get_review_metrics"}}],
        )
    )
    assert isinstance(plan, AgentPlan)
    assert plan.tool_calls[0]["id"] == "call_lc"
    assert plan.tool_calls[0]["function"]["name"] == "get_review_metrics"
    assert chat.bound_tools is not None


def test_plan_tools_empty_tool_calls() -> None:
    chat = FakeChatModel(FakeAIMessage(content="ok", tool_calls=[]))
    adapter = _adapter(chat)
    plan = adapter.plan_tools(
        AgentPlanRequest(question="问题？", scope_label="范围", tools=[])
    )
    assert plan.tool_calls == []


def test_plan_tools_wraps_invoke_errors() -> None:
    chat = FakeChatModel(FakeAIMessage(), invoke_raises=RuntimeError("boom"))
    adapter = _adapter(chat)
    with pytest.raises(LangChainAdapterError):
        adapter.plan_tools(
            AgentPlanRequest(question="问题？", scope_label="范围", tools=[])
        )


# --- synthesize ---


def test_synthesize_parses_json_answer() -> None:
    chat = FakeChatModel(
        FakeAIMessage(),
        FakeAIMessage(
            content='{"answer": "平均评分 3.0。", "limitations": ["缺数据"], "evidence_call_ids": ["call_1"]}'
        ),
    )
    adapter = _adapter(chat)
    answer = adapter.synthesize(
        SynthesisRequest(
            question="问题？",
            scope_label="范围",
            assistant_message={"role": "assistant", "tool_calls": []},
            tool_messages=[{"role": "tool", "tool_call_id": "call_1", "content": "{}"}],
            tools=[],
        )
    )
    assert isinstance(answer, AgentAnswer)
    assert answer.answer == "平均评分 3.0。"
    assert answer.limitations == ["缺数据"]
    assert answer.evidence_call_ids == ["call_1"]


def test_synthesize_rejects_invalid_json() -> None:
    chat = FakeChatModel(FakeAIMessage(), FakeAIMessage(content="not json"))
    adapter = _adapter(chat)
    with pytest.raises(LangChainAdapterError):
        adapter.synthesize(
            SynthesisRequest(
                question="问题？",
                scope_label="范围",
                assistant_message={},
                tool_messages=[],
                tools=[],
            )
        )


def test_synthesize_rejects_empty_answer() -> None:
    chat = FakeChatModel(FakeAIMessage(), FakeAIMessage(content="{}"))
    adapter = _adapter(chat)
    with pytest.raises(LangChainAdapterError):
        adapter.synthesize(
            SynthesisRequest(
                question="问题？",
                scope_label="范围",
                assistant_message={},
                tool_messages=[],
                tools=[],
            )
        )


def test_synthesize_rejects_non_list_fields() -> None:
    chat = FakeChatModel(
        FakeAIMessage(),
        FakeAIMessage(content='{"answer": "x", "limitations": "bad"}'),
    )
    adapter = _adapter(chat)
    with pytest.raises(LangChainAdapterError):
        adapter.synthesize(
            SynthesisRequest(
                question="问题？",
                scope_label="范围",
                assistant_message={},
                tool_messages=[],
                tools=[],
            )
        )


def test_synthesize_wraps_invoke_errors() -> None:
    chat = FakeChatModel(
        FakeAIMessage(),
        FakeAIMessage(content="{}"),
        invoke_raises=RuntimeError("down"),
    )
    adapter = _adapter(chat)
    with pytest.raises(LangChainAdapterError):
        adapter.synthesize(
            SynthesisRequest(
                question="问题？",
                scope_label="范围",
                assistant_message={},
                tool_messages=[],
                tools=[],
            )
        )


# --- lazy chat build ---


def test_lazy_chat_build_missing_key_raises() -> None:
    adapter = LangChainDeepSeekAdapter(
        config_loader=lambda: {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "",
            "base_url": "https://x",
        }
    )
    with pytest.raises(LangChainUnavailableError):
        adapter.plan_tools(AgentPlanRequest(question="q", scope_label="s", tools=[]))


def test_lazy_chat_build_wrong_provider_raises() -> None:
    adapter = LangChainDeepSeekAdapter(
        config_loader=lambda: {
            "provider": "openai",
            "model": "deepseek-chat",
            "api_key": "k",
            "base_url": "https://x",
        }
    )
    with pytest.raises(LangChainUnavailableError):
        adapter.plan_tools(AgentPlanRequest(question="q", scope_label="s", tools=[]))


# --- pure helpers ---


def test_extract_tool_calls_adds_index_id_when_missing() -> None:
    message = FakeAIMessage(
        tool_calls=[{"name": "compare_versions", "args": {"versions": ["1.9.0"]}}]
    )
    calls = _extract_tool_calls(message)
    assert calls[0]["id"].startswith("call_")
    assert calls[0]["function"]["name"] == "compare_versions"


def test_extract_tool_calls_handles_empty() -> None:
    assert _extract_tool_calls(FakeAIMessage(tool_calls=[])) == []
    assert _extract_tool_calls(FakeAIMessage(tool_calls=None)) == []


def test_assistant_message_builds_standard_shape() -> None:
    message = _assistant_message(FakeAIMessage(content="hi", tool_calls=[]), [])
    assert message["role"] == "assistant"
    assert message["content"] == "hi"


def test_as_ai_tool_calls_rebuilds_langchain_shape() -> None:
    assistant = {
        "tool_calls": [
            {
                "id": "call_1",
                "function": {"name": "get_review_metrics", "arguments": "{}"},
            }
        ]
    }
    calls = _as_ai_tool_calls(assistant)
    assert calls[0]["name"] == "get_review_metrics"
    assert calls[0]["args"] == {}


def test_safe_parse_arguments_handles_bad_input() -> None:
    assert _safe_parse_arguments(None) == {}
    assert _safe_parse_arguments("not json") == {}
    assert _safe_parse_arguments({"a": 1}) == {"a": 1}
    assert _safe_parse_arguments('{"a": 2}') == {"a": 2}


def test_parse_answer_accepts_valid_json() -> None:
    answer = _parse_answer(
        '{"answer": "ok", "limitations": [], "evidence_call_ids": ["c1"]}',
        lambda text: text,
    )
    assert answer.answer == "ok"
    assert answer.evidence_call_ids == ["c1"]


def test_parse_answer_rejects_empty_text() -> None:
    with pytest.raises(LangChainAdapterError):
        _parse_answer("   ", lambda text: text)


def test_parse_answer_rejects_non_dict() -> None:
    with pytest.raises(LangChainAdapterError):
        _parse_answer("[1, 2]", lambda text: text)
