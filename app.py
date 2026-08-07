"""Streamlit application entrypoint (assembly only; logic lives in components).

Uploads, filters, summary, AI insights, agent and pagination are delegated to
frontend.components; business analysis always runs on the backend.
"""

import streamlit as st

from frontend.api_client import (
    ApiClientError,
    build_api_client,
)
from frontend.components import (
    STATE_AI_INSIGHT_ID,
    STATE_AI_INSIGHTS_SCOPE_SIGNATURE,
    STATE_AVAILABLE_CATEGORIES,
    STATE_DATASET_METADATA,
    STATE_FULL_SUMMARY,
    handle_api_error,
    load_full_summary,
    render_agent_section,
    render_ai_insights,
    render_analysis_tabs,
    render_dataset_caption,
    render_filter_sidebar,
    render_health_metrics,
    render_keyword_columns,
    render_priority_table,
    render_rating_sentiment_charts,
    render_review_pagination,
    render_scatter,
    render_trend,
    render_upload_section,
)

st.set_page_config(page_title="竞品舆情分析罗盘", page_icon="🧭", layout="wide")
st.title("🧭 竞品舆情自动化分析罗盘")
st.markdown("上传应用商店评论数据，一键提取核心槽点与情感健康度。")


@st.cache_resource
def get_api_client():
    return build_api_client()


client = get_api_client()

with st.sidebar:
    st.header("📂 数据接入")

dataset_id = render_upload_section(client)
if dataset_id is None:
    st.info(
        "👈 请在左侧上传你在上一步爬取的 `xiaohongshu_reviews.csv` 文件以生成分析报告。"
    )
    st.stop()

metadata = st.session_state.get(STATE_DATASET_METADATA, {})
with st.sidebar:
    render_dataset_caption(metadata)

try:
    full_summary = st.session_state.get(STATE_FULL_SUMMARY)
    if not isinstance(full_summary, dict):
        full_summary = load_full_summary(client, dataset_id)
except ApiClientError as exc:
    handle_api_error(exc, "加载数据概览")
    st.stop()

category_options = sorted(st.session_state.get(STATE_AVAILABLE_CATEGORIES, []))
current_filters = render_filter_sidebar(category_options, dataset_id)

try:
    summary = client.get_summary(dataset_id, current_filters)
    stored_insight_id = st.session_state.get(STATE_AI_INSIGHT_ID)
    stored_insight_signature = st.session_state.get(STATE_AI_INSIGHTS_SCOPE_SIGNATURE)
    if stored_insight_id and stored_insight_signature == summary.get("scope_signature"):
        summary = client.get_summary(
            dataset_id,
            current_filters,
            insight_id=stored_insight_id,
        )
except ApiClientError as exc:
    handle_api_error(exc, "加载看板分析")
    st.stop()

st.success("数据处理完成！")
if summary.get("sample_size", 0) == 0:
    st.warning("当前筛选条件下没有评论，请放宽筛选条件。")
for warning in summary.get("warnings", []):
    st.caption(f"⚠️ {warning}")

st.header("📊 产品健康概览")
render_health_metrics(summary)

render_priority_table(summary)
render_rating_sentiment_charts(summary)
render_scatter(summary)
render_keyword_columns(summary)
render_trend(summary)

render_review_pagination(client, dataset_id, current_filters)
st.divider()

render_analysis_tabs(full_summary)
st.divider()

st.header("🧠 AI 舆情洞察")
render_ai_insights(client, dataset_id, current_filters, summary)
st.divider()

render_agent_section(
    client,
    dataset_id,
    metadata,
    current_filters,
    summary,
    full_summary,
)
