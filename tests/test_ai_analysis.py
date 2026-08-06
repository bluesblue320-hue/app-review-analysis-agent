import json
import os
import unittest
from unittest.mock import patch

import pandas as pd

import ai_analysis


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload, ensure_ascii=False)

    def json(self):
        return self._payload


class AiAnalysisTests(unittest.TestCase):
    def test_load_config_defaults_to_deepseek_flash(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            config = ai_analysis.load_ai_config()

        self.assertEqual(config["provider"], "deepseek")
        self.assertEqual(config["model"], "deepseek-v4-flash")
        self.assertEqual(config["api_key"], "sk-test")

    def test_parse_json_content_tolerates_markdown_fences(self):
        parsed = ai_analysis.parse_json_content('```json\n{"summary": "稳定"}\n```')

        self.assertEqual(parsed["summary"], "稳定")

    def test_normalize_insights_fills_missing_sections(self):
        normalized = ai_analysis.normalize_insights({"summary": "整体偏负面"})

        self.assertEqual(normalized["summary"], "整体偏负面")
        self.assertEqual(normalized["pain_points"], [])
        self.assertEqual(normalized["recommendations"], [])

    def test_build_review_packet_keeps_representative_reviews(self):
        df = pd.DataFrame(
            [
                {"评分": 1, "内容": "总是无故封号，客服也找不到"},
                {"评分": 5, "内容": "内容很多，种草体验不错"},
                {"评分": 4, "内容": "高分但是广告太多"},
            ]
        )

        packet = ai_analysis.build_review_packet(df, max_reviews=2)

        self.assertEqual(packet["metrics"]["total_reviews"], 3)
        self.assertEqual(packet["metrics"]["average_rating"], 3.33)
        self.assertLessEqual(len(packet["reviews"]), 2)
        self.assertIn("评分", packet["reviews"][0])
        self.assertIn("内容", packet["reviews"][0])

    def test_analyze_reviews_posts_deepseek_payload_and_normalizes_response(self):
        df = pd.DataFrame([{"评分": 1, "内容": "无故封号，申诉没人理"}])
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "用户主要抱怨账号治理。",
                                "pain_points": [{"name": "账号封禁"}],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

        calls = []

        def fake_post(url, headers, json, timeout):
            calls.append(
                {"url": url, "headers": headers, "json": json, "timeout": timeout}
            )
            return FakeResponse(payload=payload)

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            result = ai_analysis.analyze_reviews(df, post_func=fake_post)

        self.assertEqual(result["summary"], "用户主要抱怨账号治理。")
        self.assertEqual(result["pain_points"][0]["name"], "账号封禁")
        self.assertEqual(calls[0]["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(calls[0]["json"]["model"], "deepseek-v4-flash")
        self.assertEqual(calls[0]["json"]["response_format"], {"type": "json_object"})

    def test_deepseek_error_does_not_expose_upstream_response_body(self):
        response = FakeResponse(status_code=401, text="secret upstream detail")
        config = {
            "provider": "deepseek",
            "model": "test-model",
            "api_key": "sk-secret",
            "base_url": "https://example.invalid/chat",
        }

        with self.assertRaises(ai_analysis.AiAnalysisError) as context:
            ai_analysis.call_deepseek(
                [],
                config,
                post_func=lambda *args, **kwargs: response,
            )

        self.assertIn("401", str(context.exception))
        self.assertNotIn("secret upstream detail", str(context.exception))
        self.assertNotIn("sk-secret", str(context.exception))


if __name__ == "__main__":
    unittest.main()
