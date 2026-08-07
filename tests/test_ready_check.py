"""Task 6: /ready migration-aware readiness checks."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from backend.schemas.common import ReadyResponse


class TestReadyResponseSchema(unittest.TestCase):
    def test_schema_parses_full_payload(self) -> None:
        payload = ReadyResponse(
            status="ok",
            service="app-review-analysis-agent",
            database="ok",
            migration="head",
            redis="ok",
        )
        data = json.loads(payload.model_dump_json())
        assert data == {
            "status": "ok",
            "service": "app-review-analysis-agent",
            "database": "ok",
            "migration": "head",
            "redis": "ok",
        }

    def test_schema_rejects_unknown_fields(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            ReadyResponse(  # type: ignore[call-arg]
                status="ok",
                service="x",
                database="ok",
                migration="head",
                redis="ok",
                extra="nope",
            )


class TestReadyCheckMemoryBackend(unittest.TestCase):
    def _settings(self, **overrides):
        from backend.core.config import Settings

        base = Settings()
        return Settings(
            **{
                **{
                    "service_name": base.service_name,
                    "storage_backend": "memory",
                    "database_url": base.database_url,
                },
                **overrides,
            }
        )

    def _call(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        client = TestClient(app)
        return client.get("/api/v1/ready")

    def test_memory_backend_ready_ok(self) -> None:
        mock_settings = self._settings()
        with (
            patch("backend.routers.health.settings", mock_settings),
            patch(
                "backend.services.cache_service.cache_service.ready", return_value=True
            ),
        ):
            response = self._call()
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "n/a"
        assert body["migration"] == "n/a"
        assert body["redis"] == "ok"

    def test_memory_backend_redis_degraded(self) -> None:
        mock_settings = self._settings()
        with (
            patch("backend.routers.health.settings", mock_settings),
            patch(
                "backend.services.cache_service.cache_service.ready", return_value=False
            ),
        ):
            response = self._call()
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
        assert response.json()["redis"] == "degraded"


class TestReadyCheckDatabaseBackend(unittest.TestCase):
    def _settings(self, **overrides):
        from backend.core.config import Settings

        base = Settings()
        return Settings(
            **{
                **{
                    "service_name": base.service_name,
                    "storage_backend": "database",
                    "database_url": "sqlite:///./data/ready.db",
                },
                **overrides,
            }
        )

    def _call(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        client = TestClient(app)
        return client.get("/api/v1/ready")

    def test_database_connected_head_ok(self) -> None:
        with (
            patch("backend.routers.health.settings", self._settings()),
            patch(
                "backend.services.dataset_service.dataset_store.ready",
                return_value=True,
            ),
            patch("backend.routers.health._alembic_head", return_value="aeb4cbb3b3b2"),
            patch(
                "backend.routers.health._current_revision", return_value="aeb4cbb3b3b2"
            ),
            patch(
                "backend.services.cache_service.cache_service.ready", return_value=True
            ),
        ):
            response = self._call()
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["database"] == "ok"
        assert response.json()["migration"] == "head"

    def test_database_unavailable_503(self) -> None:
        with (
            patch("backend.routers.health.settings", self._settings()),
            patch(
                "backend.services.dataset_service.dataset_store.ready",
                return_value=False,
            ),
        ):
            response = self._call()
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"
        assert response.json()["database"] == "error"

    def test_migration_behind_503(self) -> None:
        with (
            patch("backend.routers.health.settings", self._settings()),
            patch(
                "backend.services.dataset_service.dataset_store.ready",
                return_value=True,
            ),
            patch("backend.routers.health._alembic_head", return_value="aeb4cbb3b3b2"),
            patch("backend.routers.health._current_revision", return_value="old-rev"),
        ):
            response = self._call()
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"
        assert response.json()["migration"] == "behind"

    def test_database_ready_redis_degraded(self) -> None:
        with (
            patch("backend.routers.health.settings", self._settings()),
            patch(
                "backend.services.dataset_service.dataset_store.ready",
                return_value=True,
            ),
            patch("backend.routers.health._alembic_head", return_value="aeb4cbb3b3b2"),
            patch(
                "backend.routers.health._current_revision", return_value="aeb4cbb3b3b2"
            ),
            patch(
                "backend.services.cache_service.cache_service.ready", return_value=False
            ),
        ):
            response = self._call()
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
        assert response.json()["redis"] == "degraded"
        assert response.json()["migration"] == "head"

    def test_migration_check_failure_503(self) -> None:
        with (
            patch("backend.routers.health.settings", self._settings()),
            patch(
                "backend.services.dataset_service.dataset_store.ready",
                return_value=True,
            ),
            patch(
                "backend.routers.health._alembic_head",
                side_effect=RuntimeError("alembic broken"),
            ),
        ):
            response = self._call()
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"


if __name__ == "__main__":
    unittest.main()
