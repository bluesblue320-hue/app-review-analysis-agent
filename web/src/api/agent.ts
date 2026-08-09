import type { AgentQueryRequest, AgentQueryResponse } from "../types/api";
import { apiRequest } from "./client";

export function queryAgent(request: AgentQueryRequest) {
  return apiRequest<AgentQueryResponse>("/agent/query", { method: "POST", body: { ...request } });
}
