"""Deterministic mock DeepSeek tool client for the evaluation framework.

The mock client implements the same ``plan`` / ``synthesize`` interface as
``DeepSeekToolClient`` and is driven by a per-case ``mock_plan``, so the
evaluation never contacts the real API in Mock mode.
"""

from __future__ import annotations

from typing import Any

from backend.agent.deepseek_client import (
    ToolCallingResponseError,
    ToolCallingTimeout,
    ToolCallingUnavailable,
)

DEFAULT_MOCK_ANSWER = "已根据工具结果完成分析。"

# Names used only to simulate model misbehaviour; never part of the whitelist.
ILLEGAL_TOOL_NAME = "delete_dataset"
ILLEGAL_ARGUMENT_TOOL_NAME = "analyze_negative_reviews"
ILLEGAL_ARGUMENT_PAYLOAD = {"top_n": 999}


class MockToolClient:
    """Fake DeepSeek client whose behaviour is fully controlled by ``mock_plan``.

    Supported behaviours (``mock_plan["behavior"]``):

    - ``unavailable``       -> plan raises ``ToolCallingUnavailable``
    - ``timeout``           -> plan raises ``ToolCallingTimeout``
    - ``no_tool_calls``     -> plan returns an empty tool call list
    - ``illegal_tool``      -> plan returns a non-whitelisted tool call
    - ``illegal_arguments`` -> plan returns a whitelisted tool with invalid arguments
    - ``ungrounded_answer`` -> tool calls succeed but ``mock_answer`` contains a
      number that does not exist in the tool results

    Without a behaviour, ``mock_plan["tool_calls"]`` is returned verbatim and
    ``mock_answer`` is returned by ``synthesize``.
    """

    def __init__(
        self,
        mock_plan: dict[str, Any] | None = None,
        mock_answer: str = "",
    ) -> None:
        self.mock_plan = mock_plan or {}
        self.mock_answer = mock_answer or DEFAULT_MOCK_ANSWER
        self.plan_count = 0
        self.synthesize_count = 0
        self.last_synthesis_messages: list[dict[str, Any]] = []

    def plan(self, **kwargs: Any) -> dict[str, Any]:
        self.plan_count += 1
        behavior = self.mock_plan.get("behavior")
        if behavior == "timeout":
            raise ToolCallingTimeout("Mock 模式模拟模型超时。")
        if behavior == "unavailable":
            raise ToolCallingUnavailable("Mock 模式模拟模型不可用。")
        if behavior == "response_error":
            raise ToolCallingResponseError("Mock 模式模拟响应异常。")
        if behavior == "illegal_tool":
            specs = [("call_illegal", ILLEGAL_TOOL_NAME, {})]
        elif behavior == "illegal_arguments":
            specs = [
                ("call_bad_args", ILLEGAL_ARGUMENT_TOOL_NAME, ILLEGAL_ARGUMENT_PAYLOAD)
            ]
        elif behavior == "no_tool_calls":
            specs = []
        elif behavior == "ungrounded_answer":
            specs = [("call_metrics", "get_review_metrics", {})]
        else:
            specs = [
                (
                    str(item.get("id") or f"call_{index}"),
                    str(item["name"]),
                    item.get("arguments", {}),
                )
                for index, item in enumerate(self.mock_plan.get("tool_calls") or [])
            ]
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                self._call(call_id, name, arguments)
                for call_id, name, arguments in specs
            ],
        }

    def synthesize(self, **kwargs: Any) -> str:
        self.synthesize_count += 1
        self.last_synthesis_messages = kwargs.get("tool_messages") or []
        if self.mock_plan.get("behavior") == "synthesize_error":
            raise ToolCallingResponseError("Mock 模式模拟合成回答失败。")
        if self.mock_plan.get("behavior") == "ungrounded_answer":
            return "当前共有 999 条有效评论，平均评分 9.99。"
        return self.mock_answer

    @staticmethod
    def _call(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        import json

        return {
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            },
        }
