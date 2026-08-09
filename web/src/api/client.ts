import { APIError, type APIErrorPayload } from "../types/api";

// The API prefix has exactly one source of truth. Vite and Nginx proxy /api.
export const API_PREFIX = "/api/v1";
const DEFAULT_TIMEOUT_MS = 60_000;

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | object;
  timeoutMs?: number;
};

function requestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function isJsonBody(body: RequestOptions["body"]): body is object {
  return Boolean(body) && !(body instanceof FormData) && typeof body === "object";
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", requestId());

  let body = options.body as BodyInit | undefined;
  if (isJsonBody(options.body)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  try {
    const response = await fetch(`${API_PREFIX}${path}`, {
      ...options,
      headers,
      body,
      signal: controller.signal,
    });
    const responseRequestId = response.headers.get("X-Request-ID") ?? "";
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new APIError(
        response.ok ? "后端返回了无法解析的响应。" : `请求失败（HTTP ${response.status}）。`,
        response.status,
        "invalid_response",
        responseRequestId,
      );
    }
    if (!response.ok) {
      const errorPayload = payload as Partial<APIErrorPayload>;
      throw new APIError(
        errorPayload.error?.message ?? `请求失败（HTTP ${response.status}）。`,
        response.status,
        errorPayload.error?.code ?? "api_error",
        errorPayload.request_id ?? responseRequestId,
      );
    }
    return payload as T;
  } catch (error) {
    if (error instanceof APIError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new APIError("请求超时，请稍后重试。", 0, "request_timeout", "");
    }
    throw new APIError("无法连接分析服务，请检查网络或稍后重试。", 0, "network_error", "");
  } finally {
    globalThis.clearTimeout(timeout);
  }
}
