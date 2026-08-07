import unittest

from intent_router import detect_intent


class DetectIntentTests(unittest.TestCase):
    def test_routes_negative_review_question(self):
        self.assertEqual(
            detect_intent("差评主要集中在哪些问题？"), "negative_review_analysis"
        )

    def test_routes_risk_review_question(self):
        self.assertEqual(
            detect_intent("哪些评论需要人工优先处理？"), "risk_review_analysis"
        )

    def test_routes_positive_review_question(self):
        self.assertEqual(
            detect_intent("用户最喜欢哪些功能？"), "positive_review_analysis"
        )

    def test_routes_version_question(self):
        self.assertEqual(detect_intent("哪个版本问题最多？"), "version_analysis")

    def test_routes_trend_question(self):
        self.assertEqual(detect_intent("最近评分趋势有没有下降？"), "trend_analysis")

    def test_routes_product_suggestion_question(self):
        self.assertEqual(detect_intent("帮我生成产品优化建议。"), "product_suggestion")

    def test_routes_report_generation_question(self):
        self.assertEqual(
            detect_intent("帮我生成一份评论分析报告。"), "report_generation"
        )

    def test_routes_empty_question_to_general_analysis(self):
        self.assertEqual(detect_intent(""), "general_analysis")

    def test_routes_unknown_question_to_general_analysis(self):
        self.assertEqual(detect_intent("今天天气怎么样？"), "general_analysis")

    def test_prioritizes_risk_over_negative_review(self):
        self.assertEqual(
            detect_intent("严重差评里哪些需要人工优先处理？"),
            "risk_review_analysis",
        )


if __name__ == "__main__":
    unittest.main()
