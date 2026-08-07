"""Cache abstraction (NullCache / MemoryCache / RedisCache) and Redis short lock.

Redis only implements deterministic analytics caching and the AI-insight
generation short lock. Service code never depends on redis-py directly; it
only sees the ``Cache`` protocol and the ``InsightLock`` helper.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from typing import Any, Protocol, runtime_checkable

from backend.core.config import settings

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 1


@runtime_checkable
class Cache(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...
    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None: ...
    def delete(self, key: str) -> None: ...


class NullCache:
    """No-op cache used when Redis is not configured."""

    def get(self, _key: str) -> dict[str, Any] | None:
        return None

    def set(self, _key: str, _value: dict[str, Any], ttl_seconds: int) -> None:
        return None

    def delete(self, _key: str) -> None:
        return None
    def invalidate_dataset(self, _dataset_id: str) -> None:
        return None

    def ready(self) -> bool:
        return True


class MemoryCache:
    """Thread-safe process-local cache for tests and local fallback."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= time.monotonic():
                self._entries.pop(key, None)
                return None
            return json.loads(json.dumps(value, ensure_ascii=False))

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        with self._lock:
            self._entries[key] = (
                time.monotonic() + max(0, int(ttl_seconds)),
                json.loads(json.dumps(value, ensure_ascii=False)),
            )

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def invalidate_dataset(self, dataset_id: str) -> None:
        prefix = f"ara:{_env_tag()}:v1:analytics:{dataset_id}:"
        with self._lock:
            for key in list(self._entries):
                if key.startswith(prefix):
                    self._entries.pop(key, None)

    def ready(self) -> bool:
        return True

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class RedisCache:
    def __init__(self, url: str, ttl_seconds: int) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._ttl_seconds = ttl_seconds

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            value = self._client.get(key)
            if not value:
                return None
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                return None
            return parsed
        except Exception as exc:
            logger.warning("Redis cache read failed: error_type=%s", type(exc).__name__)
            return None

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        try:
            self._client.setex(
                key,
                max(1, int(ttl_seconds)),
                json.dumps(value, ensure_ascii=False),
            )
        except Exception as exc:
            logger.warning("Redis cache write failed: error_type=%s", type(exc).__name__)

    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except Exception as exc:
            logger.warning("Redis cache delete failed: error_type=%s", type(exc).__name__)

    def invalidate_dataset(self, dataset_id: str) -> None:
        try:
            keys = list(
                self._client.scan_iter(
                    match=f"ara:{_env_tag()}:v1:analytics:{dataset_id}:*",
                    count=100,
                )
            )
            if keys:
                self._client.delete(*keys)
            lock_keys = list(
                self._client.scan_iter(
                    match=f"ara:{_env_tag()}:v1:lock:insight:{dataset_id}:*",
                    count=100,
                )
            )
            if lock_keys:
                self._client.delete(*lock_keys)
        except Exception as exc:
            logger.warning(
                "Redis cache invalidation failed: error_type=%s", type(exc).__name__
            )

    def ready(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def _client_handle(self):
        return self._client


class InsightLock:
    """Atomic Redis short lock guarding duplicate AI-insight model calls.

    The lock only reduces duplicate model calls (cost optimization); data
    uniqueness is guaranteed by the PostgreSQL UNIQUE(insight_fingerprint)
    constraint and insert-or-get-existing, so Redis failure never breaks the
    system.
    """

    def __init__(self, cache: Any, lock_ttl_seconds: int = 30) -> None:
        self._cache = cache
        self._lock_ttl_seconds = lock_ttl_seconds
        self._local: dict[str, str] = {}
        self._local_lock = threading.RLock()

    def acquire(self, key: str) -> bool:
        """Try to take the lock; returns True when this caller holds it."""
        token = uuid.uuid4().hex
        if isinstance(self._cache, RedisCache):
            try:
                acquired = self._cache._client_handle().set(
                    key, token, nx=True, ex=self._lock_ttl_seconds
                )
                if not acquired:
                    return False
            except Exception as exc:
                logger.warning(
                    "Redis lock acquire failed: error_type=%s", type(exc).__name__
                )
                # Redis failure: let the caller proceed; PostgreSQL still
                # guarantees a single insight row.
                return True
        elif isinstance(self._cache, MemoryCache):
            with self._local_lock:
                entry = self._cache._entries.get(key)
                if entry is not None and entry[0] > time.monotonic():
                    return False
                self._cache._entries[key] = (
                    time.monotonic() + self._lock_ttl_seconds,
                    {"token": token},
                )
        else:
            # NullCache: no lock, rely on the database constraint.
            return True
        with self._local_lock:
            self._local[key] = token
        return True

    def release(self, key: str) -> None:
        """Release only when this caller still holds the token (token-safe)."""
        with self._local_lock:
            token = self._local.pop(key, None)
        if token is None:
            return
        if isinstance(self._cache, RedisCache):
            try:
                pipeline = self._cache._client_handle().pipeline()
                pipeline.watch(key)
                current = pipeline.get(key)
                if current == token:
                    pipeline.multi()
                    pipeline.delete(key)
                    pipeline.execute()
                pipeline.unwatch()
            except Exception as exc:
                logger.warning(
                    "Redis lock release failed: error_type=%s", type(exc).__name__
                )
        elif isinstance(self._cache, MemoryCache):
            with self._local_lock:
                entry = self._cache._entries.get(key)
                if entry and entry[1].get("token") == token:
                    self._cache._entries.pop(key, None)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        for key in list(self._local):
            self.release(key)
        return False


def summary_cache_key(dataset_id: str, payload: dict[str, Any]) -> str:
    """Deterministic cache key for analytics payloads (scope not included)."""
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"summary:{dataset_id}:{digest}"


def analytics_cache_key(
    *,
    dataset_id: str,
    scope_signature: str,
    analysis_type: str,
    insight_id: str | None = None,
) -> str:
    return (
        f"ara:{_env_tag()}:v1:analytics:{dataset_id}:{scope_signature}:"
        f"{analysis_type}:{insight_id or 'none'}"
    )


def insight_lock_key(dataset_id: str, scope_signature: str) -> str:
    return f"ara:{_env_tag()}:v1:lock:insight:{dataset_id}:{scope_signature}"


def dataset_keys_key(dataset_id: str) -> str:
    return f"ara:{_env_tag()}:v1:dataset-keys:{dataset_id}"


def _env_tag() -> str:
    return settings.app_env or "dev"


def build_cache(
    *,
    redis_url: str | None = None,
    ttl_seconds: int | None = None,
    memory: bool = False,
) -> Any:
    """Build the active cache based on configuration (Redis > Memory > Null)."""
    url = redis_url if redis_url is not None else settings.redis_url
    ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
    if url:
        return RedisCache(url, ttl)
    if memory:
        return MemoryCache()
    return NullCache()


cache_service = build_cache()
insight_lock = InsightLock(cache_service)
