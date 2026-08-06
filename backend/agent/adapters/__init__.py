"""Agent model adapter contract shared by Direct and LangChain adapters.

An adapter is responsible only for model interaction: planning tool calls and
synthesizing a structured answer. It never runs business analysis — every
analysis tool is executed by the shared ``ToolExecutor`` under the
orchestrator's control.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class AgentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    scope_label: str = Field(min_length=1, max_length=200)
    tools: list[dict[str, object]] = Field(default_factory=list)


class AgentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    # Raw assistant message (content + tool_calls) preserved for synthesis.
    assistant_message: dict[str, Any] = Field(default_factory=dict)


class SynthesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    scope_label: str = Field(min_length=1, max_length=200)
    assistant_message: dict[str, Any] = Field(default_factory=dict)
    tool_messages: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, object]] = Field(default_factory=list)


class AgentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    evidence_call_ids: list[str] = Field(default_factory=list)


@runtime_checkable
class AgentModelAdapter(Protocol):
    """Minimal model-facing contract for the shared orchestrator."""

    name: str

    def plan_tools(self, request: AgentPlanRequest) -> AgentPlan:
        """Ask the model which whitelisted tools to call for the question."""
        ...

    def synthesize(self, request: SynthesisRequest) -> AgentAnswer:
        """Ask the model to write a structured, evidence-grounded answer."""
        ...


def build_adapter(
    adapter_name: str,
    *,
    post_func: Any = None,
    config_loader: Any = None,
    redactor: Any = None,
    timeout_seconds: int | None = None,
    chat_model: Any = None,
) -> AgentModelAdapter:
    """Factory for the configured agent adapter.

    ``adapter_name`` must be ``direct`` or ``langchain``. The optional
    injection hooks are used by tests and by the evaluation framework.
    """
    from backend.agent.adapters.direct_adapter import DirectDeepSeekAdapter
    from backend.agent.adapters.langchain_adapter import LangChainDeepSeekAdapter

    if adapter_name == "direct":
        return DirectDeepSeekAdapter(
            post_func=post_func,
            config_loader=config_loader,
            redactor=redactor,
            timeout_seconds=timeout_seconds,
        )
    if adapter_name == "langchain":
        return LangChainDeepSeekAdapter(
            config_loader=config_loader,
            redactor=redactor,
            timeout_seconds=timeout_seconds,
            chat_model=chat_model,
        )
    raise ValueError(f"未知的 Agent Adapter：{adapter_name}")
