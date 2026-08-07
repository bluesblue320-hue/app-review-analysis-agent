"""HTTP service wrapper for controlled tool calling with rule fallback."""

from __future__ import annotations

from agent_workflow import dataframe_scope_signature
from backend.agent.tool_calling import ControlledToolCallingAgent
from backend.schemas.agent import AgentQueryRequest, AgentQueryResponse
from backend.services.dataset_service import InMemoryDatasetStore
from backend.services.insight_store import InMemoryInsightStore
from backend.services.repositories import (
    ANALYSIS_VERSION,
    compute_scope_signature,
)
from backend.services.scope_service import ReviewScopeService


class AgentService:
    def __init__(
        self,
        store: InMemoryDatasetStore,
        insight_store: InMemoryInsightStore,
        *,
        agent: ControlledToolCallingAgent | None = None,
    ) -> None:
        self._scope_service = ReviewScopeService(store)
        self._insight_store = insight_store
        self._agent = agent or ControlledToolCallingAgent()

    def query(self, request: AgentQueryRequest) -> AgentQueryResponse:
        full_dataset = request.scope == "full"
        dataset = self._scope_service._store.get(request.dataset_id)
        dataframe = self._scope_service.get_dataframe(
            request.dataset_id,
            request.filters,
            full_dataset=full_dataset,
        )
        scope_label = "完整上传数据" if full_dataset else "当前筛选结果"
        content_hash = dataset.content_hash or dataframe_scope_signature(
            dataset.dataframe
        )
        scope_signature = compute_scope_signature(
            content_hash,
            request.filters.model_dump(),
            analysis_version=ANALYSIS_VERSION,
        )
        matched_insights, insight_warning = self._insight_store.resolve(
            insight_id=request.insight_id,
            dataset_id=request.dataset_id,
            scope_signature=scope_signature,
            sample_size=len(dataframe),
        )
        result = self._agent.run(
            question=request.question,
            dataframe=dataframe,
            ai_insights=matched_insights,
            scope_label=scope_label,
        )
        from backend.core.audit_log import log_event

        adapter = getattr(self._agent, "_adapter", None)
        log_event(
            "agent_query",
            dataset_id=request.dataset_id,
            routing=result.routing,
            adapter=getattr(adapter, "name", "unknown"),
            tool_calls=len(result.tool_calls),
            sample_size=int(len(dataframe)),
            scope_signature=scope_signature,
        )
        return AgentQueryResponse(
            intent=result.intent,
            answer=result.answer,
            scope=request.scope,
            scope_label=scope_label,
            sample_size=int(len(dataframe)),
            scope_signature=scope_signature,
            tables=result.tables,
            routing=result.routing,
            tool_calls=[trace.model_dump() for trace in result.tool_calls],
            evidence=result.evidence,
            evidence_call_ids=result.evidence_call_ids,
            warnings=[
                *([insight_warning] if insight_warning else []),
                *result.warnings,
            ],
            limitations=result.limitations,
        )


# Kept as a compatibility alias for integrations importing the previous name.
RuleAgentService = AgentService
