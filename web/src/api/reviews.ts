import type { Filters, ReviewSearchResponse, ReviewView } from "../types/api";
import { apiRequest } from "./client";

export function searchReviews(
  datasetId: string,
  filters: Filters,
  view: ReviewView,
  offset: number,
  limit: number,
) {
  return apiRequest<ReviewSearchResponse>("/analytics/reviews/search", {
    method: "POST",
    body: { dataset_id: datasetId, filters, view, offset, limit },
  });
}
