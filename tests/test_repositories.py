"""Stage 3: Repository Protocols, scope signatures and SQLAlchemy persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from backend.services.insight_store import (
    INSIGHT_NOT_FOUND_WARNING,
    INSIGHT_SCOPE_MISMATCH_WARNING,
    InMemoryInsightStore,
)
from backend.services.repositories import (
    canonical_filters,
    compute_content_hash,
    compute_insight_fingerprint,
    compute_scope_signature,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"评分": 1, "内容": "无故封号", "版本": "2.0.0", "时间": "2026-07-01"},
            {"评分": 5, "内容": "内容丰富", "版本": "1.9.0", "时间": "2026-07-02"},
            {"评分": 4, "内容": "搜索体验好", "版本": "2.0.0", "时间": "2026-07-03"},
        ]
    )


class TestCanonicalFilters:
    def test_empty_filters_fixed_representation(self) -> None:
        assert canonical_filters(None) == "none"
        assert canonical_filters({}) == "none"

    def test_categories_deduplicated_and_sorted(self) -> None:
        signature_a = canonical_filters({"categories": ["功能", "性能"]})
        signature_b = canonical_filters({"categories": ["性能", "功能", "功能"]})
        assert signature_a == signature_b

    def test_empty_list_uses_fixed_representation(self) -> None:
        assert canonical_filters({"categories": []}) == canonical_filters(
            {"categories": [""]}
        )

    def test_keyword_stripped(self) -> None:
        assert canonical_filters({"keyword": " 封号 "}) == canonical_filters(
            {"keyword": "封号"}
        )

    def test_float_fixed_format(self) -> None:
        assert canonical_filters({"rating_min": 1.0}) == canonical_filters(
            {"rating_min": 1}
        )

    def test_json_sorted_keys_stable_separators(self) -> None:
        assert canonical_filters({"b": 2, "a": 1}) == canonical_filters(
            {"a": 1, "b": 2}
        )


class TestScopeSignature:
    def test_stable_for_same_content_and_filters(self) -> None:
        content_hash = compute_content_hash(_frame(), ("评分", "内容", "版本", "时间"))
        filters = {"categories": ["功能"], "keyword": "封号"}
        sig_a = compute_scope_signature(content_hash, filters)
        sig_b = compute_scope_signature(content_hash, filters)
        assert sig_a == sig_b

    def test_changes_when_filters_change(self) -> None:
        content_hash = compute_content_hash(_frame(), ("评分", "内容", "版本", "时间"))
        assert compute_scope_signature(
            content_hash, {"categories": ["功能"]}
        ) != compute_scope_signature(content_hash, {"categories": ["性能"]})

    def test_changes_when_analysis_version_changes(self) -> None:
        content_hash = compute_content_hash(_frame(), ("评分", "内容", "版本", "时间"))
        assert compute_scope_signature(
            content_hash, None, "v1"
        ) != compute_scope_signature(content_hash, None, "v2")

    def test_changes_when_content_changes(self) -> None:
        hash_a = compute_content_hash(_frame(), ("评分", "内容", "版本", "时间"))
        other = _frame().copy()
        other.loc[0, "内容"] = "完全不同"
        hash_b = compute_content_hash(other, ("评分", "内容", "版本", "时间"))
        assert hash_a != hash_b

    def test_does_not_include_insight_id(self) -> None:
        content_hash = compute_content_hash(_frame(), ("评分", "内容", "版本", "时间"))
        sig = compute_scope_signature(content_hash, None)
        assert "insight" not in sig


class TestInsightFingerprint:
    def test_stable_for_same_fields(self) -> None:
        fingerprint_a = compute_insight_fingerprint(
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
        )
        fingerprint_b = compute_insight_fingerprint(
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
        )
        assert fingerprint_a == fingerprint_b

    def test_changes_with_sample_size(self) -> None:
        assert compute_insight_fingerprint(
            dataset_id="d1", scope_signature="sig", sample_size=3
        ) != compute_insight_fingerprint(
            dataset_id="d1", scope_signature="sig", sample_size=4
        )

    def test_changes_with_dataset_id(self) -> None:
        assert compute_insight_fingerprint(
            dataset_id="d1", scope_signature="sig", sample_size=3
        ) != compute_insight_fingerprint(
            dataset_id="d2", scope_signature="sig", sample_size=3
        )

    def test_fixed_field_order_is_sha256_hex(self) -> None:
        fingerprint = compute_insight_fingerprint(
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
            analysis_version="v1",
            provider="deepseek",
            model_name="deepseek-v4-flash",
        )
        assert len(fingerprint) == 64
        assert all(character in "0123456789abcdef" for character in fingerprint)


class TestInMemoryRepositoryDedup:
    def test_same_fingerprint_returns_existing_record(self) -> None:
        store = InMemoryInsightStore()
        first = store.create(
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
            insights={"summary": "A"},
        )
        second = store.create(
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
            insights={"summary": "B"},
        )
        assert first.insight_id == second.insight_id
        assert store.get(first.insight_id).insights == {"summary": "A"}

    def test_find_by_fingerprint_hits_unexpired(self) -> None:
        store = InMemoryInsightStore()
        record = store.create(
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
            insights={"summary": "A"},
        )
        fingerprint = compute_insight_fingerprint(
            dataset_id="d1", scope_signature="sig", sample_size=3
        )
        found = store.find_by_fingerprint(fingerprint)
        assert found is not None
        assert found.insight_id == record.insight_id

    def test_find_by_fingerprint_miss(self) -> None:
        store = InMemoryInsightStore()
        fingerprint = compute_insight_fingerprint(
            dataset_id="nope", scope_signature="sig", sample_size=3
        )
        assert store.find_by_fingerprint(fingerprint) is None

    def test_refresh_expired_keeps_same_id(self) -> None:
        store = InMemoryInsightStore()
        original = store.create(
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
            insights={"summary": "旧"},
        )
        fingerprint = compute_insight_fingerprint(
            dataset_id="d1", scope_signature="sig", sample_size=3
        )
        from backend.services.insight_store import InsightRecord

        store._records[original.insight_id] = InsightRecord(
            insight_id=original.insight_id,
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
            insights={"summary": "旧"},
            created_at=datetime.now(UTC) - timedelta(days=40),
            expires_at=datetime.now(UTC) - timedelta(days=10),
        )
        refreshed = store.refresh_expired(
            fingerprint=fingerprint,
            insights={"summary": "新"},
        )
        assert refreshed.insight_id == original.insight_id
        assert refreshed.insights == {"summary": "新"}
        # Still only one record for the fingerprint.
        assert store.find_by_fingerprint(fingerprint).insight_id == original.insight_id

    def test_expired_fingerprint_not_found(self) -> None:
        store = InMemoryInsightStore()
        store.create(
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
            insights={"summary": "A"},
        )
        fingerprint = compute_insight_fingerprint(
            dataset_id="d1", scope_signature="sig", sample_size=3
        )
        # Expire all records.
        for key in list(store._records):
            record = store._records[key]
            from backend.services.insight_store import InsightRecord

            store._records[key] = InsightRecord(
                insight_id=record.insight_id,
                dataset_id=record.dataset_id,
                scope_signature=record.scope_signature,
                sample_size=record.sample_size,
                insights=record.insights,
                created_at=record.created_at,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        assert store.find_by_fingerprint(fingerprint) is None

    def test_resolve_warns_on_scope_mismatch(self) -> None:
        store = InMemoryInsightStore()
        record = store.create(
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
            insights={"summary": "A"},
        )
        insights, warning = store.resolve(
            insight_id=record.insight_id,
            dataset_id="d1",
            scope_signature="other",
            sample_size=3,
        )
        assert insights is None
        assert warning == INSIGHT_SCOPE_MISMATCH_WARNING

    def test_resolve_warns_on_missing(self) -> None:
        store = InMemoryInsightStore()
        insights, warning = store.resolve(
            insight_id="missing",
            dataset_id="d1",
            scope_signature="sig",
            sample_size=3,
        )
        assert insights is None
        assert warning == INSIGHT_NOT_FOUND_WARNING
