import type { AIConfigResponse, AIInsightResponse, Filters } from "../types/api";
import { apiRequest } from "./client";

export function getAIConfig() {
  return apiRequest<AIConfigResponse>("/ai/config");
}

export function generateAIInsight(datasetId: string, filters: Filters) {
  return apiRequest<AIInsightResponse>("/ai/insights", {
    method: "POST",
    body: { dataset_id: datasetId, filters },
  });
}
