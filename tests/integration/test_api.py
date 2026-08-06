from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.dataset_service import dataset_store
from backend.services.insight_store import insight_store


@pytest.fixture
def client():
    dataset_store.clear()
    insight_store.clear()
    with TestClient(app) as test_client:
        yield test_client
    dataset_store.clear()
    insight_store.clear()


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
    assert result["removed_rows"] == 2
    assert result["invalid_rating_rows"] == 1
    assert result["invalid_reasons"] == {"invalid_rating": 1, "empty_content": 1}
    assert result["columns"] == ["评分", "内容", "版本"]
    assert result["created_at"].endswith("Z")


def test_upload_excludes_out_of_range_ratings_and_full_agent_uses_valid_rows(
    client: TestClient,
):
    rows = [
        {"评分": 0, "内容": "零星非法评论"},
        {"评分": 6, "内容": "六星非法评论"},
        {"评分": 1, "内容": "一星边界评论"},
        {"评分": 5, "内容": "五星边界评论"},
        {"评分": "not-a-rating", "内容": "无法转换的评分"},
        {"评分": 3, "内容": "   "},
    ]
    dataset = _upload(client, rows)
    summary_response = client.post(
        "/api/v1/analytics/summary",
        json={"dataset_id": dataset["dataset_id"], "filters": {}},
    )
    agent_response = client.post(
        "/api/v1/agent/query",
        json={
            "dataset_id": dataset["dataset_id"],
            "question": "平均评分是多少？",
            "filters": {},
            "scope": "full",
        },
    )

    assert dataset["original_rows"] == 6
    assert dataset["valid_rows"] == 2
    assert dataset["removed_rows"] == 4
    assert dataset["invalid_rating_rows"] == 3
    assert dataset["invalid_reasons"] == {"invalid_rating": 3, "empty_content": 1}
    assert summary_response.status_code == 200, summary_response.text
    summary = summary_response.json()
    assert summary["sample_size"] == dataset["valid_rows"]
    assert {
        item["rating"]
        for item in summary["rating_distribution"]
        if item["review_count"] > 0
    } == {1, 5}
    assert agent_response.status_code == 200, agent_response.text
    assert agent_response.json()["sample_size"] == dataset["valid_rows"]


def _fake_insights(name: str, suggestion: str) -> dict[str, object]:
    return {
        "summary": "测试洞察",
        "pain_points": [
            {
                "name": name,
                "severity": "high",
                "suggestion": suggestion,
            }
        ],
        "delighters": [],
        "sentiment_drivers": [],
        "high_risk_reviews": [],
        "recommendations": [suggestion],
        "report_copy": "测试汇报文案",
    }


def _generate_insight(
    client: TestClient,
    dataset_id: str,
    insights: dict[str, object],
    filters: dict[str, object] | None = None,
) -> dict[str, object]:
    with patch("backend.services.ai_service.analyze_reviews", return_value=insights):
        response = client.post(
            "/api/v1/ai/insights",
            json={"dataset_id": dataset_id, "filters": filters or {}},
        )
    assert response.status_code == 200, response.text
    return response.json()


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


def test_summary_finds_rating_sentiment_mismatch_after_review_preview_limit(
    client: TestClient,
):
    mismatch_content = "第 101 条异常评论"
    rows = [{"评分": 5, "内容": f"普通评论 {index}"} for index in range(1, 101)]
    rows.append({"评分": 5, "内容": mismatch_content})

    def fake_sentiment(content: object) -> float:
        return 10.0 if content == mismatch_content else 80.0

    with patch(
        "review_preprocessing.calculate_sentiment",
        new=fake_sentiment,
    ):
        dataset = _upload(client, rows)

    response = client.post(
        "/api/v1/analytics/summary",
        json={"dataset_id": dataset["dataset_id"], "filters": {}},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["sample_size"] == 101
    assert len(result["reviews"]) == 100
    assert all(review["content"] != mismatch_content for review in result["reviews"])
    assert result["rating_sentiment_mismatch_count"] == 1
    assert len(result["rating_sentiment_mismatches"]) == 1
    mismatch = result["rating_sentiment_mismatches"][0]
    assert mismatch["content"] == mismatch_content
    assert mismatch["rating"] == 5
    assert mismatch["sentiment"] == 10.0
    assert set(mismatch) == {"rating", "sentiment", "category", "risk_label", "content"}


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


def test_ai_config_does_not_expose_api_key(client: TestClient, caplog, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret")
    response = client.get("/api/v1/ai/config")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "api_key" not in response.json()
    assert "sk-secret" not in response.text
    assert "sk-secret" not in caplog.text


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

    with patch(
        "backend.services.ai_service.analyze_reviews", return_value=fake_insights
    ):
        response = client.post(
            "/api/v1/ai/insights",
            json={
                "dataset_id": dataset["dataset_id"],
                "filters": {"keyword": "封号"},
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["insight_id"].startswith("insight_")
    assert response.json()["sample_size"] == 1
    assert response.json()["insights"]["summary"] == "测试洞察"
    assert len(response.json()["scope_signature"]) == 64


def test_summary_reuses_server_stored_insight_with_matching_id(client: TestClient):
    dataset = _upload(client, _sample_rows())
    suggestion = "建立可信的账号申诉进度入口。"
    generated = _generate_insight(
        client,
        str(dataset["dataset_id"]),
        _fake_insights("账号封禁问题", suggestion),
    )

    response = client.post(
        "/api/v1/analytics/summary",
        json={
            "dataset_id": dataset["dataset_id"],
            "filters": {},
            "insight_id": generated["insight_id"],
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["warnings"] == []
    assert suggestion in {
        item["ai_recommendation"] for item in result["issue_priorities"]
    }


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/analytics/summary",
            {"filters": {}, "ai_insights": {"summary": "客户端伪造"}},
        ),
        (
            "/api/v1/analytics/summary",
            {"filters": {}, "ai_scope_signature": "forged-signature"},
        ),
        (
            "/api/v1/agent/query",
            {
                "question": "差评主要集中在哪些问题？",
                "filters": {},
                "scope": "full",
                "ai_insights": {"summary": "客户端伪造"},
                "ai_scope_signature": "forged-signature",
            },
        ),
    ],
)
def test_analysis_requests_reject_client_supplied_ai_insights(
    client: TestClient,
    path: str,
    payload: dict[str, object],
):
    dataset = _upload(client, _sample_rows())

    response = client.post(
        path,
        json={"dataset_id": dataset["dataset_id"], **payload},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_insight_id_warns_and_keeps_deterministic_summary(
    client: TestClient,
):
    dataset = _upload(client, _sample_rows())

    response = client.post(
        "/api/v1/analytics/summary",
        json={
            "dataset_id": dataset["dataset_id"],
            "filters": {},
            "insight_id": "insight_missing",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert any("不存在" in warning for warning in result["warnings"])
    assert all(not item["ai_recommendation"] for item in result["issue_priorities"])


def test_missing_insight_id_warns_and_keeps_agent_available(client: TestClient):
    dataset = _upload(client, _sample_rows())

    response = client.post(
        "/api/v1/agent/query",
        json={
            "dataset_id": dataset["dataset_id"],
            "question": "差评主要集中在哪些问题？",
            "filters": {},
            "scope": "full",
            "insight_id": "insight_missing",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["answer"]
    assert any("不存在" in warning for warning in result["warnings"])


def test_insight_from_dataset_a_is_not_used_for_dataset_b(client: TestClient):
    dataset_a = _upload(client, _sample_rows())
    dataset_b = _upload(client, _sample_rows())
    suggestion = "跨数据集伪复用不应出现。"
    generated = _generate_insight(
        client,
        str(dataset_a["dataset_id"]),
        _fake_insights("账号问题", suggestion),
    )

    response = client.post(
        "/api/v1/analytics/summary",
        json={
            "dataset_id": dataset_b["dataset_id"],
            "filters": {},
            "insight_id": generated["insight_id"],
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert any("数据范围" in warning for warning in result["warnings"])
    assert suggestion not in {
        item["ai_recommendation"] for item in result["issue_priorities"]
    }


def test_full_dataset_insight_is_not_used_for_filtered_summary(client: TestClient):
    dataset = _upload(client, _sample_rows())
    suggestion = "完整范围洞察不应进入筛选范围。"
    generated = _generate_insight(
        client,
        str(dataset["dataset_id"]),
        _fake_insights("账号封号问题", suggestion),
    )

    response = client.post(
        "/api/v1/analytics/summary",
        json={
            "dataset_id": dataset["dataset_id"],
            "filters": {"keyword": "封号"},
            "insight_id": generated["insight_id"],
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert any("数据范围" in warning for warning in result["warnings"])
    assert suggestion not in {
        item["ai_recommendation"] for item in result["issue_priorities"]
    }


def test_changed_filter_does_not_reuse_previous_filtered_insight(client: TestClient):
    dataset = _upload(client, _sample_rows())
    suggestion = "旧筛选洞察不应参与新优先级。"
    generated = _generate_insight(
        client,
        str(dataset["dataset_id"]),
        _fake_insights("广告体验问题", suggestion),
        {"keyword": "封号"},
    )

    response = client.post(
        "/api/v1/analytics/summary",
        json={
            "dataset_id": dataset["dataset_id"],
            "filters": {"keyword": "广告"},
            "insight_id": generated["insight_id"],
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert any("数据范围" in warning for warning in result["warnings"])
    assert suggestion not in {
        item["ai_recommendation"] for item in result["issue_priorities"]
    }


def test_agent_reuses_insight_only_by_matching_server_insight_id(client: TestClient):
    dataset = _upload(client, _sample_rows())
    suggestion = "Agent 仅使用服务端保存的账号建议。"
    generated = _generate_insight(
        client,
        str(dataset["dataset_id"]),
        _fake_insights("账号封号问题", suggestion),
    )

    response = client.post(
        "/api/v1/agent/query",
        json={
            "dataset_id": dataset["dataset_id"],
            "question": "差评主要集中在哪些问题？",
            "filters": {},
            "scope": "full",
            "insight_id": generated["insight_id"],
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["warnings"] == []
    assert suggestion in {item["AI建议"] for item in result["tables"]["问题优先级"]}


def test_ai_insight_response_and_logs_do_not_expose_api_key(
    client: TestClient,
    caplog,
    monkeypatch,
):
    dataset = _upload(client, _sample_rows())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret-insight")

    with patch(
        "backend.services.ai_service.analyze_reviews",
        return_value=_fake_insights("账号问题", "安全建议"),
    ):
        response = client.post(
            "/api/v1/ai/insights",
            json={"dataset_id": dataset["dataset_id"], "filters": {}},
        )

    assert response.status_code == 200, response.text
    assert "sk-secret-insight" not in response.text
    assert "sk-secret-insight" not in caplog.text


def test_ai_insight_response_recursively_removes_nan(client: TestClient):
    dataset = _upload(client, _sample_rows())
    fake_insights = _fake_insights("账号问题", "安全建议")
    fake_insights["pain_points"][0]["severity"] = float("nan")

    with patch(
        "backend.services.ai_service.analyze_reviews",
        return_value=fake_insights,
    ):
        response = client.post(
            "/api/v1/ai/insights",
            json={"dataset_id": dataset["dataset_id"], "filters": {}},
        )

    assert response.status_code == 200, response.text
    assert response.json()["insights"]["pain_points"][0]["severity"] is None
    assert "NaN" not in response.text


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
    assert result["evidence_call_ids"] == ["rule_1"]


def test_agent_response_includes_evidence_call_ids_for_rule_fallback(
    client: TestClient,
):
    dataset = _upload(client, _sample_rows())
    response = client.post(
        "/api/v1/agent/query",
        json={
            "dataset_id": dataset["dataset_id"],
            "question": "闪退一定是服务器接口导致的吗？",
            "filters": {},
            "scope": "full",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["routing"] == "rule"
    assert result["limitations"], "unanswerable question must carry limitations"
    assert result["evidence_call_ids"] == ["rule_1"]


def test_dataset_delete_removes_dataset_and_returns_deleted(client: TestClient):
    dataset = _upload(client, _sample_rows())
    response = client.delete(f"/api/v1/datasets/{dataset['dataset_id']}")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "dataset_id": dataset["dataset_id"],
        "deleted": True,
    }
    # The deleted dataset is no longer visible.
    missing = client.post(
        "/api/v1/analytics/summary",
        json={"dataset_id": dataset["dataset_id"], "filters": {}},
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"]["code"] == "dataset_not_found"


def test_dataset_delete_unknown_id_returns_not_found(client: TestClient):
    response = client.delete("/api/v1/datasets/dataset_missing")
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "dataset_not_found"


def test_missing_bearer_token_returns_401(client: TestClient):
    with patch("backend.core.middleware.settings") as mock_settings:
        mock_settings.access_token = "secret-token"
        mock_settings.api_prefix = "/api/v1"
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        protected = client.post(
            "/api/v1/analytics/summary",
            json={"dataset_id": "dataset_x", "filters": {}},
        )
        assert protected.status_code == 401, protected.text
        assert protected.json()["error"]["code"] == "unauthorized"
        assert protected.headers.get("X-Request-ID")


def test_wrong_bearer_token_returns_401(client: TestClient):
    with patch("backend.core.middleware.settings") as mock_settings:
        mock_settings.access_token = "secret-token"
        mock_settings.api_prefix = "/api/v1"
        response = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer wrong-token"},
        )
        # /health is public: it must not require a token
        assert response.status_code == 200
        protected = client.post(
            "/api/v1/analytics/summary",
            json={"dataset_id": "dataset_x", "filters": {}},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert protected.status_code == 401, protected.text


def test_correct_bearer_token_is_accepted(client: TestClient):
    with patch("backend.core.middleware.settings") as mock_settings:
        mock_settings.access_token = "secret-token"
        mock_settings.api_prefix = "/api/v1"
        response = client.post(
            "/api/v1/analytics/summary",
            json={"dataset_id": "dataset_missing", "filters": {}},
            headers={"Authorization": "Bearer secret-token"},
        )
        # token accepted: request proceeds to business logic (dataset not found)
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "dataset_not_found"
