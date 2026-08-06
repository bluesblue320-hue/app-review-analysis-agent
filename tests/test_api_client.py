import unittest
from unittest.mock import Mock

import requests

from frontend.api_client import (
    ApiResponseError,
    ApiTimeoutError,
    BackendApiClient,
    BackendUnavailableError,
    InvalidApiResponseError,
)


class BackendApiClientTests(unittest.TestCase):
    def make_client(self):
        session = Mock()
        return BackendApiClient(
            "http://backend.test/",
            timeout=12,
            session=session,
        ), session

    @staticmethod
    def response(status_code=200, payload=None):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = payload if payload is not None else {}
        return response

    def test_summary_request_returns_json_and_sends_filters(self):
        client, session = self.make_client()
        session.request.return_value = self.response(
            payload={"sample_size": 3, "scope_signature": "abc"}
        )
        filters = {"rating_min": 1, "rating_max": 3}

        result = client.get_summary("dataset_1", filters)

        self.assertEqual(result["sample_size"], 3)
        session.request.assert_called_once_with(
            "POST",
            "http://backend.test/api/v1/analytics/summary",
            timeout=12,
            json={
                "dataset_id": "dataset_1",
                "filters": filters,
            },
        )

    def test_summary_sends_only_server_insight_id(self):
        client, session = self.make_client()
        session.request.return_value = self.response(payload={"sample_size": 3})

        client.get_summary("dataset_1", {}, insight_id="insight_1")

        payload = session.request.call_args.kwargs["json"]
        self.assertEqual(
            payload,
            {
                "dataset_id": "dataset_1",
                "filters": {},
                "insight_id": "insight_1",
            },
        )
        self.assertNotIn("ai_insights", payload)
        self.assertNotIn("ai_scope_signature", payload)

    def test_agent_sends_only_server_insight_id(self):
        client, session = self.make_client()
        session.request.return_value = self.response(payload={"answer": "ok"})

        client.query_agent(
            dataset_id="dataset_1",
            question="差评问题",
            filters={},
            scope="full",
            insight_id="insight_1",
        )

        payload = session.request.call_args.kwargs["json"]
        self.assertEqual(payload["insight_id"], "insight_1")
        self.assertNotIn("ai_insights", payload)
        self.assertNotIn("ai_scope_signature", payload)

    def test_upload_uses_multipart_file(self):
        client, session = self.make_client()
        session.request.return_value = self.response(
            payload={"dataset_id": "dataset_1"}
        )

        result = client.upload_dataset("reviews.csv", b"csv-content")

        self.assertEqual(result["dataset_id"], "dataset_1")
        files = session.request.call_args.kwargs["files"]
        self.assertEqual(files["file"], ("reviews.csv", b"csv-content", "text/csv"))

    def test_timeout_has_specific_error(self):
        client, session = self.make_client()
        session.request.side_effect = requests.Timeout("slow backend")

        with self.assertRaisesRegex(ApiTimeoutError, "12 秒"):
            client.health()

    def test_connection_failure_has_friendly_error(self):
        client, session = self.make_client()
        session.request.side_effect = requests.ConnectionError("connection refused")

        with self.assertRaisesRegex(BackendUnavailableError, "FastAPI 已启动"):
            client.health()

    def test_non_200_uses_backend_error_message(self):
        client, session = self.make_client()
        session.request.return_value = self.response(
            status_code=404,
            payload={
                "error": {
                    "code": "dataset_not_found",
                    "message": "数据集不存在",
                }
            },
        )

        with self.assertRaises(ApiResponseError) as context:
            client.get_summary("dataset_missing", {})

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.code, "dataset_not_found")
        self.assertEqual(str(context.exception), "数据集不存在")

    def test_success_with_invalid_json_is_rejected(self):
        client, session = self.make_client()
        response = self.response(status_code=200)
        response.json.side_effect = ValueError("invalid json")
        session.request.return_value = response

        with self.assertRaisesRegex(InvalidApiResponseError, "无法解析的 JSON"):
            client.health()

    def test_success_with_non_object_json_is_rejected(self):
        client, session = self.make_client()
        session.request.return_value = self.response(payload=["not", "an", "object"])

        with self.assertRaisesRegex(InvalidApiResponseError, "必须是对象"):
            client.health()


if __name__ == "__main__":
    unittest.main()
