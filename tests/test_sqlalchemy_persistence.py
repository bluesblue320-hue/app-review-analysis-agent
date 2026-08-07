"""Stage 3: SQLAlchemy/PostgreSQL repository persistence tests.

Uses SQLite in-memory/temp files to exercise the same SQLAlchemy 2 code paths
that run against PostgreSQL; migrations are validated against a temp database.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from backend.core.exceptions import DatasetNotFoundError
from backend.services.insight_store import InsightNotFoundError
from backend.services.repositories import (
    ANALYSIS_VERSION,
    compute_insight_fingerprint,
)
from backend.services.sqlalchemy_dataset_store import SqlAlchemyDatasetStore
from backend.services.sqlalchemy_insight_store import SqlAlchemyInsightStore
from backend.storage.database import InsightModel, get_database_runtime


@pytest.fixture()
def sqlite_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'stage3.db'}"


@pytest.fixture()
def dataset_store(sqlite_url):
    store = SqlAlchemyDatasetStore(sqlite_url)
    store.clear()
    yield store
    store.clear()


@pytest.fixture()
def insight_store(sqlite_url):
    store = SqlAlchemyInsightStore(sqlite_url)
    store.clear()
    yield store
    store.clear()


def _csv_bytes() -> bytes:
    rows = [
        "评分,内容,版本,时间",
        "1,无故封号,2.0.0,2026-07-01",
        "5,内容丰富,1.9.0,2026-07-02",
        "4,搜索体验好,2.0.0,2026-07-03",
    ]
    return "\n".join(rows).encode("utf-8")


def test_dataset_survives_service_restart(dataset_store, sqlite_url) -> None:
    record = dataset_store.create("reviews.csv", _csv_bytes())
    # A fresh store instance against the same database file = "restart".
    reloaded = SqlAlchemyDatasetStore(sqlite_url)
    restored = reloaded.get(record.dataset_id)
    assert restored.valid_rows == 3
    assert restored.content_hash == record.content_hash
    assert len(restored.dataframe) == 3


def test_insight_survives_service_restart(
    dataset_store, insight_store, sqlite_url
) -> None:
    dataset = dataset_store.create("reviews.csv", _csv_bytes())
    record = insight_store.create(
        dataset_id=dataset.dataset_id,
        scope_signature="sig1",
        sample_size=3,
        insights={"summary": "持久洞察"},
    )
    reloaded = SqlAlchemyInsightStore(sqlite_url)
    restored = reloaded.get(record.insight_id)
    assert restored.insights == {"summary": "持久洞察"}


def test_delete_cascades_reviews_and_insights(dataset_store, insight_store) -> None:
    dataset = dataset_store.create("reviews.csv", _csv_bytes())
    insight_store.create(
        dataset_id=dataset.dataset_id,
        scope_signature="sig1",
        sample_size=3,
        insights={"summary": "将被级联删除"},
    )
    dataset_store.delete(dataset.dataset_id)
    with pytest.raises(DatasetNotFoundError):
        dataset_store.get(dataset.dataset_id)
    # Insight for the deleted dataset must be gone too.
    runtime = insight_store._runtime
    with runtime.session_factory.begin() as session:
        from sqlalchemy import select

        remaining = session.scalars(
            select(InsightModel).where(InsightModel.dataset_id == dataset.dataset_id)
        ).all()
    assert remaining == []


def test_expired_dataset_unreadable_after_cleanup(dataset_store) -> None:
    dataset = dataset_store.create("reviews.csv", _csv_bytes())
    runtime = dataset_store._runtime
    with runtime.session_factory.begin() as session:
        from backend.storage.database import DatasetModel

        model = session.get(DatasetModel, dataset.dataset_id)
        model.expires_at = datetime.now(UTC) - timedelta(days=1)
    with pytest.raises(DatasetNotFoundError):
        dataset_store.get(dataset.dataset_id)
    assert dataset_store.cleanup_expired() >= 1
    # Second cleanup is idempotent.
    assert dataset_store.cleanup_expired() == 0


def test_same_fingerprint_concurrent_upsert_yields_one_record(
    dataset_store, insight_store
) -> None:
    dataset = dataset_store.create("reviews.csv", _csv_bytes())
    fingerprint = compute_insight_fingerprint(
        dataset_id=dataset.dataset_id,
        scope_signature="sig-concurrent",
        sample_size=3,
        analysis_version=ANALYSIS_VERSION,
    )
    results: list[str] = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            record = insight_store.upsert_fingerprint(
                fingerprint=fingerprint,
                dataset_id=dataset.dataset_id,
                scope_signature="sig-concurrent",
                sample_size=3,
                insights={"summary": "并发写入"},
            )
            results.append(record.insight_id)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(set(results)) == 1


def test_unique_conflict_returns_existing_not_500(insight_store) -> None:
    """Insert-or-get-existing: conflict must read and return the existing row."""
    from backend.storage.database import DatasetModel

    runtime = insight_store._runtime
    with runtime.session_factory.begin() as session:
        session.add(
            DatasetModel(
                dataset_id="d_existing",
                filename="f.csv",
                original_rows=1,
                valid_rows=1,
                columns_json=["评分"],
                content_hash="h",
                analysis_version="v1",
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
    fingerprint = compute_insight_fingerprint(
        dataset_id="d_existing", scope_signature="sig", sample_size=1
    )
    first = insight_store.upsert_fingerprint(
        fingerprint=fingerprint,
        dataset_id="d_existing",
        scope_signature="sig",
        sample_size=1,
        insights={"summary": "第一个"},
    )
    second = insight_store.upsert_fingerprint(
        fingerprint=fingerprint,
        dataset_id="d_existing",
        scope_signature="sig",
        sample_size=1,
        insights={"summary": "第二个"},
    )
    assert first.insight_id == second.insight_id
    assert insight_store.get(first.insight_id).insights == {"summary": "第一个"}


def test_refresh_expired_keeps_same_insight_id(insight_store) -> None:
    from backend.storage.database import DatasetModel

    runtime = insight_store._runtime
    with runtime.session_factory.begin() as session:
        session.add(
            DatasetModel(
                dataset_id="d_expired",
                filename="f.csv",
                original_rows=1,
                valid_rows=1,
                columns_json=["评分"],
                content_hash="h",
                analysis_version="v1",
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
    fingerprint = compute_insight_fingerprint(
        dataset_id="d_expired", scope_signature="sig", sample_size=1
    )
    original = insight_store.upsert_fingerprint(
        fingerprint=fingerprint,
        dataset_id="d_expired",
        scope_signature="sig",
        sample_size=1,
        insights={"summary": "旧"},
    )
    with runtime.session_factory.begin() as session:
        model = session.get(InsightModel, original.insight_id)
        model.expires_at = datetime.now(UTC) - timedelta(days=1)
    refreshed = insight_store.refresh_expired(
        fingerprint=fingerprint,
        insights={"summary": "新"},
    )
    assert refreshed.insight_id == original.insight_id
    assert refreshed.insights == {"summary": "新"}
    # Exactly one row remains.
    runtime2 = insight_store._runtime
    with runtime2.session_factory.begin() as session:
        from sqlalchemy import func, select

        count = session.scalar(
            select(func.count(InsightModel.insight_id)).where(
                InsightModel.insight_fingerprint == fingerprint
            )
        )
    assert count == 1


def test_find_by_fingerprint_hits_and_expired_miss(insight_store) -> None:
    from backend.storage.database import DatasetModel

    runtime = insight_store._runtime
    with runtime.session_factory.begin() as session:
        session.add(
            DatasetModel(
                dataset_id="d_fp",
                filename="f.csv",
                original_rows=1,
                valid_rows=1,
                columns_json=["评分"],
                content_hash="h",
                analysis_version="v1",
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
    fingerprint = compute_insight_fingerprint(
        dataset_id="d_fp", scope_signature="sig", sample_size=1
    )
    record = insight_store.upsert_fingerprint(
        fingerprint=fingerprint,
        dataset_id="d_fp",
        scope_signature="sig",
        sample_size=1,
        insights={"summary": "命中"},
    )
    assert (
        insight_store.find_by_fingerprint(fingerprint).insight_id == record.insight_id
    )
    # Expire it.
    with runtime.session_factory.begin() as session:
        model = session.get(InsightModel, record.insight_id)
        model.expires_at = datetime.now(UTC) - timedelta(days=1)
    assert insight_store.find_by_fingerprint(fingerprint) is None
    # include_expired=True still returns the expired record so the service can
    # distinguish "expired" from "not found" and refresh it in place.
    expired = insight_store.get_by_fingerprint(fingerprint, include_expired=True)
    assert expired is not None
    assert expired.insight_id == record.insight_id
    assert expired.is_expired is True
    # get_by_fingerprint(include_expired=False) behaves like find_by_fingerprint.
    assert insight_store.get_by_fingerprint(fingerprint) is None


def test_refresh_expired_after_get_by_fingerprint_keeps_id(insight_store) -> None:
    from backend.storage.database import DatasetModel

    runtime = insight_store._runtime
    with runtime.session_factory.begin() as session:
        session.add(
            DatasetModel(
                dataset_id="d_ref",
                filename="f.csv",
                original_rows=1,
                valid_rows=1,
                columns_json=["评分"],
                content_hash="h",
                analysis_version="v1",
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
    fingerprint = compute_insight_fingerprint(
        dataset_id="d_ref", scope_signature="sig", sample_size=1
    )
    first = insight_store.upsert_fingerprint(
        fingerprint=fingerprint,
        dataset_id="d_ref",
        scope_signature="sig",
        sample_size=1,
        insights={"summary": "旧内容"},
    )
    # Expire the record.
    with runtime.session_factory.begin() as session:
        model = session.get(InsightModel, first.insight_id)
        model.expires_at = datetime.now(UTC) - timedelta(days=1)

    # Service flow: include_expired finds it, then refresh replaces payload.
    refreshed = insight_store.refresh_expired(
        fingerprint=fingerprint,
        insights={"summary": "新内容"},
        provider="deepseek",
        model_name="deepseek-v4-flash",
    )
    assert refreshed.insight_id == first.insight_id  # same id kept
    assert refreshed.insights["summary"] == "新内容"
    assert refreshed.expires_at > datetime.now(UTC)
    # No expired content is served afterward.
    assert insight_store.find_by_fingerprint(fingerprint).insights["summary"] == "新内容"


def test_cleanup_expired_insights_idempotent(insight_store) -> None:
    from backend.storage.database import DatasetModel

    runtime = insight_store._runtime
    with runtime.session_factory.begin() as session:
        session.add(
            DatasetModel(
                dataset_id="d_cleanup",
                filename="f.csv",
                original_rows=1,
                valid_rows=1,
                columns_json=["评分"],
                content_hash="h",
                analysis_version="v1",
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
    fingerprint = compute_insight_fingerprint(
        dataset_id="d_cleanup", scope_signature="sig", sample_size=1
    )
    record = insight_store.upsert_fingerprint(
        fingerprint=fingerprint,
        dataset_id="d_cleanup",
        scope_signature="sig",
        sample_size=1,
        insights={"summary": "过期"},
    )
    with runtime.session_factory.begin() as session:
        model = session.get(InsightModel, record.insight_id)
        model.expires_at = datetime.now(UTC) - timedelta(days=1)
    assert insight_store.cleanup_expired() >= 1
    assert insight_store.cleanup_expired() == 0
    with pytest.raises(InsightNotFoundError):
        insight_store.get(record.insight_id)


def test_alembic_upgrade_downgrade_roundtrip(tmp_path) -> None:
    """Empty PostgreSQL-equivalent DB: alembic upgrade head then downgrade."""
    import subprocess
    import sys

    db_url = f"sqlite:///{tmp_path / 'migrate.db'}"
    env = {**__import__("os").environ, "DATABASE_URL": db_url}
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
    )
    assert upgrade.returncode == 0, upgrade.stderr
    runtime = get_database_runtime(db_url)
    from sqlalchemy import inspect

    inspector = inspect(runtime.engine)
    tables = set(inspector.get_table_names())
    assert {"datasets", "reviews", "insights"} <= tables
    columns = {column["name"] for column in inspector.get_columns("insights")}
    assert {"insight_fingerprint", "provider", "model_name"} <= columns

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
    )
    assert downgrade.returncode == 0, downgrade.stderr
    inspector = inspect(runtime.engine)
    assert {"datasets", "reviews", "insights"} - set(inspector.get_table_names()) == {
        "datasets",
        "reviews",
        "insights",
    }
