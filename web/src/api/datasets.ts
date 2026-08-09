import type { DatasetUploadResponse } from "../types/api";
import { apiRequest } from "./client";

export function uploadDataset(file: File): Promise<DatasetUploadResponse> {
  const body = new FormData();
  body.append("file", file);
  return apiRequest<DatasetUploadResponse>("/datasets", { method: "POST", body });
}

export function deleteDataset(datasetId: string): Promise<{ dataset_id: string; deleted: boolean }> {
  return apiRequest(`/datasets/${encodeURIComponent(datasetId)}`, { method: "DELETE" });
}
