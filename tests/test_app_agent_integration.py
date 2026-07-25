import unittest
from pathlib import Path


class AppAgentIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("app.py").read_text(encoding="utf-8")

    def test_imports_agent_workflow(self):
        self.assertIn("from agent_workflow import (", self.source)
        self.assertIn("run_agent,", self.source)
        self.assertIn("match_ai_insights,", self.source)

    def test_renders_agent_scope_and_question_controls(self):
        self.assertIn('st.header("🤖 自然语言分析 Agent")', self.source)
        self.assertIn('"Agent 分析范围"', self.source)
        self.assertIn('options=["完整上传数据", "当前筛选结果"]', self.source)
        self.assertIn('st.text_input(', self.source)
        self.assertIn('st.button("让 Agent 分析")', self.source)

    def test_uses_scope_matched_ai_insights(self):
        self.assertIn('st.session_state["ai_insights_scope_signature"]', self.source)
        self.assertIn("matched_ai_insights = match_ai_insights(", self.source)
        self.assertIn("df=agent_df", self.source)
        self.assertIn("ai_insights=matched_ai_insights", self.source)
        self.assertIn("scope=agent_scope", self.source)

    def test_dashboard_uses_only_scope_matched_ai_insights(self):
        self.assertIn("current_insights = match_ai_insights(", self.source)
        self.assertIn("        filtered_df,\n    )", self.source)
        self.assertIn(
            "priority_df = calculate_priority_table(filtered_df, ai_insights=current_insights, top_n=5)",
            self.source,
        )
        self.assertIn("insights = current_insights", self.source)
        self.assertIn(
            'if st.session_state.get("ai_insights") and current_insights is None:',
            self.source,
        )
        self.assertIn("请重新生成 AI 洞察", self.source)
        self.assertNotIn(
            'current_insights = st.session_state.get("ai_insights")', self.source
        )
        self.assertNotIn('insights = st.session_state.get("ai_insights")', self.source)

    def test_empty_filter_no_longer_stops_complete_data_agent(self):
        warning = 'st.warning("当前筛选条件下没有评论，请放宽筛选条件。")'
        warning_position = self.source.index(warning)
        following_source = self.source[warning_position:warning_position + 180]
        self.assertNotIn("st.stop()", following_source)


if __name__ == "__main__":
    unittest.main()
