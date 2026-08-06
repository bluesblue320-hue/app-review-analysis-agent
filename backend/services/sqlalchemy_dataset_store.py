"""SQLAlchemy-backed dataset repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pandas as pd
from sqlalchemy import delete, select

from backend.core.config import settings
from backend.core.exceptions import DatasetNotFoundError
from backend.core.serialization import dataframe_to_records
from backend.services.dataset_ingestion import parse_and_prepare_dataset
from backend.services.dataset_service import DatasetRecord
from backend.storage.database import (
    DatasetModel,
    InsightModel,
    ReviewModel,
    database_ready,
    get_database_runtime,
)
from review_fields import (
    CATEGORY_COLUMN,
    CONTENT_COLUMN,
    RATING_COLUMN,
    RISK_LABEL_COLUMN,
    SENTIMENT_COLUMN,
    TIME_COLUMN_CANDIDATES,
    TITLE_COLUMN,
    TOKEN_COLUMN,
    VERSION_COLUMN,
)


class SqlAlchemyDatasetStore:
    def __init__(self, database_url: str | None = None) -> None:
        self._runtime = get_database_runtime(database_url or settings.database_url)

    def create(self, filename: str, content: bytes) -> DatasetRecord:
        raw, prepared = parse_and_prepare_dataset(filename, content, settings)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=settings.data_retention_days)
        dataset_id = f"dataset_{uuid4().hex}"
        records = dataframe_to_records(prepared)
        with self._runtime.session_factory.begin() as session:
            session.add(
                DatasetModel(
                    dataset_id=dataset_id,
                    filename=filename,
                    original_rows=int(len(raw)),
                    valid_rows=int(len(prepared)),
                    columns_json=[str(column) for column in raw.columns],
                    created_at=now,
                    expires_at=expires_at,
                )
            )
            session.add_all(
                self._review_model(dataset_id, index, record)
                for index, record in enumerate(records)
            )
        return DatasetRecord(
            dataset_id=dataset_id,
            dataframe=prepared.copy(deep=True),
            original_rows=int(len(raw)),
            valid_rows=int(len(prepared)),
            columns=tuple(str(column) for column in raw.columns),
            created_at=now,
            expires_at=expires_at,
        )

    def get(self, dataset_id: str) -> DatasetRecord:
        now = datetime.now(timezone.utc)
        with self._runtime.session_factory.begin() as session:
            model = session.get(DatasetModel, dataset_id)
            if model is None or _as_utc(model.expires_at) <= now:
                if model is not None:
                    session.delete(model)
                raise DatasetNotFoundError(dataset_id)
            rows = session.scalars(
                select(ReviewModel)
                .where(ReviewModel.dataset_id == dataset_id)
                .order_by(ReviewModel.row_number)
            ).all()
            dataframe = pd.DataFrame([row.payload_json for row in rows])
            return DatasetRecord(
                dataset_id=model.dataset_id,
                dataframe=dataframe,
                original_rows=model.original_rows,
                valid_rows=model.valid_rows,
                columns=tuple(model.columns_json),
                created_at=_as_utc(model.created_at),
                expires_at=_as_utc(model.expires_at),
            )

    def delete(self, dataset_id: str) -> None:
        with self._runtime.session_factory.begin() as session:
            model = session.get(DatasetModel, dataset_id)
            if model is None:
                raise DatasetNotFoundError(dataset_id)
            session.delete(model)

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        with self._runtime.session_factory.begin() as session:
            expired_ids = session.scalars(
                select(DatasetModel.dataset_id).where(DatasetModel.expires_at <= now)
            ).all()
            if expired_ids:
                session.execute(
                    delete(DatasetModel).where(DatasetModel.dataset_id.in_(expired_ids))
                )
            return len(expired_ids)

    def clear(self) -> None:
        with self._runtime.session_factory.begin() as session:
            session.execute(delete(InsightModel))
            session.execute(delete(ReviewModel))
            session.execute(delete(DatasetModel))

    def ready(self) -> bool:
        return database_ready(self._runtime.engine)

    @staticmethod
    def _review_model(
        dataset_id: str,
        row_number: int,
        payload: dict[str, object],
    ) -> ReviewModel:
        review_time = next(
            (payload.get(column) for column in TIME_COLUMN_CANDIDATES if payload.get(column)),
            None,
        )
        return ReviewModel(
            dataset_id=dataset_id,
            row_number=row_number,
            rating=_float_or_none(payload.get(RATING_COLUMN)),
            content=str(payload.get(CONTENT_COLUMN) or ""),
            title=_string_or_none(payload.get(TITLE_COLUMN)),
            review_time=_string_or_none(review_time),
            version=_string_or_none(payload.get(VERSION_COLUMN)),
            tokens=_string_or_none(payload.get(TOKEN_COLUMN)),
            sentiment=_float_or_none(payload.get(SENTIMENT_COLUMN)),
            category=_string_or_none(payload.get(CATEGORY_COLUMN)),
            risk_label=_string_or_none(payload.get(RISK_LABEL_COLUMN)),
            payload_json=payload,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _float_or_none(value):
    return None if value is None else float(value)


def _string_or_none(value):
    return None if value is None else str(value)
