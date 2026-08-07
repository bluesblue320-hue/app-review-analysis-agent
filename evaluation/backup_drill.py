"""PostgreSQL backup and isolated-environment restore drill.

Usage (with a running postgres container from docker-compose):

    python -m evaluation.backup_drill \
        --database-url postgresql+psycopg2://app:app@localhost:5432/app \
        --backup-dir evaluation/reports/backup-drill

Drill steps:
1. Create a dataset via the SQLAlchemy store (persisted to PostgreSQL).
2. Dump the database with pg_dump.
3. Drop/recreate the schema (simulating data loss).
4. Restore from the dump.
5. Verify the dataset is readable again.

PostgreSQL must be reachable; the drill refuses to run against SQLite.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent


def _pg_tools(database_url: str) -> tuple[str, str]:
    """Extract host/db from a SQLAlchemy URL and find pg_dump/pg_restore."""
    # postgresql+psycopg2://user:pass@host:port/db
    without_driver = database_url.split("://", 1)[1]
    credentials, rest = without_driver.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    host_port, _, dbname = rest.rpartition("/")
    host, _, port = host_port.rpartition(":")
    if not port:
        port = "5432"
    pg_env = {
        "PGHOST": host or "localhost",
        "PGPORT": port,
        "PGUSER": user,
        "PGDATABASE": dbname,
    }
    return pg_env, dbname


def drill(database_url: str, backup_dir: Path) -> dict[str, Any]:
    pg_env, dbname = _pg_tools(database_url)
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_path = backup_dir / "app_backup.sql"
    results: dict[str, Any] = {}

    from backend.services.sqlalchemy_dataset_store import SqlAlchemyDatasetStore

    store = SqlAlchemyDatasetStore(database_url)
    dataset = store.create(
        "reviews.csv",
        "评分,内容,版本,时间\n1,无故封号,2.0.0,2026-07-01\n5,内容丰富,1.9.0,2026-07-02\n".encode(),
    )
    results["dataset_created"] = dataset.dataset_id is not None

    dump = subprocess.run(
        ["pg_dump", "-Fc", "-f", str(dump_path), dbname],
        env={**__import__("os").environ, **pg_env},
        capture_output=True,
        text=True,
    )
    results["dump_ok"] = dump.returncode == 0
    if not results["dump_ok"]:
        results["dump_stderr"] = dump.stderr[-500:]
        return results

    # Simulate data loss: drop all rows in datasets (cascades reviews/insights).
    from backend.storage.database import DatasetModel, get_database_runtime

    runtime = get_database_runtime(database_url)
    with runtime.session_factory.begin() as session:
        from sqlalchemy import delete

        session.execute(delete(DatasetModel))
    try:
        store.get(dataset.dataset_id)
        results["data_loss_verified"] = False
    except Exception:
        results["data_loss_verified"] = True

    # Restore from dump.
    restore = subprocess.run(
        ["pg_restore", "-Fc", "-c", "--if-exists", "-d", dbname, str(dump_path)],
        env={**__import__("os").environ, **pg_env},
        capture_output=True,
        text=True,
    )
    results["restore_ok"] = restore.returncode == 0
    if not results["restore_ok"]:
        results["restore_stderr"] = restore.stderr[-500:]
        return results

    restored = store.get(dataset.dataset_id)
    results["restored_dataset_readable"] = restored.valid_rows == 2
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="PostgreSQL 备份/恢复演练")
    parser.add_argument(
        "--database-url",
        default="postgresql+psycopg2://app:app@localhost:5432/app",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(PACKAGE_DIR / "reports" / "backup-drill"),
    )
    args = parser.parse_args()

    if "sqlite" in args.database_url:
        print("备份演练要求 PostgreSQL，拒绝针对 SQLite 执行。", file=sys.stderr)
        return 2

    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "database_url_sanitized": args.database_url.split("://")[0] + "://***@***/***",
        "checks": drill(args.database_url, Path(args.backup_dir)),
    }
    report["all_passed"] = all(report["checks"].values())
    report_path = Path(args.backup_dir) / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
