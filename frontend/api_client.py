"""Single HTTP client used by the Streamlit frontend."""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 60.0


class ApiClientError(Exception):
    """Base exception safe to show in the Streamlit UI."""


class BackendUnavailableError(ApiClientError):
    """Raised when no connection to the backend can be established."""


class ApiTimeoutError(ApiClientError):
    """Raised when a backend request exceeds the configured timeout."""


class InvalidApiResponseError(ApiClientError):
    """Raised when a successful backend response is not a JSON object."""


class ApiResponseError(ApiClientError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class BackendApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BACKEND_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/v1/health")

    def upload_dataset(
        self,
        filename: str,
        content: bytes,
        content_type: str = "text/csv",
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/v1/datasets",
            files={"file": (filename, content, content_type)},
        )

    def get_summary(
        self,
        dataset_id: str,
        filters: dict[str, Any],
        *,
        insight_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "dataset_id": dataset_id,
            "filters": filters,
        }
        if insight_id is not None:
            payload["insight_id"] = insight_id
        return self._request_json(
            "POST",
            "/api/v1/analytics/summary",
            json=payload,
        )

    def get_ai_config(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/v1/ai/config")

    def generate_ai_insights(
        self,
        dataset_id: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/v1/ai/insights",
            json={"dataset_id": dataset_id, "filters": filters},
        )

    def query_agent(
        self,
        *,
        dataset_id: str,
        question: str,
        filters: dict[str, Any],
        scope: str,
        insight_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "dataset_id": dataset_id,
            "question": question,
            "filters": filters,
            "scope": scope,
        }
        if insight_id is not None:
            payload["insight_id"] = insight_id
        return self._request_json(
            "POST",
            "/api/v1/agent/query",
            json=payload,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                timeout=self.timeout,
                **kwargs,
            )
        except requests.Timeout as exc:
            raise ApiTimeoutError(
                f"后端请求超时（{self.timeout:g} 秒），请稍后重试。"
            ) from exc
        except requests.ConnectionError as exc:
            raise BackendUnavailableError(
                f"无法连接后端服务：{self.base_url}。请确认 FastAPI 已启动。"
            ) from exc
        except requests.RequestException as exc:
            raise BackendUnavailableError(f"后端请求失败：{exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            if 200 <= response.status_code < 300:
                raise InvalidApiResponseError("后端返回了无法解析的 JSON。") from exc
            raise ApiResponseError(
                response.status_code,
                "invalid_error_response",
                f"后端返回 HTTP {response.status_code}，但错误内容不是有效 JSON。",
            ) from exc

        if not isinstance(payload, dict):
            raise InvalidApiResponseError("后端 JSON 响应必须是对象。")
        if not 200 <= response.status_code < 300:
            error = payload.get("error")
            error = error if isinstance(error, dict) else {}
            code = str(error.get("code") or "api_error")
            message = str(
                error.get("message")
                or f"后端请求失败，HTTP 状态码 {response.status_code}。"
            )
            raise ApiResponseError(response.status_code, code, message)
        return payload


def build_api_client() -> BackendApiClient:
    base_url = os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL).strip()
    raw_timeout = os.getenv("BACKEND_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        timeout = float(raw_timeout)
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    if timeout <= 0:
        timeout = DEFAULT_TIMEOUT_SECONDS
    return BackendApiClient(base_url=base_url or DEFAULT_BACKEND_URL, timeout=timeout)
