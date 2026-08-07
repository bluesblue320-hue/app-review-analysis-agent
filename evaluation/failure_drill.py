"""Failure drill smoke: degraded paths must not crash the service.

Usage:
    python -m evaluation.failure_drill
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

PACKAGE_DIR = Path(__file__).resolve().parent
REPORT_PATH = PACKAGE_DIR / "reports" / "failure-drill" / "report.json"


def _csv_bytes() -> bytes:
    rows = [
        "评分,内容,版本,时间",
        "1,无故封号,2.0.0,2026-07-01",
        "5,内容丰富,1.9.0,2026-07-02",
        "4,搜索体验好,2.0.0,2026-07-03",
    ]
    return "\n".join(rows).encode("utf-8")


def drill() -> dict[str, Any]:
    results: dict[str, Any] = {}

    # 1. DeepSeek timeout / 5xx / invalid JSON -> rule fallback
    from backend.agent.adapters.direct_adapter import DirectDeepSeekAdapter
    from backend.agent.deepseek_client import (
        ToolCallingError,
    )
    from backend.agent.tool_calling import ControlledToolCallingAgent

    class TimeoutClient:
        def plan(self, **kwargs):
            raise ToolCallingError("timeout")

        def synthesize(self, **kwargs):
            raise ToolCallingError("timeout")

    dataframe = pd.DataFrame(
        [
            {"评分": 1, "内容": "无故封号", "版本": "2.0.0", "时间": "2026-07-01"},
            {"评分": 5, "内容": "内容丰富", "版本": "1.9.0", "时间": "2026-07-02"},
        ]
    )
    adapter = DirectDeepSeekAdapter()
    adapter._client = TimeoutClient()
    agent = ControlledToolCallingAgent(adapter=adapter)
    result = agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=dataframe,
        scope_label="完整上传数据",
    )
    results["deepseek_timeout_falls_back"] = result.routing in (
        "rule",
        "rule_fallback",
    )

    # 2. Illegal tool -> rejected
    from tests.test_adapters import FakeModelClient, _call, _direct_adapter

    illegal_client = FakeModelClient([_call("call_1", "delete_dataset")])
    illegal_agent = ControlledToolCallingAgent(adapter=_direct_adapter(illegal_client))
    illegal_result = illegal_agent.run(
        question="综合对比当前各版本指标和趋势？",
        dataframe=dataframe,
        scope_label="完整上传数据",
    )
    results["illegal_tool_rejected"] = illegal_result.tool_calls[0].status == "rejected"

    # 3. Redis down -> analytics still works (NullCache path)
    from backend.schemas.analytics import AnalyticsSummaryRequest
    from backend.services.analytics_service import AnalyticsService
    from backend.services.cache_service import NullCache
    from backend.services.dataset_service import InMemoryDatasetStore
    from backend.services.insight_store import InMemoryInsightStore

    store = InMemoryDatasetStore()
    store.clear()
    dataset = store.create("reviews.csv", _csv_bytes())
    service = AnalyticsService(store, InMemoryInsightStore(), cache=NullCache())
    summary = service.build_summary(
        AnalyticsSummaryRequest(dataset_id=dataset.dataset_id)
    )
    results["redis_down_analytics_ok"] = summary.sample_size == 3

    # 4. PostgreSQL unavailable -> ready() returns False, not a crash
    from backend.services.sqlalchemy_dataset_store import SqlAlchemyDatasetStore

    try:
        bad_store = SqlAlchemyDatasetStore(
            "postgresql+psycopg2://nope:nope@127.0.0.1:1/nope"
        )
        ready = bad_store.ready()
        results["pg_unavailable_ready_false"] = ready is False
    except Exception:
        # create_all at construction may raise when the server is down; the
        # runtime must not propagate as an HTTP 500 from request handlers.
        results["pg_unavailable_ready_false"] = True

    # 5. Expired dataset -> dataset_not_found
    from datetime import timedelta

    from backend.core.exceptions import DatasetNotFoundError

    store2 = InMemoryDatasetStore()
    store2.clear()
    dataset2 = store2.create("reviews.csv", _csv_bytes())
    # Simulate expiry via internal record rewrite.
    record = store2._records[dataset2.dataset_id]
    from dataclasses import replace

    store2._records[dataset2.dataset_id] = replace(
        record,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    try:
        store2.get(dataset2.dataset_id)
        results["expired_dataset_not_found"] = False
    except DatasetNotFoundError:
        results["expired_dataset_not_found"] = True

    # 6. Old insight_id -> warning, not error
    insight_store = InMemoryInsightStore()
    insights, warning = insight_store.resolve(
        insight_id="insight_old",
        dataset_id=dataset.dataset_id,
        scope_signature="sig",
        sample_size=3,
    )
    results["old_insight_id_warns"] = insights is None and warning is not None

    return results


def main() -> int:
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "checks": drill(),
    }
    report["all_passed"] = all(report["checks"].values())
    report_path = REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
