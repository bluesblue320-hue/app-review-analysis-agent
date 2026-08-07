"""Deterministic performance benchmark for upload, summary, pagination and Agent.

Usage:
    python -m evaluation.benchmark --rows 10000 --runs 3
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backend.schemas.analytics import AnalyticsSummaryRequest, ReviewSearchRequest
from backend.services.analytics_service import AnalyticsService
from backend.services.dataset_service import InMemoryDatasetStore
from backend.services.insight_store import InMemoryInsightStore

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_FIXTURE = PACKAGE_DIR / "fixtures" / "synthetic_10000.csv"


def _timed(fn):
    started = time.perf_counter()
    result = fn()
    return result, round((time.perf_counter() - started) * 1000, 2)


def benchmark(
    rows: int,
    runs: int,
    fixture: str | Path,
) -> dict[str, Any]:
    dataframe = pd.read_csv(fixture)
    if len(dataframe) > rows:
        dataframe = dataframe.head(rows)

    store = InMemoryDatasetStore()
    insight_store = InMemoryInsightStore()
    service = AnalyticsService(store, insight_store)

    upload_times: list[float] = []
    summary_times: list[float] = []
    page_times: list[float] = []
    agent_rule_times: list[float] = []

    content = dataframe.to_csv(index=False).encode("utf-8")
    dataset_id = ""
    for _ in range(runs):
        record, elapsed = _timed(lambda: store.create("fixture.csv", content))
        upload_times.append(elapsed)
        dataset_id = record.dataset_id
        summary, summary_ms = _timed(
            lambda dataset_id=dataset_id: service.build_summary(
                AnalyticsSummaryRequest(dataset_id=dataset_id)
            )
        )
        summary_times.append(summary_ms)
        _, page_ms = _timed(
            lambda dataset_id=dataset_id: service.search_reviews(
                ReviewSearchRequest(
                    dataset_id=dataset_id, view="all", offset=0, limit=100
                )
            )
        )
        page_times.append(page_ms)
        _, agent_ms = _timed(
            lambda dataset_id=dataset_id: _rule_agent_query(store, dataset_id)
        )
        agent_rule_times.append(agent_ms)

    def percentile(values: list[float], p: float) -> float:
        ordered = sorted(values)
        index = min(len(ordered) - 1, int(len(ordered) * p))
        return ordered[index]

    report = {
        "fixture": str(fixture),
        "rows": len(dataframe),
        "runs": runs,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "results": {
            "upload_ms": {
                "p50": percentile(upload_times, 0.5),
                "p95": percentile(upload_times, 0.95),
                "max": max(upload_times),
            },
            "summary_ms": {
                "p50": percentile(summary_times, 0.5),
                "p95": percentile(summary_times, 0.95),
                "max": max(summary_times),
            },
            "pagination_100_ms": {
                "p50": percentile(page_times, 0.5),
                "p95": percentile(page_times, 0.95),
                "max": max(page_times),
            },
            "rule_agent_ms": {
                "p50": percentile(agent_rule_times, 0.5),
                "p95": percentile(agent_rule_times, 0.95),
                "max": max(agent_rule_times),
            },
        },
        "targets": {
            "upload_10000_rows_seconds": 30.0,
            "warm_summary_p95_seconds": 3.0,
            "pagination_100_p95_seconds": 1.0,
            "rule_agent_p95_seconds": 3.0,
        },
    }
    return report


def _rule_agent_query(store: InMemoryDatasetStore, dataset_id: str) -> Any:
    from backend.agent.tool_calling import ControlledToolCallingAgent

    record = store.get(dataset_id)
    return ControlledToolCallingAgent().run(
        question="当前共有多少条评论？",
        dataframe=record.dataframe,
        scope_label="完整上传数据",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="确定性性能基准")
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output-dir", default=str(PACKAGE_DIR / "reports" / "perf"))
    args = parser.parse_args()

    report = benchmark(args.rows, args.runs, args.fixture)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "benchmark.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report["results"], ensure_ascii=False, indent=2))
    print(f"报告：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
