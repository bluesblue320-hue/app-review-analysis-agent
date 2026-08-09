import type { AnalyticsSummary, Filters } from "../types/api";
import { apiRequest } from "./client";

export function getAnalyticsSummary(datasetId: string, filters: Filters, insightId?: string) {
  return apiRequest<AnalyticsSummary>("/analytics/summary", {
    method: "POST",
    body: { dataset_id: datasetId, filters, ...(insightId ? { insight_id: insightId } : {}) },
  });
}
