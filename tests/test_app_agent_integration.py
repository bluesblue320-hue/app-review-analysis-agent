import unittest
from pathlib import Path


class AppApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("app.py").read_text(encoding="utf-8")

    def test_imports_only_http_client_for_business_workflows(self):
        self.assertIn("from frontend.api_client import (", self.source)
        self.assertNotIn("from visual_analysis import", self.source)
        self.assertNotIn("from review_preprocessing import", self.source)
        self.assertNotIn("from agent_workflow import", self.source)
        self.assertNotIn("from ai_analysis import", self.source)

    def test_uploads_csv_and_saves_dataset_id(self):
        self.assertIn("client.upload_dataset(", self.source)
        self.assertIn('st.session_state["dataset_id"] = dataset_id', self.source)
        self.assertIn('st.session_state["uploaded_file_signature"]', self.source)

    def test_sends_filters_to_summary_endpoint(self):
        self.assertIn("current_filters = filters_payload(", self.source)
        self.assertIn("client.get_summary(", self.source)
        self.assertIn("selected_categories", self.source)
        self.assertIn("high_risk_only", self.source)

    def test_renders_agent_scope_and_uses_backend_agent(self):
        self.assertIn('st.header("🤖 自然语言分析 Agent")', self.source)
        self.assertIn('options=["完整上传数据", "当前筛选结果"]', self.source)
        self.assertIn("client.query_agent(", self.source)
        self.assertNotIn("run_agent(", self.source)

    def test_ai_insights_are_generated_by_backend(self):
        self.assertIn("client.generate_ai_insights(", self.source)
        self.assertIn('st.session_state["ai_insight_id"]', self.source)
        self.assertIn('st.session_state["ai_insights_scope_signature"]', self.source)
        self.assertNotIn("analyze_reviews(", self.source)

    def test_backend_requests_send_only_insight_id(self):
        self.assertIn("insight_id=stored_insight_id", self.source)
        self.assertIn("insight_id=agent_insight_id", self.source)
        self.assertNotIn('ai_insights=st.session_state.get("ai_insights")', self.source)
        self.assertNotIn("ai_scope_signature=", self.source)

    def test_dataset_switch_clears_server_insight_reference(self):
        clear_state = self.source[self.source.index("def clear_dataset_state") :]
        clear_state = clear_state[: clear_state.index("def handle_api_error")]
        self.assertIn('"ai_insight_id"', clear_state)

    def test_rating_sentiment_mismatch_tab_uses_dedicated_backend_fields(self):
        self.assertIn('full_summary.get("rating_sentiment_mismatches", [])', self.source)
        self.assertIn('"rating_sentiment_mismatch_count"', self.source)
        self.assertNotIn('.str.contains("高星低情绪"', self.source)

    def test_handles_api_errors_without_stopping_complete_scope_agent(self):
        self.assertIn("except ApiClientError as exc:", self.source)
        warning = 'st.warning("当前筛选条件下没有评论，请放宽筛选条件。")'
        warning_position = self.source.index(warning)
        following_source = self.source[warning_position : warning_position + 180]
        self.assertNotIn("st.stop()", following_source)


if __name__ == "__main__":
    unittest.main()
