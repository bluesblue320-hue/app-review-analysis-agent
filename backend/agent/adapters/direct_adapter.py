"""Direct DeepSeek HTTP adapter implementing the shared AgentModelAdapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ai_analysis import load_ai_config
from backend.agent.adapters import (
    AgentAnswer,
    AgentPlan,
    AgentPlanRequest,
    SynthesisRequest,
)
from backend.agent.deepseek_client import DeepSeekToolClient
from backend.core.privacy import redact_text


class DirectDeepSeekAdapter:
    """Native DeepSeek tool-calling adapter.

    This is a thin wrapper over the existing ``DeepSeekToolClient``. The
    model-facing behaviour (plan + synthesize) is unchanged; the shared
    orchestrator keeps ownership of evidence validation, guardrails and
    rule fallback.
    """

    name = "direct"

    def __init__(
        self,
        *,
        post_func: Callable[..., Any] | None = None,
        config_loader: Callable[[], dict[str, Any]] | None = None,
        redactor: Callable[[object], str] | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self._client = DeepSeekToolClient(
            post_func=post_func or _default_post,
            config_loader=config_loader or load_ai_config,
            timeout_seconds=timeout_seconds,
            redactor=redactor or redact_text,
        )

    def plan_tools(self, request: AgentPlanRequest) -> AgentPlan:
        message = self._client.plan(
            question=request.question,
            scope_label=request.scope_label,
            tools=request.tools,
        )
        return AgentPlan(
            tool_calls=list(message.get("tool_calls") or []),
            assistant_message=message,
        )

    def synthesize(self, request: SynthesisRequest) -> AgentAnswer:
        result = self._client.synthesize(
            question=request.question,
            scope_label=request.scope_label,
            assistant_message=request.assistant_message,
            tool_messages=request.tool_messages,
            tools=request.tools,
        )
        if isinstance(result, str):
            return AgentAnswer(answer=result.strip())
        return AgentAnswer(
            answer=str(result.get("answer") or "").strip(),
            limitations=list(result.get("limitations") or []),
            evidence_call_ids=list(result.get("evidence_call_ids") or []),
        )


def _default_post(*args: Any, **kwargs: Any) -> Any:
    import requests

    return requests.post(*args, **kwargs)
