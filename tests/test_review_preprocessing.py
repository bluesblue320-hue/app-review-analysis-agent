import unittest

import pandas as pd

import review_fields
import review_preprocessing
import visual_analysis


class _FixedSentimentAnalyzer:
    def __init__(self, text):
        self.text = text
        self.sentiments = 0.81234


class ReviewPreprocessingTests(unittest.TestCase):
    def test_shared_field_constants_remain_available_from_visual_analysis(self):
        self.assertEqual(visual_analysis.RATING_COLUMN, review_fields.RATING_COLUMN)
        self.assertEqual(visual_analysis.CONTENT_COLUMN, review_fields.CONTENT_COLUMN)
        self.assertEqual(visual_analysis.SENTIMENT_COLUMN, review_fields.SENTIMENT_COLUMN)
        self.assertEqual(visual_analysis.CATEGORY_COLUMN, review_fields.CATEGORY_COLUMN)
        self.assertEqual(visual_analysis.RISK_LABEL_COLUMN, review_fields.RISK_LABEL_COLUMN)

    def test_clean_and_tokenize_preserves_existing_text_policy(self):
        result = review_preprocessing.clean_and_tokenize(
            "小红书软件非常不错，账号登录后一直闪退 123"
        )

        self.assertNotIn("小红书", result)
        self.assertNotIn("软件", result)
        self.assertNotIn("123", result)
        self.assertIn("闪退", result)

    def test_calculate_sentiment_uses_existing_zero_to_one_hundred_scale(self):
        score = review_preprocessing.calculate_sentiment(
            "测试评论",
            analyzer_factory=_FixedSentimentAnalyzer,
        )

        self.assertEqual(score, 81.23)

    def test_expected_sentiment_error_is_logged_and_uses_neutral_fallback(self):
        def invalid_analyzer(text):
            raise ValueError("invalid sentiment input")

        with self.assertLogs("review_preprocessing", level="WARNING") as logs:
            score = review_preprocessing.calculate_sentiment(
                "异常评论",
                analyzer_factory=invalid_analyzer,
            )

        self.assertEqual(score, 50.0)
        self.assertIn("error_type=ValueError", logs.output[0])
        self.assertNotIn("异常评论", logs.output[0])

    def test_unexpected_sentiment_error_is_not_silently_swallowed(self):
        def broken_analyzer(text):
            raise RuntimeError("programming error")

        with self.assertRaises(RuntimeError):
            review_preprocessing.calculate_sentiment(
                "测试评论",
                analyzer_factory=broken_analyzer,
            )

    def test_preprocess_reviews_adds_columns_without_mutating_source(self):
        source = pd.DataFrame([{"评分": 5, "内容": "搜索内容丰富"}])

        processed = review_preprocessing.preprocess_reviews(source)

        self.assertNotIn(review_fields.TOKEN_COLUMN, source.columns)
        self.assertNotIn(review_fields.SENTIMENT_COLUMN, source.columns)
        self.assertIn(review_fields.TOKEN_COLUMN, processed.columns)
        self.assertIn(review_fields.SENTIMENT_COLUMN, processed.columns)

    def test_preprocess_reviews_rejects_missing_content_column(self):
        with self.assertRaisesRegex(ValueError, "缺少必要列：内容"):
            review_preprocessing.preprocess_reviews(pd.DataFrame([{"评分": 5}]))


if __name__ == "__main__":
    unittest.main()
