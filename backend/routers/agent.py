"""Controlled Tool Calling Agent endpoint."""

from fastapi import APIRouter

from backend.schemas.agent import AgentQueryRequest, AgentQueryResponse
from backend.services.agent_service import AgentService
from backend.services.dataset_service import dataset_store
from backend.services.insight_store import insight_store

router = APIRouter(prefix="/agent", tags=["agent"])
agent_service = AgentService(dataset_store, insight_store)


@router.post("/query", response_model=AgentQueryResponse)
def query_agent(request: AgentQueryRequest) -> AgentQueryResponse:
    return agent_service.query(request)
