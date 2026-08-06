"""Optional Redis cache with a no-op fallback."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from backend.core.config import settings


logger = logging.getLogger(__name__)


class NullCache:
    def get(self, _key: str) -> dict[str, Any] | None:
        return None

    def set(self, _key: str, _value: dict[str, Any]) -> None:
        return None

    def invalidate_dataset(self, _dataset_id: str) -> None:
        return None

    def ready(self) -> bool:
        return True


class RedisCache:
    def __init__(self, url: str, ttl_seconds: int) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._ttl_seconds = ttl_seconds

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            value = self._client.get(key)
            return json.loads(value) if value else None
        except Exception as exc:
            logger.warning("Redis cache read failed: error_type=%s", type(exc).__name__)
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        try:
            self._client.setex(key, self._ttl_seconds, json.dumps(value, ensure_ascii=False))
        except Exception as exc:
            logger.warning("Redis cache write failed: error_type=%s", type(exc).__name__)

    def invalidate_dataset(self, dataset_id: str) -> None:
        try:
            keys = list(self._client.scan_iter(match=f"summary:{dataset_id}:*", count=100))
            if keys:
                self._client.delete(*keys)
        except Exception as exc:
            logger.warning("Redis cache invalidation failed: error_type=%s", type(exc).__name__)

    def ready(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False


def summary_cache_key(dataset_id: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"summary:{dataset_id}:{digest}"


cache_service = (
    RedisCache(settings.redis_url, settings.cache_ttl_seconds)
    if settings.redis_url
    else NullCache()
)
