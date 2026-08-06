"""HTTP service wrapper for controlled tool calling with rule fallback."""

from __future__ import annotations

from agent_workflow import dataframe_scope_signature
from backend.agent.tool_calling import ControlledToolCallingAgent
from backend.schemas.agent import AgentQueryRequest, AgentQueryResponse
from backend.services.dataset_service import InMemoryDatasetStore
from backend.services.insight_store import InMemoryInsightStore
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
        dataframe = self._scope_service.get_dataframe(
            request.dataset_id,
            request.filters,
            full_dataset=full_dataset,
        )
        scope_label = "完整上传数据" if full_dataset else "当前筛选结果"
        scope_signature = dataframe_scope_signature(dataframe)
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
            warnings=[
                *([insight_warning] if insight_warning else []),
                *result.warnings,
            ],
            limitations=result.limitations,
        )


# Kept as a compatibility alias for integrations importing the previous name.
RuleAgentService = AgentService
