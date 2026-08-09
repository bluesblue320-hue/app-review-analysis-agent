import { APIError } from "../types/api";

export function formatNumber(value: number, digits = 1): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits }).format(value);
}

export function errorMessage(error: unknown): string {
  if (error instanceof APIError) {
    return `${error.message}${error.requestId ? `（请求 ID：${error.requestId}）` : ""}`;
  }
  return error instanceof Error ? error.message : "发生未知错误。";
}

export function cellText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
