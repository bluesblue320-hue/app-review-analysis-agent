"""Tests for the cache service including Redis and Null variants."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from backend.services.cache_service import (
    NullCache,
    RedisCache,
    summary_cache_key,
)


class TestNullCache:
    def test_get_returns_none(self) -> None:
        assert NullCache().get("any") is None

    def test_set_and_invalidate_are_noops(self) -> None:
        cache = NullCache()
        cache.set("k", {"a": 1})
        cache.invalidate_dataset("d1")
        assert cache.ready() is True


class TestSummaryCacheKey:
    def test_key_is_deterministic_and_scoped(self) -> None:
        key_a = summary_cache_key("d1", {"b": 2, "a": 1})
        key_b = summary_cache_key("d1", {"a": 1, "b": 2})
        key_c = summary_cache_key("d2", {"a": 1, "b": 2})
        assert key_a == key_b
        assert key_a != key_c
        assert key_a.startswith("summary:d1:")


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

    def test_set_uses_ttl_and_json(self) -> None:
        client = MagicMock()
        cache = self._cache(client)
        cache.set("summary:d1:h", {"answer": "ok"})
        client.setex.assert_called_once()
        args = client.setex.call_args
        assert args[0][1] == 60
        assert json.loads(args[0][2]) == {"answer": "ok"}

    def test_set_exception_is_swallowed(self) -> None:
        client = MagicMock()
        client.setex.side_effect = RuntimeError("down")
        cache = self._cache(client)
        cache.set("summary:d1:h", {})  # must not raise

    def test_invalidate_dataset_scans_and_deletes(self) -> None:
        client = MagicMock()
        client.scan_iter.return_value = ["summary:d1:a", "summary:d1:b"]
        cache = self._cache(client)
        cache.invalidate_dataset("d1")
        client.scan_iter.assert_called_once_with(match="summary:d1:*", count=100)
        client.delete.assert_called_once_with("summary:d1:a", "summary:d1:b")

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


class TestCacheServiceSelection:
    def test_service_uses_null_cache_when_no_redis(self) -> None:
        from backend.services.cache_service import cache_service

        assert isinstance(cache_service, NullCache)
