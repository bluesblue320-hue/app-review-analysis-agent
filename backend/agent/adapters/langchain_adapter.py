"""LangChain DeepSeek adapter using ChatDeepSeek.bind_tools.

The adapter performs a single model round-trip for planning and one for
synthesis. The bounded multi-tool loop (at most three tool calls) lives in
the shared orchestrator, which keeps ownership of the tool whitelist,
Pydantic validation, evidence checks, guardrails and rule fallback. The
adapter never runs business analysis itself.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ai_analysis import load_ai_config
from backend.agent.adapters import (
    AgentAnswer,
    AgentPlan,
    AgentPlanRequest,
    SynthesisRequest,
)
from backend.core.privacy import redact_text


class LangChainUnavailableError(RuntimeError):
    """Raised when langchain-deepseek cannot be imported or configured."""


class LangChainAdapterError(RuntimeError):
    """Raised on recoverable model-side failures within the LangChain path."""


def _build_chat_model(
    config: dict[str, Any],
    *,
    timeout_seconds: int | None = None,
):
    try:
        from langchain_deepseek import ChatDeepSeek
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise LangChainUnavailableError(
            "未安装 langchain-deepseek，无法使用 LangChain Adapter。"
        ) from exc

    api_key = str(config.get("api_key") or "").strip()
    if not api_key:
        raise LangChainUnavailableError("未配置 DEEPSEEK_API_KEY。")
    if str(config.get("provider") or "") != "deepseek":
        raise LangChainUnavailableError("当前 AI_PROVIDER 不是 deepseek。")

    from backend.services.repositories import DEFAULT_AI_MODEL

    return ChatDeepSeek(
        model=str(config.get("model") or DEFAULT_AI_MODEL),
        api_key=api_key,
        base_url=str(config.get("base_url") or ""),
        timeout=timeout_seconds or 60,
        temperature=0.1,
        max_tokens=2000,
        streaming=False,
    )


class LangChainDeepSeekAdapter:
    """LangChain tool-calling adapter with the same contract as Direct."""

    name = "langchain"

    def __init__(
        self,
        *,
        config_loader: Callable[[], dict[str, Any]] | None = None,
        redactor: Callable[[object], str] | None = None,
        timeout_seconds: int | None = None,
        chat_model: Any = None,
    ) -> None:
        self._config_loader = config_loader or load_ai_config
        self._redactor = redactor or redact_text
        self._timeout_seconds = timeout_seconds
        self._chat = chat_model

    def _ensure_chat(self):
        if self._chat is None:
            self._chat = _build_chat_model(
                self._config_loader(),
                timeout_seconds=self._timeout_seconds,
            )
        return self._chat

    def plan_tools(self, request: AgentPlanRequest) -> AgentPlan:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            chat = self._ensure_chat()
            messages = [
                SystemMessage(content=_PLANNER_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"分析范围：{self._redactor(request.scope_label)}\n"
                        f"用户问题：{self._redactor(request.question)}"
                    )
                ),
            ]
            bound = chat.bind_tools(request.tools)
            response = bound.invoke(messages)
            tool_calls = _extract_tool_calls(response)
            return AgentPlan(
                tool_calls=tool_calls,
                assistant_message=_assistant_message(response, tool_calls),
            )
        except LangChainUnavailableError:
            raise
        except Exception as exc:
            raise LangChainAdapterError(
                f"LangChain 工具规划失败：{type(exc).__name__}"
            ) from exc

    def synthesize(self, request: SynthesisRequest) -> AgentAnswer:
        try:
            from langchain_core.messages import (
                AIMessage,
                HumanMessage,
                SystemMessage,
                ToolMessage,
            )

            chat = self._ensure_chat()
            messages: list[Any] = [
                SystemMessage(content=_SYNTHESIS_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"分析范围：{self._redactor(request.scope_label)}\n"
                        f"用户问题：{self._redactor(request.question)}"
                    )
                ),
            ]
            assistant_content = request.assistant_message.get("content")
            assistant_tool_calls = _as_ai_tool_calls(request.assistant_message)
            messages.append(
                AIMessage(
                    content=assistant_content or "",
                    tool_calls=assistant_tool_calls,
                )
            )
            for tool_message in request.tool_messages:
                messages.append(
                    ToolMessage(
                        content=str(tool_message.get("content") or ""),
                        tool_call_id=str(tool_message.get("tool_call_id") or ""),
                    )
                )

            response = chat.invoke(messages, response_format={"type": "json_object"})
            content = response.content if isinstance(response.content, str) else ""
            return _parse_answer(content, self._redactor)
        except LangChainUnavailableError:
            raise
        except Exception as exc:
            raise LangChainAdapterError(
                f"LangChain 回答合成失败：{type(exc).__name__}"
            ) from exc


_PLANNER_SYSTEM_PROMPT = (
    "你是 App 评论分析助手。根据用户问题选择最合适的只读分析工具，"
    "不要编造工具，不要执行任何写操作。"
)
_SYNTHESIS_SYSTEM_PROMPT = (
    "你是 App 评论分析助手。基于提供的工具结果撰写结构化回答。"
    '只输出 JSON 对象：{"answer": string, "limitations": string[], '
    '"evidence_call_ids": string[]}。answer 中的每个数字必须能在工具结果中找到。'
)


def _extract_tool_calls(response: Any) -> list[dict[str, Any]]:
    """Normalize LangChain AIMessage.tool_calls to the shared dict shape."""
    raw_tool_calls = getattr(response, "tool_calls", None) or []
    normalized: list[dict[str, Any]] = []
    for index, call in enumerate(raw_tool_calls, start=1):
        call_id = str(call.get("id") or f"call_{index}")
        name = str(call.get("name") or "")
        arguments = call.get("args") or call.get("arguments") or {}
        normalized.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        )
    return normalized


def _assistant_message(
    response: Any, tool_calls: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": getattr(response, "content", None),
        "tool_calls": tool_calls,
    }


def _as_ai_tool_calls(assistant_message: dict[str, Any]) -> list[dict[str, Any]]:
    """Rebuild LangChain tool_calls from the normalized OpenAI-style dicts."""
    raw_calls = assistant_message.get("tool_calls") or []
    tool_calls: list[dict[str, Any]] = []
    for call in raw_calls:
        function = call.get("function") or {}
        tool_calls.append(
            {
                "name": str(function.get("name") or ""),
                "args": _safe_parse_arguments(function.get("arguments")),
                "id": str(call.get("id") or ""),
            }
        )
    return tool_calls


def _safe_parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _parse_answer(content: str, _redactor: Callable[[object], str]) -> AgentAnswer:
    text = str(content or "").strip()
    if not text:
        raise LangChainAdapterError("LangChain 未返回可用回答。")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LangChainAdapterError("LangChain 合成回答不是有效 JSON。") from exc
    if not isinstance(parsed, dict):
        raise LangChainAdapterError("LangChain 合成回答必须是 JSON 对象。")
    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        raise LangChainAdapterError("LangChain 合成回答缺少 answer。")
    raw_limitations = parsed.get("limitations") or []
    if not isinstance(raw_limitations, list):
        raise LangChainAdapterError("LangChain limitations 必须是数组。")
    raw_evidence_ids = parsed.get("evidence_call_ids") or []
    if not isinstance(raw_evidence_ids, list):
        raise LangChainAdapterError("LangChain evidence_call_ids 必须是数组。")
    return AgentAnswer(
        answer=answer,
        limitations=[
            str(item).strip() for item in raw_limitations if str(item).strip()
        ],
        evidence_call_ids=[str(item) for item in raw_evidence_ids],
    )
