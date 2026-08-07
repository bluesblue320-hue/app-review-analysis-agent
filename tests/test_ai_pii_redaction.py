"""Task 2: PII redaction at the external-model request boundary.

Verifies the actual JSON payload sent to the model (captured via a fake
post_func) contains no raw phone numbers, emails, CN ID cards or bank cards.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

import pandas as pd

import ai_analysis
from backend.core.privacy import (
    BANK_CARD_PLACEHOLDER,
    CN_ID_PLACEHOLDER,
    EMAIL_PLACEHOLDER,
    PHONE_PLACEHOLDER,
    redact_recursive,
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.status_code = status_code
        self._payload = payload or {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"summary": "ok", "pain_points": []},
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

    def json(self):
        return self._payload


class TestRedactRecursive(unittest.TestCase):
    def test_recurses_dict_list_tuple_and_keeps_numbers(self):
        source = {
            "metrics": {"total_reviews": 3, "average_rating": 2.5},
            "reviews": [
                {
                    "内容": "电话13800138000 邮箱a@b.com 身份证110101199003078888 卡6222021234567890123",
                    "评分": 1,
                    "tags": ("联系人", "13812345678"),
                }
            ],
            "active": True,
            "none_value": None,
        }
        redacted = redact_recursive(source)
        assert redacted["metrics"] == {"total_reviews": 3, "average_rating": 2.5}
        assert redacted["active"] is True
        assert redacted["none_value"] is None
        assert PHONE_PLACEHOLDER in redacted["reviews"][0]["内容"]
        assert EMAIL_PLACEHOLDER in redacted["reviews"][0]["内容"]
        assert CN_ID_PLACEHOLDER in redacted["reviews"][0]["内容"]
        assert BANK_CARD_PLACEHOLDER in redacted["reviews"][0]["内容"]
        assert "13800138000" not in redacted["reviews"][0]["内容"]
        assert redacted["reviews"][0]["tags"][1] == PHONE_PLACEHOLDER
        assert redacted["reviews"][0]["评分"] == 1

    def test_non_container_leaves_pass_through(self):
        assert redact_recursive(42) == 42
        assert redact_recursive(3.14) == 3.14
        assert redact_recursive(True) is True
        assert redact_recursive(None) is None


class TestAiInsightsPayloadRedaction(unittest.TestCase):
    def test_model_request_payload_contains_no_raw_pii(self):
        df = pd.DataFrame(
            [
                {
                    "评分": 1,
                    "内容": "联系我 13800138000 或 user@example.com，身份证 110101199003078888",
                    "版本": "2.0.0",
                    "时间": "2026-07-01",
                },
                {
                    "评分": 5,
                    "内容": "银行卡 6222021234567890123 有问题",
                    "版本": "2.0.0",
                    "时间": "2026-07-02",
                },
            ]
        )
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["json"] = json
            return FakeResponse()

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            ai_analysis.analyze_reviews(df, post_func=fake_post)

        payload_text = json.dumps(captured["json"], ensure_ascii=False)
        assert "13800138000" not in payload_text
        assert "user@example.com" not in payload_text
        assert "110101199003078888" not in payload_text
        assert "6222021234567890123" not in payload_text
        assert PHONE_PLACEHOLDER in payload_text
        assert EMAIL_PLACEHOLDER in payload_text
        assert CN_ID_PLACEHOLDER in payload_text
        assert BANK_CARD_PLACEHOLDER in payload_text

    def test_metrics_numbers_unchanged_in_payload(self):
        df = pd.DataFrame(
            [
                {"评分": 1, "内容": "差评 13800138000"},
                {"评分": 5, "内容": "好评"},
                {"评分": 3, "内容": "中评"},
            ]
        )
        captured = {}

        def fake_post(url, headers, json, timeout):
            captured["json"] = json
            return FakeResponse()

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            ai_analysis.analyze_reviews(df, post_func=fake_post)

        messages = captured["json"]["messages"]
        user_content = json.loads(messages[1]["content"])
        metrics = user_content["review_packet"]["metrics"]
        assert metrics["total_reviews"] == 3
        assert metrics["average_rating"] == 3.0
        assert PHONE_PLACEHOLDER in messages[1]["content"]


if __name__ == "__main__":
    unittest.main()
