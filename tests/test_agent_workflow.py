import unittest

import pandas as pd

import agent_workflow
from visual_analysis import prepare_dashboard_data


class AgentWorkflowTests(unittest.TestCase):
    def make_reviews(self):
        raw = pd.DataFrame(
            [
                {
                    "评分": 1,
                    "内容": "无故封号，申诉没人处理，人工客服不回复",
                    "情绪指数": 8,
                    "分词内容": "封号 申诉 人工客服 回复",
                    "版本": "2.0.0",
                    "时间": "2026-07-01",
                },
                {
                    "评分": 2,
                    "内容": "更新后一直闪退，加载也很慢",
                    "情绪指数": 18,
                    "分词内容": "更新 闪退 加载",
                    "版本": "2.0.0",
                    "时间": "2026-07-02",
                },
                {
                    "评分": 3,
                    "内容": "广告太多，推荐质量下降",
                    "情绪指数": 40,
                    "分词内容": "广告 推荐 质量",
                    "版本": "1.9.0",
                    "时间": "2026-07-02",
                },
                {
                    "评分": 4,
                    "内容": "搜索内容丰富，使用方便",
                    "情绪指数": 78,
                    "分词内容": "搜索 内容 丰富 方便",
                    "版本": "1.9.0",
                    "时间": "2026-07-03",
                },
                {
                    "评分": 5,
                    "内容": "很喜欢社区内容和种草体验",
                    "情绪指数": 92,
                    "分词内容": "喜欢 社区 内容 种草 体验",
                    "版本": "1.9.0",
                    "时间": "2026-07-03",
                },
            ]
        )
        return prepare_dashboard_data(raw)

    def assert_result_shape(self, result, expected_intent):
        self.assertEqual(result["intent"], expected_intent)
        self.assertIsInstance(result["answer"], str)
        self.assertTrue(result["answer"])
        self.assertIsInstance(result["dataframes"], dict)

    def test_negative_workflow_returns_keywords_priority_and_examples(self):
        result = agent_workflow.run_negative_review_analysis("差评问题", self.make_reviews())

        self.assert_result_shape(result, "negative_review_analysis")
        self.assertEqual(
            set(result["dataframes"]),
            {"差评关键词", "问题优先级", "典型差评"},
        )
        self.assertLessEqual(result["dataframes"]["典型差评"].iloc[0]["评分"], 3)

    def test_risk_workflow_only_returns_non_normal_labels(self):
        result = agent_workflow.run_risk_review_analysis("高风险", self.make_reviews())

        self.assert_result_shape(result, "risk_review_analysis")
        risks = result["dataframes"]["高风险评论"]
        self.assertTrue((risks["风险标签"] != "正常").all())

    def test_positive_workflow_returns_keyword_table(self):
        result = agent_workflow.run_positive_review_analysis("喜欢什么", self.make_reviews())

        self.assert_result_shape(result, "positive_review_analysis")
        self.assertFalse(result["dataframes"]["好评关键词"].empty)

    def test_version_workflow_aggregates_and_sorts_problem_versions(self):
        result = agent_workflow.run_version_analysis("哪个版本问题最多", self.make_reviews())

        self.assert_result_shape(result, "version_analysis")
        version_table = result["dataframes"]["版本分析"]
        self.assertEqual(
            list(version_table.columns),
            ["版本", "评论数", "平均评分", "平均情绪指数", "差评数", "差评占比"],
        )
        self.assertEqual(version_table.iloc[0]["版本"], "2.0.0")

    def test_version_workflow_handles_missing_version(self):
        reviews = self.make_reviews().drop(columns=["版本"])

        result = agent_workflow.run_version_analysis("版本", reviews)

        self.assertIn("缺少“版本”字段", result["answer"])
        self.assertTrue(result["dataframes"]["版本分析"].empty)

    def test_trend_workflow_compares_latest_two_dates(self):
        result = agent_workflow.run_trend_analysis("最近趋势", self.make_reviews())

        self.assert_result_shape(result, "trend_analysis")
        self.assertFalse(result["dataframes"]["趋势分析"].empty)
        self.assertIn("最近两个时间点", result["answer"])

    def test_trend_workflow_handles_missing_time(self):
        reviews = self.make_reviews().drop(columns=["时间"])

        result = agent_workflow.run_trend_analysis("趋势", reviews)

        self.assertIn("缺少可识别的时间字段", result["answer"])

    def test_product_suggestion_prefers_matching_ai_recommendations(self):
        insights = {
            "recommendations": ["建立账号申诉进度查询入口。"],
            "report_copy": "账号治理是当前首要问题。",
        }

        result = agent_workflow.run_product_suggestion(
            "优化建议",
            self.make_reviews(),
            ai_insights=insights,
        )

        self.assertIn("建立账号申诉进度查询入口", result["answer"])
        self.assertIn("账号治理是当前首要问题", result["answer"])
        self.assertFalse(result["dataframes"]["问题优先级"].empty)

    def test_report_contains_required_markdown_sections(self):
        result = agent_workflow.run_report_generation("生成报告", self.make_reviews())

        for heading in (
            "# App 评论舆情分析报告",
            "## 一、核心指标",
            "## 二、问题优先级",
            "## 三、高风险评论",
            "## 四、AI 舆情总结",
            "## 五、产品优化建议",
        ):
            self.assertIn(heading, result["answer"])

    def test_general_workflow_returns_metrics_and_examples(self):
        result = agent_workflow.run_general_analysis("看看数据", self.make_reviews())

        self.assert_result_shape(result, "general_analysis")
        self.assertEqual(result["dataframes"]["基础指标"].iloc[0]["评论数"], 5)
        self.assertIn("可以继续提问", result["answer"])

    def test_run_agent_routes_adds_scope_prefix_and_meta(self):
        reviews = self.make_reviews().iloc[:3]

        result = agent_workflow.run_agent(
            "差评主要集中在哪些问题？",
            reviews,
            scope="当前筛选结果",
        )

        self.assertEqual(result["intent"], "negative_review_analysis")
        self.assertTrue(result["answer"].startswith("以下结论基于当前筛选后的 3 条评论。"))
        self.assertEqual(
            result["meta"],
            {"scope": "当前筛选结果", "sample_size": 3},
        )

    def test_run_agent_handles_empty_and_missing_columns(self):
        empty_result = agent_workflow.run_agent("分析差评", pd.DataFrame())
        missing_result = agent_workflow.run_agent(
            "分析差评",
            pd.DataFrame([{"内容": "只有内容"}]),
        )

        self.assertIn("没有评论", empty_result["answer"])
        self.assertIn("缺少必要列", missing_result["answer"])
        self.assertEqual(empty_result["meta"]["sample_size"], 0)

    def test_scope_signature_matches_only_identical_samples(self):
        reviews = self.make_reviews()
        signature = agent_workflow.dataframe_scope_signature(reviews)
        insights = {"summary": "同范围洞察"}

        self.assertEqual(
            agent_workflow.match_ai_insights(insights, signature, reviews),
            insights,
        )
        self.assertIsNone(
            agent_workflow.match_ai_insights(insights, signature, reviews.iloc[:2])
        )
        self.assertIsNone(agent_workflow.match_ai_insights(insights, None, reviews))


if __name__ == "__main__":
    unittest.main()
