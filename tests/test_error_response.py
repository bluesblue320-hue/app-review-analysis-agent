"""Tasks 8+9: ENABLE_DOCS toggle and uniform error responses with request_id.

Verifies every error class (401, 404, 422, AppError, 500) returns a body
whose request_id matches the X-Request-ID header, and that ENABLE_DOCS
actually controls /docs, /redoc and /openapi.json.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app


class TestErrorResponseRequestId(unittest.TestCase):
    def _client(self):
        return TestClient(app)

    def _check_request_id(self, response) -> str:
        header_id = response.headers.get("X-Request-ID", "")
        assert header_id, "missing X-Request-ID header"
        body_id = response.json().get("request_id", "")
        assert body_id == header_id, "body request_id != header X-Request-ID"
        return body_id

    def test_401_unauthorized(self) -> None:
        # With a configured access token, a missing/invalid token is rejected.
        with patch("backend.core.middleware.settings") as mock_settings:
            mock_settings.access_token = "configured-token"
            mock_settings.api_prefix = "/api/v1"
            response = self._client().get(
                "/api/v1/datasets/x", headers={"Authorization": "Bearer wrong"}
            )
        assert response.status_code == 401
        self._check_request_id(response)
        assert response.json()["error"]["code"] == "unauthorized"

    def test_404_not_found(self) -> None:
        response = self._client().get("/api/v1/does-not-exist")
        assert response.status_code == 404
        self._check_request_id(response)
        assert response.json()["error"]["code"] == "http_error"

    def test_422_validation_error(self) -> None:
        with patch("backend.core.middleware.settings") as mock_settings:
            mock_settings.access_token = ""
            mock_settings.api_prefix = "/api/v1"
            response = self._client().post(
                "/api/v1/analytics/summary", json={"filters": "not-a-dict"}
            )
        assert response.status_code == 422
        self._check_request_id(response)
        assert response.json()["error"]["code"] == "validation_error"

    def test_app_error_has_request_id(self) -> None:
        with patch("backend.core.middleware.settings") as mock_settings:
            mock_settings.access_token = ""
            mock_settings.api_prefix = "/api/v1"
            response = self._client().post(
                "/api/v1/analytics/summary",
                json={"dataset_id": "missing-dataset", "filters": {}},
            )
        # Unknown dataset raises AppError (dataset_not_found, 404).
        assert response.status_code == 404
        self._check_request_id(response)
        assert response.json()["error"]["code"] == "dataset_not_found"

    def test_500_internal_error_hides_details(self) -> None:
        # Force an unhandled exception via a route that always raises.
        from backend.main import app as application

        @application.get("/api/v1/_boom", include_in_schema=False)
        def _boom():
            raise RuntimeError("secret internal detail")

        client = TestClient(application, raise_server_exceptions=False)
        with patch("backend.core.middleware.settings") as mock_settings:
            mock_settings.access_token = ""
            mock_settings.api_prefix = "/api/v1"
            response = client.get("/api/v1/_boom")
        assert response.status_code == 500
        self._check_request_id(response)
        body = response.json()
        assert body["error"]["code"] == "internal_error"
        assert "secret internal detail" not in response.text

    def test_404_without_route_still_has_request_id(self) -> None:
        response = self._client().get("/api/v1/unknown-route-xyz")
        assert response.status_code == 404
        self._check_request_id(response)


class TestEnableDocsToggle(unittest.TestCase):
    def _reloaded_app(self, enable_docs: bool):
        from unittest.mock import MagicMock

        import backend.main as main_module
        from backend.core.config import Settings

        base = Settings()
        mock_settings = MagicMock()
        mock_settings.enable_docs = enable_docs
        mock_settings.api_prefix = base.api_prefix
        with patch("backend.core.config.settings", mock_settings):
            import importlib

            reloaded = importlib.reload(main_module)
            return reloaded.app

    def test_docs_disabled_hides_all_doc_urls(self) -> None:
        app = self._reloaded_app(enable_docs=False)
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404

    def test_docs_enabled_serves_docs(self) -> None:
        app = self._reloaded_app(enable_docs=True)
        assert app.docs_url == "/docs"
        assert app.openapi_url == "/openapi.json"


if __name__ == "__main__":
    unittest.main()
