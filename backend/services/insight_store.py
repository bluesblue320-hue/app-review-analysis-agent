"""Process-local storage and scope validation for generated AI insights."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4

from backend.core.config import settings

INSIGHT_NOT_FOUND_WARNING = "指定的 AI 洞察不存在，未使用 AI 洞察。"
INSIGHT_SCOPE_MISMATCH_WARNING = "当前数据范围与指定 AI 洞察不一致，旧洞察未被使用。"


class InsightNotFoundError(LookupError):
    """Raised internally when an insight record is no longer available."""


@dataclass(frozen=True)
class InsightRecord:
    insight_id: str
    dataset_id: str
    scope_signature: str
    sample_size: int
    insights: dict[str, Any]
    created_at: datetime
    expires_at: datetime


class InMemoryInsightStore:
    def __init__(self) -> None:
        self._records: dict[str, InsightRecord] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        dataset_id: str,
        scope_signature: str,
        sample_size: int,
        insights: dict[str, Any],
    ) -> InsightRecord:
        created_at = datetime.now(UTC)
        record = InsightRecord(
            insight_id=f"insight_{uuid4().hex}",
            dataset_id=dataset_id,
            scope_signature=scope_signature,
            sample_size=int(sample_size),
            insights=deepcopy(insights),
            created_at=created_at,
            expires_at=created_at + timedelta(days=settings.data_retention_days),
        )
        with self._lock:
            self._records[record.insight_id] = record
        return self._copy_record(record)

    def get(self, insight_id: str) -> InsightRecord:
        with self._lock:
            record = self._records.get(insight_id)
            if record is None or record.expires_at <= datetime.now(UTC):
                self._records.pop(insight_id, None)
                raise InsightNotFoundError(insight_id)
            return self._copy_record(record)

    def resolve(
        self,
        *,
        insight_id: str | None,
        dataset_id: str,
        scope_signature: str,
        sample_size: int,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if insight_id is None:
            return None, None

        try:
            record = self.get(insight_id)
        except InsightNotFoundError:
            return None, INSIGHT_NOT_FOUND_WARNING

        if (
            record.dataset_id != dataset_id
            or record.scope_signature != scope_signature
            or record.sample_size != int(sample_size)
        ):
            return None, INSIGHT_SCOPE_MISMATCH_WARNING
        return record.insights, None

    def delete_dataset(self, dataset_id: str) -> None:
        with self._lock:
            keys = [
                key
                for key, value in self._records.items()
                if value.dataset_id == dataset_id
            ]
            for key in keys:
                self._records.pop(key, None)

    def cleanup_expired(self) -> int:
        now = datetime.now(UTC)
        with self._lock:
            keys = [
                key for key, value in self._records.items() if value.expires_at <= now
            ]
            for key in keys:
                self._records.pop(key, None)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    @staticmethod
    def _copy_record(record: InsightRecord) -> InsightRecord:
        return InsightRecord(
            insight_id=record.insight_id,
            dataset_id=record.dataset_id,
            scope_signature=record.scope_signature,
            sample_size=record.sample_size,
            insights=deepcopy(record.insights),
            created_at=record.created_at,
            expires_at=record.expires_at,
        )


def _build_insight_store():
    if settings.storage_backend == "database":
        from backend.services.sqlalchemy_insight_store import SqlAlchemyInsightStore

        return SqlAlchemyInsightStore(settings.database_url)
    return InMemoryInsightStore()


insight_store = _build_insight_store()
