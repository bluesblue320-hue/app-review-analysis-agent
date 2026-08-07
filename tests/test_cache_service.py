"""Tests for the cache service: Null, Memory and Redis variants + short lock."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

from backend.services.cache_service import (
    InsightLock,
    MemoryCache,
    NullCache,
    RedisCache,
    analytics_cache_key,
    dataset_keys_key,
    insight_lock_key,
    summary_cache_key,
)


class TestNullCache:
    def test_get_returns_none(self) -> None:
        assert NullCache().get("any") is None

    def test_set_and_delete_are_noops(self) -> None:
        cache = NullCache()
        cache.set("k", {"a": 1}, ttl_seconds=60)
        cache.delete("k")
        cache.invalidate_dataset("d1")
        assert cache.ready() is True


class TestMemoryCache:
    def test_roundtrip(self) -> None:
        cache = MemoryCache()
        cache.set("k", {"a": 1}, ttl_seconds=60)
        assert cache.get("k") == {"a": 1}

    def test_expired_entry_returns_none(self) -> None:
        cache = MemoryCache()
        cache.set("k", {"a": 1}, ttl_seconds=0)
        assert cache.get("k") is None

    def test_delete(self) -> None:
        cache = MemoryCache()
        cache.set("k", {"a": 1}, ttl_seconds=60)
        cache.delete("k")
        assert cache.get("k") is None

    def test_invalidate_dataset_removes_only_that_dataset(self) -> None:
        cache = MemoryCache()
        cache.set(
            analytics_cache_key(
                dataset_id="d1", scope_signature="s", analysis_type="summary"
            ),
            {"payload": {}},
            ttl_seconds=60,
        )
        cache.set(
            analytics_cache_key(
                dataset_id="d2", scope_signature="s", analysis_type="summary"
            ),
            {"payload": {}},
            ttl_seconds=60,
        )
        cache.invalidate_dataset("d1")
        assert (
            cache.get(
                analytics_cache_key(
                    dataset_id="d1", scope_signature="s", analysis_type="summary"
                )
            )
            is None
        )
        assert cache.get(
            analytics_cache_key(
                dataset_id="d2", scope_signature="s", analysis_type="summary"
            )
        ) == {"payload": {}}


class TestSummaryCacheKey:
    def test_key_is_deterministic_and_scoped(self) -> None:
        key_a = summary_cache_key("d1", {"b": 2, "a": 1})
        key_b = summary_cache_key("d1", {"a": 1, "b": 2})
        key_c = summary_cache_key("d2", {"a": 1, "b": 2})
        assert key_a == key_b
        assert key_a != key_c
        assert key_a.startswith("summary:d1:")


class TestCacheKeys:
    def test_analytics_key_includes_scope_and_insight(self) -> None:
        key = analytics_cache_key(
            dataset_id="d1",
            scope_signature="sig",
            analysis_type="summary",
            insight_id="insight_1",
        )
        assert key.startswith("ara:")
        assert "d1" in key and "sig" in key and "insight_1" in key

    def test_lock_and_dataset_keys_scoped(self) -> None:
        assert insight_lock_key("d1", "sig").startswith("ara:")
        assert dataset_keys_key("d1").endswith("dataset-keys:d1")


class TestRedisCache:
    def _cache(self, client: MagicMock) -> RedisCache:
        with patch("redis.Redis.from_url", return_value=client):
            return RedisCache("redis://localhost:6379/0", ttl_seconds=60)

    def test_get_hit_parses_json(self) -> None:
        client = MagicMock()
        client.get.return_value = json.dumps({"answer": "ok"})
        cache = self._cache(client)
        assert cache.get("summary:d1:h") == {"answer": "ok"}
        client.get.assert_called_once_with("summary:d1:h")

    def test_get_miss_returns_none(self) -> None:
        client = MagicMock()
        client.get.return_value = None
        cache = self._cache(client)
        assert cache.get("summary:d1:h") is None

    def test_get_exception_returns_none(self) -> None:
        client = MagicMock()
        client.get.side_effect = RuntimeError("down")
        cache = self._cache(client)
        assert cache.get("summary:d1:h") is None

    def test_get_non_dict_returns_none(self) -> None:
        client = MagicMock()
        client.get.return_value = "[1, 2]"
        cache = self._cache(client)
        assert cache.get("summary:d1:h") is None

    def test_set_uses_ttl_and_json(self) -> None:
        client = MagicMock()
        cache = self._cache(client)
        cache.set("summary:d1:h", {"answer": "ok"}, ttl_seconds=60)
        client.setex.assert_called_once()
        args = client.setex.call_args
        assert args[0][1] == 60
        assert json.loads(args[0][2]) == {"answer": "ok"}

    def test_set_exception_is_swallowed(self) -> None:
        client = MagicMock()
        client.setex.side_effect = RuntimeError("down")
        cache = self._cache(client)
        cache.set("summary:d1:h", {}, ttl_seconds=60)  # must not raise

    def test_delete(self) -> None:
        client = MagicMock()
        cache = self._cache(client)
        cache.delete("k")
        client.delete.assert_called_once_with("k")

    def test_delete_exception_is_swallowed(self) -> None:
        client = MagicMock()
        client.delete.side_effect = RuntimeError("down")
        cache = self._cache(client)
        cache.delete("k")

    def test_invalidate_dataset_scans_and_deletes(self) -> None:
        client = MagicMock()
        client.scan_iter.side_effect = [
            ["ara:dev:v1:analytics:d1:a", "ara:dev:v1:analytics:d1:b"],
            [],
        ]
        cache = self._cache(client)
        cache.invalidate_dataset("d1")
        assert client.scan_iter.call_count == 2
        client.delete.assert_called_once_with(
            "ara:dev:v1:analytics:d1:a", "ara:dev:v1:analytics:d1:b"
        )

    def test_invalidate_dataset_no_keys(self) -> None:
        client = MagicMock()
        client.scan_iter.return_value = []
        cache = self._cache(client)
        cache.invalidate_dataset("d1")
        client.delete.assert_not_called()

    def test_invalidate_dataset_exception_is_swallowed(self) -> None:
        client = MagicMock()
        client.scan_iter.side_effect = RuntimeError("down")
        cache = self._cache(client)
        cache.invalidate_dataset("d1")

    def test_ready_returns_ping_result(self) -> None:
        client = MagicMock()
        client.ping.return_value = True
        cache = self._cache(client)
        assert cache.ready() is True

    def test_ready_false_on_exception(self) -> None:
        client = MagicMock()
        client.ping.side_effect = RuntimeError("down")
        cache = self._cache(client)
        assert cache.ready() is False


class TestInsightLock:
    def test_memory_lock_excludes_second_caller(self) -> None:
        cache = MemoryCache()
        lock = InsightLock(cache)
        key = "ara:dev:v1:lock:insight:d1:sig"
        assert lock.acquire(key) is True
        assert lock.acquire(key) is False  # still held
        lock.release(key)
        assert lock.acquire(key) is True  # released

    def test_memory_lock_token_safe_release(self) -> None:
        cache = MemoryCache()
        lock = InsightLock(cache)
        key = "ara:dev:v1:lock:insight:d1:sig"
        assert lock.acquire(key) is True
        # A second lock instance must not release the first holder's lock.
        other = InsightLock(cache)
        other.acquire(key)
        other.release(key)
        # First holder's token still in effect.
        assert lock.acquire(key) is False

    def test_memory_lock_ttl_expiry_recovers(self) -> None:
        cache = MemoryCache()
        lock = InsightLock(cache, lock_ttl_seconds=1)
        key = "ara:dev:v1:lock:insight:d1:sig"
        assert lock.acquire(key) is True
        time.sleep(1.1)
        assert lock.acquire(key) is True  # expired -> recoverable

    def test_null_cache_lock_always_succeeds(self) -> None:
        lock = InsightLock(NullCache())
        assert lock.acquire("k") is True
        lock.release("k")

    def test_redis_lock_acquire_and_release(self) -> None:
        client = MagicMock()
        client.set.return_value = True
        with patch("redis.Redis.from_url", return_value=client):
            cache = RedisCache("redis://localhost:6379/0", ttl_seconds=60)
        lock = InsightLock(cache)
        key = "ara:dev:v1:lock:insight:d1:sig"
        assert lock.acquire(key) is True
        client.set.assert_called_once()
        args = client.set.call_args
        assert args[1]["nx"] is True
        assert args[1]["ex"] == 30

    def test_redis_lock_not_acquired_when_held(self) -> None:
        client = MagicMock()
        client.set.return_value = None
        with patch("redis.Redis.from_url", return_value=client):
            cache = RedisCache("redis://localhost:6379/0", ttl_seconds=60)
        lock = InsightLock(cache)
        assert lock.acquire("k") is False

    def test_redis_lock_acquire_failure_proceeds(self) -> None:
        client = MagicMock()
        client.set.side_effect = RuntimeError("down")
        with patch("redis.Redis.from_url", return_value=client):
            cache = RedisCache("redis://localhost:6379/0", ttl_seconds=60)
        lock = InsightLock(cache)
        # Redis failure degrades to "proceed"; PostgreSQL ensures uniqueness.
        assert lock.acquire("k") is True

    def test_context_manager_releases_all(self) -> None:
        cache = MemoryCache()
        lock = InsightLock(cache)
        key = "ara:dev:v1:lock:insight:d1:sig"
        with lock:
            assert lock.acquire(key) is True
        assert lock.acquire(key) is True  # released on exit


class TestCacheServiceSelection:
    def test_service_uses_null_cache_when_no_redis(self) -> None:
        from backend.services.cache_service import cache_service

        assert isinstance(cache_service, NullCache)
