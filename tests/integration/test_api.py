from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.main import app
from backend.services.dataset_service import dataset_store


@pytest.fixture
def client():
    dataset_store.clear()
    with TestClient(app) as test_client:
        yield test_client
    dataset_store.clear()


def _csv_bytes(rows: list[dict[str, object]]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


def _upload(client: TestClient, rows: list[dict[str, object]]) -> dict[str, object]:
    response = client.post(
        "/api/v1/datasets",
        files={"file": ("reviews.csv", _csv_bytes(rows), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _sample_rows() -> list[dict[str, object]]:
    return [
        {
            "评分": 1,
            "内容": "无故封号，人工客服不回复",
            "版本": "2.0.0",
            "时间": "2026-07-01",
        },
        {
            "评分": 3,
            "内容": "广告太多，推荐质量下降",
            "版本": "2.0.0",
            "时间": "2026-07-02",
        },
        {
            "评分": 5,
            "内容": "内容丰富，搜索体验很好",
            "版本": "1.9.0",
            "时间": "2026-07-03",
        },
    ]


def test_health_check(client: TestClient):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "app-review-analysis-agent",
    }


def test_csv_upload_converts_ratings_and_removes_invalid_rows(client: TestClient):
    rows = [
        {"评分": "1", "内容": "无故封号", "版本": "2.0.0"},
        {"评分": "5", "内容": "内容丰富", "版本": "1.9.0"},
        {"评分": "not-a-rating", "内容": "评分无效", "版本": "2.0.0"},
        {"评分": "3", "内容": "   ", "版本": "2.0.0"},
    ]

    result = _upload(client, rows)

    assert result["dataset_id"].startswith("dataset_")
    assert result["original_rows"] == 4
    assert result["valid_rows"] == 2
    assert result["columns"] == ["评分", "内容", "版本"]
    assert result["created_at"].endswith("Z")


def test_upload_rejects_missing_required_column(client: TestClient):
    response = client.post(
        "/api/v1/datasets",
        files={
            "file": (
                "reviews.csv",
                _csv_bytes([{"内容": "只有内容"}]),
                "text/csv",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_dataset"
    assert "评分" in response.json()["error"]["message"]


def test_upload_rejects_non_csv_file(client: TestClient):
    response = client.post(
        "/api/v1/datasets",
        files={"file": ("reviews.txt", b"rating,content\n1,bad", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json() == {
        "error": {
            "code": "unsupported_file_type",
            "message": "仅支持 CSV 文件。",
        }
    }


def test_summary_returns_deterministic_analysis_and_json_records(client: TestClient):
    dataset = _upload(client, _sample_rows())

    response = client.post(
        "/api/v1/analytics/summary",
        json={"dataset_id": dataset["dataset_id"], "filters": {}},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["sample_size"] == 3
    assert result["average_rating"] == 3.0
    assert result["negative_ratio"] == 66.67
    assert sum(item["review_count"] for item in result["rating_distribution"]) == 3
    assert result["high_risk_count"] >= 1
    assert result["negative_keywords"]
    assert result["positive_keywords"]
    assert result["issue_priorities"]
    assert result["trend"]
    assert result["reviews"]
    assert "账号类" in result["available_categories"]
    assert len(result["scope_signature"]) == 64
    assert "NaN" not in response.text


def test_summary_reapplies_filters_on_server(client: TestClient):
    dataset = _upload(client, _sample_rows())
    dataset_id = dataset["dataset_id"]

    rating_response = client.post(
        "/api/v1/analytics/summary",
        json={
            "dataset_id": dataset_id,
            "filters": {"rating_min": 5, "rating_max": 5, "categories": []},
        },
    )
    keyword_response = client.post(
        "/api/v1/analytics/summary",
        json={
            "dataset_id": dataset_id,
            "filters": {"keyword": "封号"},
        },
    )

    assert rating_response.status_code == 200
    assert rating_response.json()["sample_size"] == 1
    assert rating_response.json()["average_rating"] == 5.0
    assert rating_response.json()["negative_ratio"] == 0.0
    assert keyword_response.status_code == 200
    assert keyword_response.json()["sample_size"] == 1
    assert "封号" in keyword_response.json()["high_risk_reviews"][0]["content"]


def test_summary_rejects_frontend_supplied_sample_size(client: TestClient):
    dataset = _upload(client, _sample_rows())

    response = client.post(
        "/api/v1/analytics/summary",
        json={
            "dataset_id": dataset["dataset_id"],
            "sample_size": 999999,
            "filters": {},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_summary_handles_unknown_dataset_with_uniform_error(client: TestClient):
    response = client.post(
        "/api/v1/analytics/summary",
        json={"dataset_id": "dataset_missing", "filters": {}},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "dataset_not_found"


def test_summary_validates_filter_ranges(client: TestClient):
    dataset = _upload(client, _sample_rows())

    response = client.post(
        "/api/v1/analytics/summary",
        json={
            "dataset_id": dataset["dataset_id"],
            "filters": {"rating_min": 5, "rating_max": 1},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_ai_config_does_not_expose_api_key(client: TestClient):
    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-secret"}):
        response = client.get("/api/v1/ai/config")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "api_key" not in response.json()
    assert "sk-secret" not in response.text


def test_ai_insights_use_server_dataset_scope(client: TestClient):
    dataset = _upload(client, _sample_rows())
    fake_insights = {
        "summary": "测试洞察",
        "pain_points": [],
        "delighters": [],
        "sentiment_drivers": [],
        "high_risk_reviews": [],
        "recommendations": [],
        "report_copy": "",
    }

    with patch("backend.services.ai_service.analyze_reviews", return_value=fake_insights):
        response = client.post(
            "/api/v1/ai/insights",
            json={
                "dataset_id": dataset["dataset_id"],
                "filters": {"keyword": "封号"},
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["sample_size"] == 1
    assert response.json()["insights"]["summary"] == "测试洞察"
    assert len(response.json()["scope_signature"]) == 64


def test_simple_agent_query_uses_whitelisted_rule_tool(client: TestClient):
    dataset = _upload(client, _sample_rows())

    response = client.post(
        "/api/v1/agent/query",
        json={
            "dataset_id": dataset["dataset_id"],
            "question": "哪个版本问题最多？",
            "filters": {},
            "scope": "full",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["intent"] == "version_analysis"
    assert result["scope"] == "full"
    assert result["sample_size"] == 3
    assert result["tables"]["版本分析"]
    assert result["routing"] == "rule"
    assert result["tool_calls"][0]["name"] == "compare_versions"
    assert result["tool_calls"][0]["status"] == "success"
    assert result["evidence"]
