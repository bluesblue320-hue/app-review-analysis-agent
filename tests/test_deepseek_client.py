"""DeepSeek client synthesis and chat error handling."""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.agent.deepseek_client import (
    DeepSeekToolClient,
    ToolCallingResponseError,
    ToolCallingUnavailable,
)


def _response(payload: dict[str, Any], status_code: int = 200):
    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = status_code

        def json(self) -> dict[str, Any]:
            return payload

    return _FakeResponse()


def _config() -> dict[str, Any]:
    return {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "api_key": "mock-key",
        "base_url": "https://example.invalid/chat",
    }


def _client(post_func) -> DeepSeekToolClient:
    return DeepSeekToolClient(
        post_func=post_func,
        config_loader=_config,
        timeout_seconds=1,
    )


def _message(content: str | None = None, tool_calls: list | None = None):
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def test_synthesize_accepts_valid_json_with_evidence_ids() -> None:
    calls: list[dict[str, Any]] = []

    def post(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs.get("json"))
        return _response(
            _message(
                json.dumps(
                    {
                        "answer": "结论：平均评分 3.0。",
                        "limitations": ["缺少用户级数据"],
                        "evidence_call_ids": ["call_a"],
                    },
                    ensure_ascii=False,
                )
            )
        )

    client = _client(post)
    result = client.synthesize(
        question="综合对比指标？",
        scope_label="当前筛选数据",
        assistant_message={"role": "assistant", "tool_calls": []},
        tool_messages=[{"role": "tool", "tool_call_id": "call_a", "content": "{}"}],
        tools=[],
    )
    assert result["answer"] == "结论：平均评分 3.0。"
    assert result["limitations"] == ["缺少用户级数据"]
    assert result["evidence_call_ids"] == ["call_a"]
    sent = calls[0]
    # User question is PII-redacted before leaving the process.
    assert "分析范围：当前筛选数据" in sent["messages"][1]["content"]


def test_synthesize_rejects_unknown_evidence_id() -> None:
    def post(*args: Any, **kwargs: Any) -> Any:
        return _response(
            _message(
                json.dumps(
                    {
                        "answer": "结论：平均评分 3.0。",
                        "evidence_call_ids": ["call_missing"],
                    },
                    ensure_ascii=False,
                )
            )
        )

    client = _client(post)
    with pytest.raises(ToolCallingResponseError):
        client.synthesize(
            question="问题？",
            scope_label="当前筛选数据",
            assistant_message={"role": "assistant", "tool_calls": []},
            tool_messages=[{"role": "tool", "tool_call_id": "call_a", "content": "{}"}],
            tools=[],
        )


def test_synthesize_rejects_invalid_json() -> None:
    def post(*args: Any, **kwargs: Any) -> Any:
        return _response(_message("不是 JSON"))

    client = _client(post)
    with pytest.raises(ToolCallingResponseError):
        client.synthesize(
            question="问题？",
            scope_label="当前筛选数据",
            assistant_message={"role": "assistant", "tool_calls": []},
            tool_messages=[],
            tools=[],
        )


def test_synthesize_rejects_empty_answer() -> None:
    def post(*args: Any, **kwargs: Any) -> Any:
        return _response(_message(json.dumps({"answer": "  "})))

    client = _client(post)
    with pytest.raises(ToolCallingResponseError):
        client.synthesize(
            question="问题？",
            scope_label="当前筛选数据",
            assistant_message={"role": "assistant", "tool_calls": []},
            tool_messages=[],
            tools=[],
        )


def test_chat_requires_deepseek_provider() -> None:
    client = DeepSeekToolClient(
        post_func=lambda *a, **k: None,
        config_loader=lambda: {"provider": "other", "api_key": "k"},
        timeout_seconds=1,
    )
    with pytest.raises(ToolCallingUnavailable):
        client.plan(question="问题？", scope_label="完整上传数据", tools=[])


def test_chat_requires_api_key() -> None:
    client = DeepSeekToolClient(
        post_func=lambda *a, **k: None,
        config_loader=lambda: {"provider": "deepseek", "api_key": ""},
        timeout_seconds=1,
    )
    with pytest.raises(ToolCallingUnavailable):
        client.plan(question="问题？", scope_label="完整上传数据", tools=[])


def test_chat_raises_on_non_200_status() -> None:
    def post(*args: Any, **kwargs: Any) -> Any:
        return _response({"error": "boom"}, status_code=500)

    client = _client(post)
    with pytest.raises(ToolCallingResponseError):
        client.plan(question="问题？", scope_label="完整上传数据", tools=[])


def test_chat_raises_on_malformed_choices() -> None:
    def post(*args: Any, **kwargs: Any) -> Any:
        return _response({"choices": []})

    client = _client(post)
    with pytest.raises(ToolCallingResponseError):
        client.plan(question="问题？", scope_label="完整上传数据", tools=[])


def test_chat_raises_on_request_exception() -> None:
    import requests

    def post(*args: Any, **kwargs: Any) -> Any:
        raise requests.ConnectionError("down")

    client = _client(post)
    with pytest.raises(ToolCallingUnavailable):
        client.plan(question="问题？", scope_label="完整上传数据", tools=[])
