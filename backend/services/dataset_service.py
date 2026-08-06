"""In-memory dataset upload and lookup service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

import pandas as pd

from backend.core.config import settings
from backend.core.exceptions import DatasetNotFoundError
from backend.services.dataset_ingestion import parse_and_prepare_dataset


@dataclass(frozen=True)
class DatasetRecord:
    dataset_id: str
    dataframe: pd.DataFrame
    original_rows: int
    valid_rows: int
    columns: tuple[str, ...]
    created_at: datetime
    expires_at: datetime


class InMemoryDatasetStore:
    def __init__(self) -> None:
        self._records: dict[str, DatasetRecord] = {}
        self._lock = RLock()

    def create(self, filename: str, content: bytes) -> DatasetRecord:
        raw_dataframe, prepared = parse_and_prepare_dataset(filename, content, settings)
        original_rows = int(len(raw_dataframe))
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(days=settings.data_retention_days)
        dataset_id = f"dataset_{uuid4().hex}"
        record = DatasetRecord(
            dataset_id=dataset_id,
            dataframe=prepared.copy(deep=True),
            original_rows=original_rows,
            valid_rows=int(len(prepared)),
            columns=tuple(str(column) for column in raw_dataframe.columns),
            created_at=created_at,
            expires_at=expires_at,
        )
        with self._lock:
            self._records[dataset_id] = record
        return self._copy_record(record)

    def get(self, dataset_id: str) -> DatasetRecord:
        with self._lock:
            record = self._records.get(dataset_id)
            if record is None or record.expires_at <= datetime.now(timezone.utc):
                self._records.pop(dataset_id, None)
                raise DatasetNotFoundError(dataset_id)
            return self._copy_record(record)

    def delete(self, dataset_id: str) -> None:
        with self._lock:
            if self._records.pop(dataset_id, None) is None:
                raise DatasetNotFoundError(dataset_id)

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        with self._lock:
            expired = [key for key, value in self._records.items() if value.expires_at <= now]
            for key in expired:
                self._records.pop(key, None)
            return len(expired)

    def ready(self) -> bool:
        return True

    def clear(self) -> None:
        """Clear process-local state; used by integration tests and local reloads."""
        with self._lock:
            self._records.clear()

    @staticmethod
    def _copy_record(record: DatasetRecord) -> DatasetRecord:
        return DatasetRecord(
            dataset_id=record.dataset_id,
            dataframe=record.dataframe.copy(deep=True),
            original_rows=record.original_rows,
            valid_rows=record.valid_rows,
            columns=record.columns,
            created_at=record.created_at,
            expires_at=record.expires_at,
        )


def _build_dataset_store():
    if settings.storage_backend == "database":
        from backend.services.sqlalchemy_dataset_store import SqlAlchemyDatasetStore

        return SqlAlchemyDatasetStore(settings.database_url)
    return InMemoryDatasetStore()


dataset_store = _build_dataset_store()
