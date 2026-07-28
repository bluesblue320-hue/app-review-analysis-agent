"""In-memory dataset upload and lookup service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import RLock
from uuid import uuid4

import pandas as pd

from backend.core.config import settings
from backend.core.exceptions import (
    DatasetNotFoundError,
    InvalidDatasetError,
    UnsupportedFileTypeError,
    UploadTooLargeError,
)
from review_fields import REQUIRED_REVIEW_COLUMNS
from review_preprocessing import preprocess_reviews
from visual_analysis import prepare_dashboard_data


@dataclass(frozen=True)
class DatasetRecord:
    dataset_id: str
    dataframe: pd.DataFrame
    original_rows: int
    valid_rows: int
    columns: tuple[str, ...]
    created_at: datetime


class InMemoryDatasetStore:
    def __init__(self) -> None:
        self._records: dict[str, DatasetRecord] = {}
        self._lock = RLock()

    def create(self, filename: str, content: bytes) -> DatasetRecord:
        if Path(filename or "").suffix.lower() != ".csv":
            raise UnsupportedFileTypeError()
        if len(content) > settings.max_upload_size_mb * 1024 * 1024:
            raise UploadTooLargeError(settings.max_upload_size_mb)
        if not content:
            raise InvalidDatasetError("CSV 文件为空。")

        try:
            raw_dataframe = pd.read_csv(BytesIO(content))
        except pd.errors.EmptyDataError as exc:
            raise InvalidDatasetError("CSV 文件为空或不包含字段。") from exc
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise InvalidDatasetError(f"CSV 文件无法解析：{exc}") from exc

        missing_columns = REQUIRED_REVIEW_COLUMNS - set(raw_dataframe.columns)
        if missing_columns:
            missing = "、".join(sorted(missing_columns))
            raise InvalidDatasetError(f"CSV 缺少必要列：{missing}")

        original_rows = int(len(raw_dataframe))
        processed = preprocess_reviews(raw_dataframe)
        prepared = prepare_dashboard_data(processed)
        created_at = datetime.now(timezone.utc)
        dataset_id = f"dataset_{uuid4().hex}"
        record = DatasetRecord(
            dataset_id=dataset_id,
            dataframe=prepared.copy(deep=True),
            original_rows=original_rows,
            valid_rows=int(len(prepared)),
            columns=tuple(str(column) for column in raw_dataframe.columns),
            created_at=created_at,
        )
        with self._lock:
            self._records[dataset_id] = record
        return self._copy_record(record)

    def get(self, dataset_id: str) -> DatasetRecord:
        with self._lock:
            record = self._records.get(dataset_id)
            if record is None:
                raise DatasetNotFoundError(dataset_id)
            return self._copy_record(record)

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
        )


dataset_store = InMemoryDatasetStore()
