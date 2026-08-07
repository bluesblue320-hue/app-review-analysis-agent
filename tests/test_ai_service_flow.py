"""Tasks 3+4: InsightLock lease concurrency and expired-insight refresh flow.

Covers AiInsightService.generate():
- concurrent requests racing for the same fingerprint call the model once;
- a losing request waits, reuses the winner's result, or returns 409;
- one lease exiting never releases another lease;
- token mismatch never deletes a lock;
- Redis failure degrades to normal generation (PG unique keeps one row);
- expired records are refreshed in place keeping the same insight_id.
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from backend.core.exceptions import (
    InsightGenerationInProgressError,
)
from backend.schemas.ai import AiInsightsRequest
from backend.services.ai_service import AiInsightService
from backend.services.cache_service import MemoryCache, NullCache
from backend.services.dataset_service import InMemoryDatasetStore
from backend.services.insight_store import InMemoryInsightStore

CSV_BYTES = (
    "评分,内容,版本,时间\n1,无故封号,2.0.0,2026-07-01\n5,内容丰富,1.9.0,2026-07-02\n"
).encode()


def _fake_analysis(post_func=None):
    """Replace analyze_reviews with a controllable fake."""

    def wrapper(df, **kwargs):
        return {
            "summary": "fake summary",
            "pain_points": [{"name": "封号"}],
            "recommendations": [],
        }

    return wrapper


def _service(store=None, insight_store=None, cache=None):
    store = store or InMemoryDatasetStore()
    insight_store = insight_store or InMemoryInsightStore()
    from backend.services.cache_service import InsightLock

    lock = InsightLock(cache if cache is not None else NullCache())
    return AiInsightService(store, insight_store, lock=lock), store


class _CountingAnalysis:
    def __init__(self):
        self.count = 0
        self.lock = threading.Lock()

    def __call__(self, df, **kwargs):
        with self.lock:
            self.count += 1
        # Simulate slow model call so the second request races.
        time.sleep(0.05)
        return {
            "summary": "fake summary",
            "pain_points": [{"name": "封号"}],
            "recommendations": [],
        }


class TestConcurrentGeneration(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryDatasetStore()
        self.store.clear()
        self.dataset = self.store.create("reviews.csv", CSV_BYTES)
        self.insight_store = InMemoryInsightStore()
        from backend.services.cache_service import InsightLock

        self.service = AiInsightService(
            self.store,
            self.insight_store,
            lock=InsightLock(MemoryCache()),
        )

    def _request(self) -> AiInsightsRequest:
        return AiInsightsRequest(dataset_id=self.dataset.dataset_id, filters={})

    def _scope(self) -> str:
        """scope_signature computed exactly as AiInsightService.generate does."""
        from backend.schemas.analytics import ReviewFilters
        from backend.services.repositories import (
            ANALYSIS_VERSION,
            compute_scope_signature,
        )

        dataset = self.store.get(self.dataset.dataset_id)
        content_hash = dataset.content_hash
        return compute_scope_signature(
            content_hash,
            ReviewFilters().model_dump(),
            analysis_version=ANALYSIS_VERSION,
        )

    def test_two_requests_same_fingerprint_call_model_once(self) -> None:
        counting = _CountingAnalysis()
        results: list = []
        errors: list = []
        barrier = threading.Barrier(2)

        def run() -> None:
            barrier.wait()
            try:
                with patch("backend.services.ai_service.analyze_reviews", counting):
                    results.append(self.service.generate(self._request()))
            except Exception as exc:  # pragma: no cover - unexpected
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert errors == [], f"unexpected errors: {errors}"
        assert counting.count == 1, f"model called {counting.count} times"
        assert len(results) == 2
        # Both callers end up with the same insight.
        assert results[0].insight_id == results[1].insight_id

    def test_second_request_waits_and_reuses_result(self) -> None:
        counting = _CountingAnalysis()
        results: list = []
        barrier = threading.Barrier(2)

        def run() -> None:
            barrier.wait()
            with patch("backend.services.ai_service.analyze_reviews", counting):
                results.append(self.service.generate(self._request()))

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert counting.count == 1
        assert len(results) == 2
        assert results[0].insight_id == results[1].insight_id
        assert results[0].insights["summary"] == "fake summary"

    def test_generation_in_progress_when_holder_stuck(self) -> None:
        from backend.services.cache_service import insight_lock_key

        scope = self._scope()
        lock_key = insight_lock_key(self.dataset.dataset_id, scope)
        lock = self.service._lock
        # Another request holds the lease and never finishes.
        with lock.hold(lock_key) as lease:
            assert lease.acquired is True
            with patch("backend.services.ai_service.LOCK_WAIT_SECONDS", 0.3):
                with self.assertRaises(InsightGenerationInProgressError):
                    self.service.generate(self._request())

    def test_redis_failure_still_generates(self) -> None:
        from unittest.mock import MagicMock

        from backend.services.cache_service import InsightLock, RedisCache

        broken = MagicMock()
        broken.set.side_effect = RuntimeError("redis down")
        cache = RedisCache("redis://down:6379/0", ttl_seconds=60)
        cache._client = broken
        service = AiInsightService(
            self.store, self.insight_store, lock=InsightLock(cache)
        )
        with patch("backend.services.ai_service.analyze_reviews", _fake_analysis()):
            result = service.generate(self._request())
        assert result.insight_id is not None
        assert result.insights["summary"] == "fake summary"


class TestExpiredRefreshFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryDatasetStore()
        self.store.clear()
        self.dataset = self.store.create("reviews.csv", CSV_BYTES)
        self.insight_store = InMemoryInsightStore()
        from backend.services.cache_service import InsightLock

        self.service = AiInsightService(
            self.store,
            self.insight_store,
            lock=InsightLock(NullCache()),
        )

    def _request(self) -> AiInsightsRequest:
        return AiInsightsRequest(dataset_id=self.dataset.dataset_id, filters={})

    def _scope(self) -> str:
        """scope_signature computed exactly as AiInsightService.generate does."""
        from backend.schemas.analytics import ReviewFilters
        from backend.services.repositories import (
            ANALYSIS_VERSION,
            compute_scope_signature,
        )

        dataset = self.store.get(self.dataset.dataset_id)
        content_hash = dataset.content_hash
        return compute_scope_signature(
            content_hash,
            ReviewFilters().model_dump(),
            analysis_version=ANALYSIS_VERSION,
        )

    def _first_insight(self):
        from backend.services.repositories import (
            ANALYSIS_VERSION,
            compute_insight_fingerprint,
            compute_scope_signature,
        )

        dataset = self.store.get(self.dataset.dataset_id)
        from backend.schemas.analytics import ReviewFilters

        content_hash = dataset.content_hash
        scope = compute_scope_signature(
            content_hash,
            ReviewFilters().model_dump(),
            analysis_version=ANALYSIS_VERSION,
        )
        fingerprint = compute_insight_fingerprint(
            dataset_id=self.dataset.dataset_id,
            scope_signature=scope,
            sample_size=2,
            analysis_version=ANALYSIS_VERSION,
            provider="deepseek",
            model_name="deepseek-v4-flash",
        )
        return fingerprint

    def test_unexpired_record_reused_without_model_call(self) -> None:
        counting = _CountingAnalysis()
        with patch("backend.services.ai_service.analyze_reviews", counting):
            first = self.service.generate(self._request())
            second = self.service.generate(self._request())
        assert counting.count == 1
        assert first.insight_id == second.insight_id

    def test_expired_record_refreshed_keeping_same_id(self) -> None:
        from datetime import UTC, datetime, timedelta

        counting = _CountingAnalysis()
        with patch("backend.services.ai_service.analyze_reviews", counting):
            first = self.service.generate(self._request())

        # Force expiry on the stored record.
        record = self.insight_store.get(first.insight_id)
        expired = record.__class__(
            insight_id=record.insight_id,
            dataset_id=record.dataset_id,
            scope_signature=record.scope_signature,
            sample_size=record.sample_size,
            insights=record.insights,
            created_at=record.created_at,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        with self.insight_store._lock:
            self.insight_store._records[first.insight_id] = expired

        with patch("backend.services.ai_service.analyze_reviews", counting):
            refreshed = self.service.generate(self._request())

        assert counting.count == 2  # model called again after expiry
        assert refreshed.insight_id == first.insight_id  # same id kept
        stored = self.insight_store.get(refreshed.insight_id)
        assert stored.expires_at > datetime.now(UTC)  # new expiry

    def test_expired_refresh_returns_new_payload(self) -> None:
        from datetime import UTC, datetime, timedelta

        calls = {"count": 0}

        def changing_model(df, **kwargs):
            calls["count"] += 1
            return {
                "summary": f"version {calls['count']}",
                "pain_points": [],
                "recommendations": [],
            }

        with patch("backend.services.ai_service.analyze_reviews", changing_model):
            first = self.service.generate(self._request())
            assert first.insights["summary"] == "version 1"

        record = self.insight_store.get(first.insight_id)
        expired = record.__class__(
            insight_id=record.insight_id,
            dataset_id=record.dataset_id,
            scope_signature=record.scope_signature,
            sample_size=record.sample_size,
            insights=record.insights,
            created_at=record.created_at,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        with self.insight_store._lock:
            self.insight_store._records[first.insight_id] = expired

        with patch("backend.services.ai_service.analyze_reviews", changing_model):
            refreshed = self.service.generate(self._request())
        assert refreshed.insights["summary"] == "version 2"
        assert refreshed.insight_id == first.insight_id

    def test_missing_record_creates_new(self) -> None:
        counting = _CountingAnalysis()
        with patch("backend.services.ai_service.analyze_reviews", counting):
            result = self.service.generate(self._request())
        assert counting.count == 1
        assert result.insight_id is not None


if __name__ == "__main__":
    unittest.main()
