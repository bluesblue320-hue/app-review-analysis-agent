"""Stage 4: Redis analytics cache + insight short lock integration tests.

Uses MemoryCache to simulate Redis semantics deterministically, plus mocked
redis-py clients for the failure paths (Redis down / timeout must never
surface as HTTP 500).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.services.analytics_service import AnalyticsService
from backend.services.cache_service import (
    InsightLock,
    MemoryCache,
    RedisCache,
    analytics_cache_key,
)
from backend.services.dataset_service import InMemoryDatasetStore
from backend.services.insight_store import InMemoryInsightStore


def _csv_bytes() -> bytes:
    rows = [
        "评分,内容,版本,时间",
        "1,无故封号,2.0.0,2026-07-01",
        "5,内容丰富,1.9.0,2026-07-02",
        "4,搜索体验好,2.0.0,2026-07-03",
    ]
    return "\n".join(rows).encode("utf-8")


@pytest.fixture()
def store():
    dataset_store = InMemoryDatasetStore()
    dataset_store.clear()
    yield dataset_store
    dataset_store.clear()


@pytest.fixture()
def insight_store():
    store = InMemoryInsightStore()
    store.clear()
    yield store
    store.clear()


def _summary_service(store, insight_store, cache):
    return AnalyticsService(store, insight_store, cache=cache)


class TestHotCacheConsistency:
    def test_cold_then_hot_cache_return_identical_results(
        self, store, insight_store
    ) -> None:
        dataset = store.create("reviews.csv", _csv_bytes())
        cache = MemoryCache()
        service = _summary_service(store, insight_store, cache)
        from backend.schemas.analytics import AnalyticsSummaryRequest

        request = AnalyticsSummaryRequest(dataset_id=dataset.dataset_id)
        first = service.build_summary(request)
        # Second call should hit the cache.
        second = service.build_summary(request)
        assert second.model_dump(mode="json") == first.model_dump(mode="json")
        assert (
            cache.get(
                analytics_cache_key(
                    dataset_id=dataset.dataset_id,
                    scope_signature=first.scope_signature,
                    analysis_type="summary",
                    insight_id=None,
                )
            )
            is not None
        )

    def test_schema_version_change_invalidates_old_entries(
        self, store, insight_store
    ) -> None:
        dataset = store.create("reviews.csv", _csv_bytes())
        cache = MemoryCache()
        service = _summary_service(store, insight_store, cache)
        from backend.schemas.analytics import AnalyticsSummaryRequest

        request = AnalyticsSummaryRequest(dataset_id=dataset.dataset_id)
        first = service.build_summary(request)
        # Simulate an old-format entry (no schema_version).
        cache.set(
            analytics_cache_key(
                dataset_id=dataset.dataset_id,
                scope_signature=first.scope_signature,
                analysis_type="summary",
            ),
            {"payload": {"sample_size": -1}},
            ttl_seconds=60,
        )
        second = service.build_summary(request)
        assert second.sample_size == 3  # recomputed, not the stale -1

    def test_different_filters_do_not_share_cache(self, store, insight_store) -> None:
        dataset = store.create("reviews.csv", _csv_bytes())
        cache = MemoryCache()
        service = _summary_service(store, insight_store, cache)
        from backend.schemas.analytics import AnalyticsSummaryRequest

        unfiltered = AnalyticsSummaryRequest(dataset_id=dataset.dataset_id)
        filtered = AnalyticsSummaryRequest(
            dataset_id=dataset.dataset_id,
            filters={"rating_min": 4, "rating_max": 5},
        )
        first = service.build_summary(unfiltered)
        second = service.build_summary(filtered)
        assert first.scope_signature != second.scope_signature

    def test_dataset_keys_index_and_best_effort_invalidation(
        self, store, insight_store
    ) -> None:
        dataset = store.create("reviews.csv", _csv_bytes())
        cache = MemoryCache()
        service = _summary_service(store, insight_store, cache)
        from backend.schemas.analytics import AnalyticsSummaryRequest

        request = AnalyticsSummaryRequest(dataset_id=dataset.dataset_id)
        service.build_summary(request)
        cache.invalidate_dataset(dataset.dataset_id)
        # Rebuild must not return stale cache.
        again = service.build_summary(request)
        assert again.sample_size == 3


class TestRedisFailureDegradation:
    def test_redis_down_analytics_still_works(self, store, insight_store) -> None:
        dataset = store.create("reviews.csv", _csv_bytes())
        broken_client = MagicMock()
        broken_client.get.side_effect = RuntimeError("connection refused")
        broken_client.setex.side_effect = RuntimeError("connection refused")
        with patch("redis.Redis.from_url", return_value=broken_client):
            cache = RedisCache("redis://down:6379/0", ttl_seconds=60)
        service = _summary_service(store, insight_store, cache)
        from backend.schemas.analytics import AnalyticsSummaryRequest

        request = AnalyticsSummaryRequest(dataset_id=dataset.dataset_id)
        result = service.build_summary(request)
        assert result.sample_size == 3  # no 500 despite Redis being down


class TestInsightShortLockSingleModelCall:
    def test_locked_path_skips_second_model_call(self, store, insight_store) -> None:
        store.create("reviews.csv", _csv_bytes())
        cache = MemoryCache()
        lock = InsightLock(cache)
        key = "ara:dev:v1:lock:insight:d1:sig"

        with lock.hold(key) as first:
            assert first.acquired is True
            # While the lease is held, a second caller is excluded.
            with lock.hold(key) as second:
                assert second.acquired is False
        with lock.hold(key) as after:
            assert after.acquired is True  # released

    def test_lock_released_after_context(self) -> None:
        cache = MemoryCache()
        lock = InsightLock(cache)
        key = "ara:dev:v1:lock:insight:d1:sig"
        with lock.hold(key) as lease:
            assert lease.acquired is True
        with lock.hold(key) as after:
            assert after.acquired is True  # released on exit


class TestCacheSerialization:
    def test_cache_values_strictly_json_serializable(self) -> None:
        cache = MemoryCache()
        cache.set("k", {"nested": {"list": [1, 2, 3]}, "flag": True}, ttl_seconds=60)
        encoded = json.dumps(cache.get("k"), ensure_ascii=False)
        assert isinstance(encoded, str)


class TestRedisInvalidationUsesScanNotKeys:
    def test_invalidate_dataset_uses_scan_iter_not_keys(self) -> None:
        """Per-dataset invalidation must rely on SCAN, never blocking KEYS."""
        client = MagicMock()
        client.scan_iter.return_value = iter(
            ["ara:dev:v1:analytics:d1:aaa:summary:none"]
        )
        with patch("redis.Redis.from_url", return_value=client):
            cache = RedisCache("redis://localhost:6379/0", ttl_seconds=60)
        cache.invalidate_dataset("d1")
        # scan_iter used; blocking keys() must not be called.
        client.scan_iter.assert_called()
        client.keys.assert_not_called()
        client.delete.assert_called_once()

    def test_invalidate_dataset_with_no_matches_is_safe(self) -> None:
        client = MagicMock()
        client.scan_iter.return_value = iter([])
        with patch("redis.Redis.from_url", return_value=client):
            cache = RedisCache("redis://localhost:6379/0", ttl_seconds=60)
        cache.invalidate_dataset("d1")  # no error, no delete call
        client.delete.assert_not_called()

    def test_invalidate_dataset_degrades_on_scan_error(self) -> None:
        client = MagicMock()
        client.scan_iter.side_effect = RuntimeError("redis down")
        with patch("redis.Redis.from_url", return_value=client):
            cache = RedisCache("redis://localhost:6379/0", ttl_seconds=60)
        cache.invalidate_dataset("d1")  # must not raise
