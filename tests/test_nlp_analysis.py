import importlib
import unittest
from unittest.mock import patch

import pandas as pd

import nlp_analysis


class NlpAnalysisTests(unittest.TestCase):
    def test_import_does_not_read_legacy_csv(self):
        with patch("pandas.read_csv") as read_csv:
            importlib.reload(nlp_analysis)

        read_csv.assert_not_called()

    def test_offline_short_text_keeps_neutral_sentiment_policy(self):
        self.assertEqual(nlp_analysis.calculate_sentiment("好"), 50.0)

    def test_offline_keywords_keep_bigram_support(self):
        keywords = nlp_analysis.extract_top_keywords(
            pd.Series(["人工 客服 回复", "人工 客服"]),
            top_n=10,
        )

        self.assertTrue(any(" " in word for word, _ in keywords))

    def test_load_reviews_rejects_missing_required_columns(self):
        with patch.object(
            nlp_analysis.pd,
            "read_csv",
            return_value=pd.DataFrame([{"内容": "只有评论"}]),
        ):
            with self.assertRaisesRegex(ValueError, "CSV 缺少必要列：评分"):
                nlp_analysis._load_reviews("reviews.csv")


if __name__ == "__main__":
    unittest.main()
