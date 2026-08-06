"""SQLAlchemy-backed AI insight repository with fingerprint deduplication."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from backend.core.config import settings
from backend.services.insight_store import InsightNotFoundError, InsightRecord
from backend.services.repositories import (
    ANALYSIS_VERSION,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    compute_insight_fingerprint,
)
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
        analysis_version: str = ANALYSIS_VERSION,
        provider: str = DEFAULT_PROVIDER,
        model_name: str = DEFAULT_MODEL,
    ) -> InsightRecord:
        fingerprint = compute_insight_fingerprint(
            dataset_id=dataset_id,
            scope_signature=scope_signature,
            sample_size=sample_size,
            analysis_version=analysis_version,
            provider=provider,
            model_name=model_name,
        )
        return self.upsert_fingerprint(
            fingerprint=fingerprint,
            dataset_id=dataset_id,
            scope_signature=scope_signature,
            sample_size=sample_size,
            insights=insights,
            analysis_version=analysis_version,
            provider=provider,
            model_name=model_name,
        )

    def find_by_fingerprint(self, fingerprint: str) -> InsightRecord | None:
        now = datetime.now(UTC)
        with self._runtime.session_factory.begin() as session:
            model = session.scalars(
                select(InsightModel).where(
                    InsightModel.insight_fingerprint == fingerprint,
                    InsightModel.expires_at > now,
                )
            ).first()
            if model is None:
                return None
            return self._record(model)

    def upsert_fingerprint(
        self,
        *,
        fingerprint: str,
        dataset_id: str,
        scope_signature: str,
        sample_size: int,
        insights: dict,
        analysis_version: str = ANALYSIS_VERSION,
        provider: str = DEFAULT_PROVIDER,
        model_name: str = DEFAULT_MODEL,
    ) -> InsightRecord:
        """Atomic insert-or-get-existing keyed by fingerprint.

        Unique-constraint conflicts are normal concurrency outcomes: the
        conflicting statement is rolled back inside a savepoint and the
        already-existing record is read and returned (never an HTTP 500).
        """
        now = datetime.now(UTC)
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
                provider=provider,
                model_name=model_name,
                analysis_version=analysis_version,
                insight_fingerprint=fingerprint,
                created_at=now,
                expires_at=dataset.expires_at,
            )
            session.add(model)
            try:
                session.flush()
            except IntegrityError:
                # Conflict: another request inserted the same fingerprint first.
                session.rollback()
                with self._runtime.session_factory.begin() as read_session:
                    existing = read_session.scalars(
                        select(InsightModel).where(
                            InsightModel.insight_fingerprint == fingerprint
                        )
                    ).first()
                    if existing is None:
                        raise InsightNotFoundError(fingerprint) from None
                    return self._record(existing)
            return self._record(model)

    def refresh_expired(
        self,
        *,
        fingerprint: str,
        insights: dict,
        provider: str = DEFAULT_PROVIDER,
        model_name: str = DEFAULT_MODEL,
    ) -> InsightRecord:
        """Update an expired same-fingerprint record in place (no new row)."""
        now = datetime.now(UTC)
        with self._runtime.session_factory.begin() as session:
            model = session.scalars(
                select(InsightModel).where(
                    InsightModel.insight_fingerprint == fingerprint
                )
            ).first()
            if model is None:
                raise InsightNotFoundError(fingerprint)
            dataset = session.get(DatasetModel, model.dataset_id)
            model.payload_json = deepcopy(insights)
            model.provider = provider
            model.model_name = model_name
            model.created_at = now
            model.expires_at = dataset.expires_at if dataset else now
            session.flush()
            return self._record(model)

    def get(self, insight_id: str) -> InsightRecord:
        now = datetime.now(UTC)
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
            session.execute(
                delete(InsightModel).where(InsightModel.dataset_id == dataset_id)
            )

    def cleanup_expired(self) -> int:
        now = datetime.now(UTC)
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
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
