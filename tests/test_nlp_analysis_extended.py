"""Extended coverage for nlp_analysis offline CLI helpers and error paths."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

import nlp_analysis


class NlpAnalysisExtendedTests(unittest.TestCase):
    def test_register_forced_words_adds_domain_phrases(self):
        with patch.object(nlp_analysis.jieba, "add_word") as add_word:
            nlp_analysis.register_forced_words()
        self.assertGreaterEqual(add_word.call_count, len(nlp_analysis.FORCED_WORDS))

    def test_advanced_clean_and_cut_returns_token_string(self):
        result = nlp_analysis.advanced_clean_and_cut("人工客服 回复太慢")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result.strip(), "")

    def test_extract_top_keywords_empty_series(self):
        keywords = nlp_analysis.extract_top_keywords(pd.Series([], dtype="object"))
        self.assertIsInstance(keywords, list)

    def test_load_reviews_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            nlp_analysis._load_reviews("definitely_not_there.csv")

    def test_load_reviews_empty_data_raises_value_error(self):
        class EmptyReader:
            def __call__(self, *args, **kwargs):
                raise pd.errors.EmptyDataError("empty")

        with patch.object(nlp_analysis.pd, "read_csv", EmptyReader()):
            with self.assertRaises(ValueError):
                nlp_analysis._load_reviews("anything.csv")

    def test_load_reviews_parser_error_raises_value_error(self):
        class BadReader:
            def __call__(self, *args, **kwargs):
                raise pd.errors.ParserError("parse")

        with patch.object(nlp_analysis.pd, "read_csv", BadReader()):
            with self.assertRaises(ValueError):
                nlp_analysis._load_reviews("anything.csv")

    def test_load_reviews_returns_dataframe_on_success(self):
        df = pd.DataFrame(
            [
                {"评分": 1, "内容": "封号", "版本": "2.0.0", "时间": "2026-07-01"},
            ]
        )
        with patch.object(nlp_analysis.pd, "read_csv", return_value=df):
            loaded = nlp_analysis._load_reviews("anything.csv")
        self.assertEqual(len(loaded), 1)

    def test_render_wordclouds_writes_both_files(self):
        keywords = [("封号", 0.9), ("客服", 0.7)]
        with (
            patch.object(nlp_analysis, "WordCloud") as mock_cloud_class,
            patch.object(nlp_analysis, "opts"),
        ):
            instance = mock_cloud_class.return_value
            instance.add.return_value = instance
            instance.set_global_opts.return_value = instance
            nlp_analysis._render_wordclouds(keywords, keywords)
        self.assertEqual(instance.render.call_count, 2)

    def test_main_success_writes_output(self):
        df = pd.DataFrame(
            [
                {
                    "评分": 1,
                    "内容": "无故封号客服不回",
                    "版本": "2.0.0",
                    "时间": "2026-07-01",
                },
                {
                    "评分": 5,
                    "内容": "内容丰富非常好用",
                    "版本": "1.9.0",
                    "时间": "2026-07-02",
                },
            ]
        )
        with (
            patch.object(nlp_analysis.pd.DataFrame, "to_csv", return_value=None),
            patch.object(nlp_analysis, "_load_reviews", return_value=df),
            patch.object(nlp_analysis, "register_forced_words"),
            patch.object(
                nlp_analysis, "extract_top_keywords", return_value=[("封号", 0.9)]
            ),
            patch.object(nlp_analysis, "_render_wordclouds"),
        ):
            exit_code = nlp_analysis.main()
        self.assertEqual(exit_code, 0)

    def test_main_missing_file_returns_one(self):
        def raising_load(path):
            raise FileNotFoundError("找不到 CSV 文件")

        with patch.object(nlp_analysis, "_load_reviews", side_effect=raising_load):
            exit_code = nlp_analysis.main()
        self.assertEqual(exit_code, 1)

    def test_main_missing_columns_returns_one(self):
        def raising_load(path):
            raise ValueError("CSV 缺少必要列")

        with patch.object(nlp_analysis, "_load_reviews", side_effect=raising_load):
            exit_code = nlp_analysis.main()
        self.assertEqual(exit_code, 1)
