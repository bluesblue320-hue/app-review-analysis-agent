import unittest

import pandas as pd

import visual_analysis


class VisualAnalysisTests(unittest.TestCase):
    def make_reviews(self):
        return pd.DataFrame(
            [
                {
                    "评分": 1,
                    "内容": "无故封号，申诉没人处理，客服也找不到",
                    "情绪指数": 8,
                },
                {"评分": 1, "内容": "账号被封，人工客服一直没有回复", "情绪指数": 12},
                {"评分": 2, "内容": "审核太严格，笔记莫名违规", "情绪指数": 25},
                {"评分": 3, "内容": "广告太多，推荐质量下降", "情绪指数": 45},
                {"评分": 5, "内容": "内容很多，种草体验不错", "情绪指数": 86},
                {"评分": 4, "内容": "高分但是广告真的太多了", "情绪指数": 22},
            ]
        )

    def test_prepare_dashboard_data_adds_category_and_risk_label(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())

        self.assertIn("问题类型", prepared.columns)
        self.assertIn("风险标签", prepared.columns)
        self.assertEqual(prepared.iloc[0]["问题类型"], "账号类")
        self.assertIn("极端负面", prepared.iloc[0]["风险标签"])
        self.assertIn("高星低情绪", prepared.iloc[5]["风险标签"])

    def test_calculate_health_metrics_counts_core_values(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())

        metrics = visual_analysis.calculate_health_metrics(prepared)

        self.assertEqual(metrics["total_reviews"], 6)
        self.assertEqual(metrics["average_rating"], 2.67)
        self.assertEqual(metrics["negative_ratio"], 66.67)
        self.assertEqual(metrics["average_sentiment"], 33.0)
        self.assertEqual(metrics["high_risk_count"], 4)

    def test_filter_reviews_by_rating_sentiment_category_keyword_and_risk(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())

        filtered = visual_analysis.filter_reviews(
            prepared,
            rating_range=(1, 2),
            sentiment_range=(0, 30),
            categories=["账号类"],
            keyword="客服",
            high_risk_only=True,
        )

        self.assertEqual(len(filtered), 2)
        self.assertTrue((filtered["问题类型"] == "账号类").all())
        self.assertTrue(filtered["内容"].str.contains("客服").all())

    def test_filter_reviews_empty_categories_returns_no_rows(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())

        filtered = visual_analysis.filter_reviews(prepared, categories=[])

        self.assertTrue(filtered.empty)

    def test_empty_data_returns_safe_metrics(self):
        empty = pd.DataFrame(columns=["评分", "内容", "情绪指数"])
        prepared = visual_analysis.prepare_dashboard_data(empty)

        metrics = visual_analysis.calculate_health_metrics(prepared)

        self.assertEqual(metrics["total_reviews"], 0)
        self.assertEqual(metrics["average_rating"], 0.0)
        self.assertEqual(metrics["negative_ratio"], 0.0)
        self.assertEqual(metrics["average_sentiment"], 0.0)
        self.assertEqual(metrics["high_risk_count"], 0)

    def test_calculate_priority_table_ranks_severe_account_problem_first(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())
        insights = {
            "pain_points": [
                {
                    "name": "账号封号申诉困难",
                    "severity": "high",
                    "suggestion": "优先处理账号封禁和申诉链路。",
                }
            ]
        }

        priority = visual_analysis.calculate_priority_table(
            prepared, ai_insights=insights, top_n=3
        )

        self.assertEqual(priority.iloc[0]["问题类型"], "账号类")
        self.assertGreater(
            priority.iloc[0]["优先级分数"], priority.iloc[1]["优先级分数"]
        )
        self.assertEqual(priority.iloc[0]["严重程度"], "high")
        self.assertIn("封号", priority.iloc[0]["代表评论"])

    def test_calculate_priority_table_merges_ai_severity_and_suggestion(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())
        insights = {
            "pain_points": [
                {
                    "name": "广告过多",
                    "severity": "high",
                    "suggestion": "降低信息流广告密度，优先检查推荐页体验。",
                }
            ]
        }

        priority = visual_analysis.calculate_priority_table(
            prepared, ai_insights=insights, top_n=5
        )
        experience = priority[priority["问题类型"] == "体验类"].iloc[0]

        self.assertGreaterEqual(experience["AI严重度"], 100)
        self.assertEqual(
            experience["AI建议"], "降低信息流广告密度，优先检查推荐页体验。"
        )

    def test_calculate_priority_table_ignores_malformed_ai_insights(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())

        string_priority = visual_analysis.calculate_priority_table(
            prepared,
            ai_insights="bad output",
        )
        malformed_pain_points_priority = visual_analysis.calculate_priority_table(
            prepared,
            ai_insights={"pain_points": "bad"},
        )

        self.assertFalse(string_priority.empty)
        self.assertFalse(malformed_pain_points_priority.empty)

    def test_rating_and_sentiment_distribution_are_chart_ready(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())

        rating = visual_analysis.rating_distribution(prepared)
        sentiment = visual_analysis.sentiment_distribution(prepared)

        self.assertEqual(list(rating.columns), ["评分", "评论数"])
        self.assertEqual(int(rating["评论数"].sum()), 6)
        self.assertEqual(list(sentiment.columns), ["情绪区间", "评论数"])
        self.assertEqual(int(sentiment["评论数"].sum()), 6)

    def test_sentiment_scatter_data_keeps_required_columns(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())

        scatter = visual_analysis.sentiment_scatter_data(prepared)

        self.assertEqual(
            list(scatter.columns),
            ["评分", "情绪指数", "问题类型", "风险标签", "内容"],
        )

    def test_extract_keyword_scores_returns_top_words(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())
        prepared["分词内容"] = [
            "封号 申诉 客服",
            "账号 封号 客服",
            "审核 违规 笔记",
            "广告 推荐 质量",
            "内容 种草 体验",
            "广告 推荐",
        ]

        keywords = visual_analysis.extract_keyword_scores(prepared["分词内容"], top_n=3)

        self.assertEqual(list(keywords.columns), ["关键词", "权重"])
        self.assertEqual(len(keywords), 3)

    def test_extract_keyword_scores_returns_empty_for_empty_vocabulary(self):
        cases = [
            pd.Series(["好 差 卡"]),
            pd.Series(["！！！"]),
            pd.Series(["a b c"]),
        ]

        for text_series in cases:
            with self.subTest(text_series=text_series.tolist()):
                keywords = visual_analysis.extract_keyword_scores(text_series)

                self.assertEqual(list(keywords.columns), ["关键词", "权重"])
                self.assertTrue(keywords.empty)

    def test_sentiment_trend_skips_when_time_column_missing(self):
        prepared = visual_analysis.prepare_dashboard_data(self.make_reviews())

        trend = visual_analysis.sentiment_trend(prepared)

        self.assertTrue(trend.empty)


if __name__ == "__main__":
    unittest.main()
