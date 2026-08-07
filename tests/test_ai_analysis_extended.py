"""Extended coverage tests for ai_analysis error paths and helpers."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests

import ai_analysis
from tests.test_ai_analysis import FakeResponse


class AiAnalysisExtendedTests(unittest.TestCase):
    def test_load_env_file_reads_keys_and_skips_comments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                '# comment\n\nAI_PROVIDER=deepseek\nDEEPSEEK_API_KEY="sk-123"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                ai_analysis.load_env_file(str(env_file))
                self.assertEqual(os.environ.get("DEEPSEEK_API_KEY"), "sk-123")

    def test_load_env_file_missing_file_is_noop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                ai_analysis.load_env_file(str(Path(tmpdir) / "absent.env"))
                self.assertNotIn("DEEPSEEK_API_KEY", os.environ)

    def test_load_env_file_keeps_existing_env_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("AI_PROVIDER=openai\n", encoding="utf-8")
            with patch.dict(os.environ, {"AI_PROVIDER": "deepseek"}, clear=False):
                ai_analysis.load_env_file(str(env_file))
                self.assertEqual(os.environ["AI_PROVIDER"], "deepseek")

    def test_parse_json_content_extracts_embedded_object(self):
        parsed = ai_analysis.parse_json_content('前缀 {"summary": "嵌入"} 后缀')
        self.assertEqual(parsed["summary"], "嵌入")

    def test_parse_json_content_raises_on_invalid_json(self):
        with self.assertRaises(ai_analysis.AiAnalysisError):
            ai_analysis.parse_json_content("完全不是 JSON")

    def test_as_list_normalizes_scalars_and_none(self):
        self.assertEqual(ai_analysis._as_list("item"), ["item"])
        self.assertEqual(ai_analysis._as_list(None), [])
        self.assertEqual(ai_analysis._as_list(["a", "b"]), ["a", "b"])

    def test_normalize_insights_raises_on_non_dict(self):
        with self.assertRaises(ai_analysis.AiAnalysisError):
            ai_analysis.normalize_insights("not a dict")

    def test_build_review_packet_missing_columns_raises(self):
        df = pd.DataFrame([{"评分": 1}])
        with self.assertRaises(ai_analysis.AiAnalysisError):
            ai_analysis.build_review_packet(df)

    def test_build_review_packet_empty_after_clean_raises(self):
        df = pd.DataFrame([{"评分": None, "内容": ""}])
        with self.assertRaises(ai_analysis.AiAnalysisError):
            ai_analysis.build_review_packet(df)

    def test_build_review_packet_with_sentiment_mismatch(self):
        df = pd.DataFrame(
            [
                {"评分": 5, "内容": "高星低情绪", "情绪指数": 10},
                {"评分": 4, "内容": "还行", "情绪指数": 60},
                {"评分": 1, "内容": "差", "情绪指数": 5},
                {"评分": 5, "内容": "很好", "情绪指数": 90},
            ]
        )
        packet = ai_analysis.build_review_packet(df, max_reviews=4)
        self.assertIn("average_sentiment", packet["metrics"])
        self.assertEqual(packet["metrics"]["total_reviews"], 4)

    def test_build_review_packet_sentiment_column_without_values(self):
        df = pd.DataFrame([{"评分": 1, "内容": "差", "情绪指数": "abc"}])
        packet = ai_analysis.build_review_packet(df)
        self.assertNotIn("average_sentiment", packet["metrics"])

    def test_call_deepseek_rejects_wrong_provider(self):
        with self.assertRaises(ai_analysis.AiAnalysisError):
            ai_analysis.call_deepseek(
                [],
                {"provider": "openai", "api_key": "k", "base_url": "u", "model": "m"},
            )

    def test_call_deepseek_rejects_missing_key(self):
        with self.assertRaises(ai_analysis.AiAnalysisError):
            ai_analysis.call_deepseek(
                [],
                {"provider": "deepseek", "api_key": "", "base_url": "u", "model": "m"},
            )

    def test_call_deepseek_wraps_request_failure(self):
        def failing_post(*args, **kwargs):
            raise requests.exceptions.ConnectionError("offline")

        with self.assertRaises(ai_analysis.AiAnalysisError):
            ai_analysis.call_deepseek(
                [{"role": "user", "content": "x"}],
                {"provider": "deepseek", "api_key": "k", "base_url": "u", "model": "m"},
                post_func=failing_post,
            )

    def test_call_deepseek_raises_on_non_200(self):
        def bad_status_post(*args, **kwargs):
            return FakeResponse(status_code=500)

        with self.assertRaises(ai_analysis.AiAnalysisError):
            ai_analysis.call_deepseek(
                [],
                {"provider": "deepseek", "api_key": "k", "base_url": "u", "model": "m"},
                post_func=bad_status_post,
            )

    def test_call_deepseek_raises_on_malformed_response(self):
        def malformed_post(*args, **kwargs):
            return FakeResponse(payload={"choices": []})

        with self.assertRaises(ai_analysis.AiAnalysisError):
            ai_analysis.call_deepseek(
                [],
                {"provider": "deepseek", "api_key": "k", "base_url": "u", "model": "m"},
                post_func=malformed_post,
            )

    def test_call_deepseek_returns_content_on_success(self):
        def ok_post(*args, **kwargs):
            return FakeResponse(
                payload={"choices": [{"message": {"content": '{"a": 1}'}}]}
            )

        content = ai_analysis.call_deepseek(
            [],
            {"provider": "deepseek", "api_key": "k", "base_url": "u", "model": "m"},
            post_func=ok_post,
        )
        self.assertEqual(content, '{"a": 1}')

    def test_analyze_reviews_full_pipeline(self):
        def ok_post(*args, **kwargs):
            return FakeResponse(
                payload={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "summary": "整体偏负面",
                                        "pain_points": ["封号"],
                                        "recommendations": [],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            )

        df = pd.DataFrame([{"评分": 1, "内容": "无故封号"}])
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "sk-test", "AI_PROVIDER": "deepseek"},
            clear=True,
        ):
            insights = ai_analysis.analyze_reviews(df, post_func=ok_post)
        self.assertEqual(insights["summary"], "整体偏负面")
        self.assertEqual(insights["pain_points"], ["封号"])
