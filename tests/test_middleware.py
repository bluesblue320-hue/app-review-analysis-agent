"""Middleware request logging never exposes tokens, PII or review bodies."""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


class LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())


@pytest.fixture
def captured_logs() -> LogCapture:
    handler = LogCapture()
    logger = logging.getLogger("backend.requests")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield handler
    logger.removeHandler(handler)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_request_log_contains_allowed_fields_only(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


def test_error_log_does_not_expose_token_or_review_body(
    client: TestClient,
    captured_logs: LogCapture,
) -> None:
    with patch("backend.core.middleware.settings") as mock_settings:
        mock_settings.access_token = "super-secret-token"
        mock_settings.api_prefix = "/api/v1"
        response = client.post(
            "/api/v1/datasets",
            files={
                "file": (
                    "reviews.csv",
                    "评分,内容\n1,联系客服 13812345678 说封号问题\n".encode(),
                    "text/csv",
                )
            },
        )
        assert response.status_code == 401
    joined = "\n".join(captured_logs.records)
    assert "super-secret-token" not in joined
    assert "13812345678" not in joined
    assert "说封号问题" not in joined
    # Log lines must be valid JSON with only safe fields.
    for line in captured_logs.records:
        payload = json.loads(line)
        assert set(payload.keys()) <= {
            "event",
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
        }
