"""Contract tests for the Streamlit componentization (stage 6).

app.py must only assemble components; all business logic (uploads, filters,
summary requests, AI insights, agent) lives in frontend/components.py and
never imports analysis modules directly.
"""

import unittest
from pathlib import Path


class AppApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = Path("app.py").read_text(encoding="utf-8")
        cls.components_source = Path("frontend/components.py").read_text(
            encoding="utf-8"
        )

    def test_app_only_assembles_components(self):
        self.assertIn("from frontend.components import (", self.app_source)
        # Business logic is delegated to components, not inlined in entrypoint.
        self.assertNotIn("def render_health_metrics", self.app_source)
        self.assertNotIn("def render_ai_insights", self.app_source)
        self.assertNotIn("def render_agent_section", self.app_source)
        self.assertNotIn("def render_review_pagination", self.app_source)

    def test_components_import_only_http_client_for_business_workflows(self):
        self.assertIn(
            "from frontend.api_client import ApiClientError", self.components_source
        )
        self.assertNotIn("from visual_analysis import", self.components_source)
        self.assertNotIn("from review_preprocessing import", self.components_source)
        self.assertNotIn("from agent_workflow import", self.components_source)
        self.assertNotIn("from ai_analysis import", self.components_source)

    def test_uploads_csv_and_saves_dataset_id(self):
        self.assertIn("client.upload_dataset(", self.components_source)
        self.assertIn(
            "st.session_state[STATE_DATASET_ID] = dataset_id", self.components_source
        )
        self.assertIn(
            "st.session_state[STATE_UPLOADED_FILE_SIGNATURE]", self.components_source
        )

    def test_sends_filters_to_summary_endpoint(self):
        self.assertIn("def filters_payload(", self.components_source)
        self.assertIn("client.get_summary(", self.components_source)
        self.assertIn("selected_categories", self.components_source)
        self.assertIn("high_risk_only", self.components_source)

    def test_filters_use_st_form(self):
        self.assertIn("st.form(", self.components_source)
        self.assertIn("st.form_submit_button", self.components_source)

    def test_renders_agent_scope_and_uses_backend_agent(self):
        self.assertIn('st.header("🤖 自然语言分析 Agent")', self.components_source)
        self.assertIn(
            'options=["完整上传数据", "当前筛选结果"]', self.components_source
        )
        self.assertIn("client.query_agent(", self.components_source)
        self.assertNotIn("run_agent(", self.components_source)

    def test_ai_insights_are_generated_by_backend(self):
        self.assertIn("client.generate_ai_insights(", self.components_source)
        self.assertIn("st.session_state[STATE_AI_INSIGHT_ID]", self.components_source)
        self.assertIn(
            "st.session_state[STATE_AI_INSIGHTS_SCOPE_SIGNATURE]",
            self.components_source,
        )
        self.assertNotIn("analyze_reviews(", self.components_source)

    def test_backend_requests_send_only_insight_id(self):
        self.assertIn("insight_id=stored_insight_id", self.app_source)
        self.assertIn("insight_id=agent_insight_id", self.components_source)
        self.assertNotIn(
            'ai_insights=st.session_state.get("ai_insights")', self.components_source
        )

    def test_dataset_switch_clears_server_insight_reference(self):
        clear_state = self.components_source[
            self.components_source.index("def clear_dataset_state") :
        ]
        clear_state = clear_state[: clear_state.index("def handle_api_error")]
        self.assertIn("STATE_AI_INSIGHT_ID", clear_state)

    def test_rating_sentiment_mismatch_tab_uses_dedicated_backend_fields(self):
        self.assertIn(
            'full_summary.get("rating_sentiment_mismatches", [])',
            self.components_source,
        )
        self.assertIn('"rating_sentiment_mismatch_count"', self.components_source)
        self.assertNotIn('.str.contains("高星低情绪"', self.components_source)

    def test_handles_api_errors_without_stopping_complete_scope_agent(self):
        self.assertIn("except ApiClientError as exc:", self.components_source)
        warning = 'st.warning("当前筛选条件下没有评论，请放宽筛选条件。")'
        self.assertIn(warning, self.app_source)

    def test_pagination_uses_view_offset_limit(self):
        self.assertIn("client.search_reviews(", self.components_source)
        self.assertIn("offset", self.components_source)
        self.assertIn("limit", self.components_source)
        self.assertIn("上一页", self.components_source)
        self.assertIn("下一页", self.components_source)

    def test_ai_requires_session_confirmation_before_model_call(self):
        self.assertIn("ai_consent_confirmed", self.components_source)
        self.assertIn("请再次点击按钮确认后继续", self.components_source)

    def test_agent_shows_limitations_evidence_and_routing(self):
        self.assertIn("limitations", self.components_source)
        self.assertIn("evidence_call_ids", self.components_source)
        self.assertIn("routing", self.components_source)


if __name__ == "__main__":
    unittest.main()
