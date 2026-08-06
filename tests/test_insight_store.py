from __future__ import annotations

import pytest

from backend.services.insight_store import (
    INSIGHT_NOT_FOUND_WARNING,
    INSIGHT_SCOPE_MISMATCH_WARNING,
    InMemoryInsightStore,
    InsightNotFoundError,
)


def test_insight_store_uses_random_ids_and_deep_copies_records() -> None:
    store = InMemoryInsightStore()
    source = {"pain_points": [{"name": "账号问题"}]}

    first = store.create(
        dataset_id="dataset_a",
        scope_signature="scope_a",
        sample_size=3,
        insights=source,
    )
    second = store.create(
        dataset_id="dataset_a",
        scope_signature="scope_a",
        sample_size=3,
        insights=source,
    )
    source["pain_points"][0]["name"] = "客户端修改"
    first.insights["pain_points"][0]["name"] = "返回值修改"

    stored = store.get(first.insight_id)
    assert first.insight_id.startswith("insight_")
    assert first.insight_id != second.insight_id
    assert stored.insights["pain_points"][0]["name"] == "账号问题"

    stored.insights["pain_points"][0]["name"] = "读取副本修改"
    assert store.get(first.insight_id).insights["pain_points"][0]["name"] == "账号问题"


def test_insight_store_resolves_only_matching_server_scope() -> None:
    store = InMemoryInsightStore()
    record = store.create(
        dataset_id="dataset_a",
        scope_signature="scope_a",
        sample_size=3,
        insights={"summary": "可信洞察"},
    )

    insights, warning = store.resolve(
        insight_id=record.insight_id,
        dataset_id="dataset_a",
        scope_signature="scope_a",
        sample_size=3,
    )
    assert insights == {"summary": "可信洞察"}
    assert warning is None

    for dataset_id, scope_signature, sample_size in (
        ("dataset_b", "scope_a", 3),
        ("dataset_a", "scope_b", 3),
        ("dataset_a", "scope_a", 2),
    ):
        insights, warning = store.resolve(
            insight_id=record.insight_id,
            dataset_id=dataset_id,
            scope_signature=scope_signature,
            sample_size=sample_size,
        )
        assert insights is None
        assert warning == INSIGHT_SCOPE_MISMATCH_WARNING


def test_insight_store_clear_removes_records_without_breaking_resolution() -> None:
    store = InMemoryInsightStore()
    record = store.create(
        dataset_id="dataset_a",
        scope_signature="scope_a",
        sample_size=1,
        insights={},
    )

    store.clear()

    with pytest.raises(InsightNotFoundError):
        store.get(record.insight_id)
    insights, warning = store.resolve(
        insight_id=record.insight_id,
        dataset_id="dataset_a",
        scope_signature="scope_a",
        sample_size=1,
    )
    assert insights is None
    assert warning == INSIGHT_NOT_FOUND_WARNING
