"""SQLAlchemy-backed AI insight repository."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from backend.core.config import settings
from backend.services.insight_store import InsightNotFoundError, InsightRecord
from backend.storage.database import DatasetModel, InsightModel, get_database_runtime


class SqlAlchemyInsightStore:
    def __init__(self, database_url: str | None = None) -> None:
        self._runtime = get_database_runtime(database_url or settings.database_url)

    def create(
        self,
        *,
        dataset_id: str,
        scope_signature: str,
        sample_size: int,
        insights: dict,
    ) -> InsightRecord:
        now = datetime.now(timezone.utc)
        with self._runtime.session_factory.begin() as session:
            dataset = session.get(DatasetModel, dataset_id)
            if dataset is None:
                raise InsightNotFoundError(dataset_id)
            model = InsightModel(
                insight_id=f"insight_{uuid4().hex}",
                dataset_id=dataset_id,
                scope_signature=scope_signature,
                sample_size=int(sample_size),
                payload_json=deepcopy(insights),
                created_at=now,
                expires_at=dataset.expires_at,
            )
            session.add(model)
        return self._record(model)

    def get(self, insight_id: str) -> InsightRecord:
        now = datetime.now(timezone.utc)
        with self._runtime.session_factory.begin() as session:
            model = session.get(InsightModel, insight_id)
            if model is None or _as_utc(model.expires_at) <= now:
                if model is not None:
                    session.delete(model)
                raise InsightNotFoundError(insight_id)
            return self._record(model)

    def resolve(
        self,
        *,
        insight_id: str | None,
        dataset_id: str,
        scope_signature: str,
        sample_size: int,
    ) -> tuple[dict | None, str | None]:
        if insight_id is None:
            return None, None
        from backend.services.insight_store import (
            INSIGHT_NOT_FOUND_WARNING,
            INSIGHT_SCOPE_MISMATCH_WARNING,
        )

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

    def clear(self) -> None:
        with self._runtime.session_factory.begin() as session:
            session.execute(delete(InsightModel))

    def delete_dataset(self, dataset_id: str) -> None:
        with self._runtime.session_factory.begin() as session:
            session.execute(delete(InsightModel).where(InsightModel.dataset_id == dataset_id))

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        with self._runtime.session_factory.begin() as session:
            expired_ids = session.scalars(
                select(InsightModel.insight_id).where(InsightModel.expires_at <= now)
            ).all()
            if expired_ids:
                session.execute(
                    delete(InsightModel).where(InsightModel.insight_id.in_(expired_ids))
                )
            return len(expired_ids)

    def _record(self, model: InsightModel) -> InsightRecord:
        return InsightRecord(
            insight_id=model.insight_id,
            dataset_id=model.dataset_id,
            scope_signature=model.scope_signature,
            sample_size=model.sample_size,
            insights=deepcopy(model.payload_json),
            created_at=_as_utc(model.created_at),
            expires_at=_as_utc(model.expires_at),
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
