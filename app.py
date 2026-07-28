import hashlib

import pandas as pd
import streamlit as st

from frontend.api_client import (
    ApiClientError,
    ApiResponseError,
    InvalidApiResponseError,
    build_api_client,
)
from review_fields import (
    CATEGORY_COLUMN,
    CONTENT_COLUMN,
    RATING_COLUMN,
    RISK_LABEL_COLUMN,
    SENTIMENT_COLUMN,
)


st.set_page_config(page_title="竞品舆情分析罗盘", page_icon="🧭", layout="wide")
st.title("🧭 竞品舆情自动化分析罗盘")
st.markdown("上传应用商店评论数据，一键提取核心槽点与情感健康度。")


@st.cache_resource
def get_api_client():
    return build_api_client()


def clear_dataset_state() -> None:
    for key in (
        "dataset_id",
        "dataset_metadata",
        "uploaded_file_signature",
        "full_summary",
        "available_categories",
        "ai_insights",
        "ai_insights_scope_signature",
        "ai_insights_sample_size",
    ):
        st.session_state.pop(key, None)


def handle_api_error(error: ApiClientError, action: str) -> None:
    if isinstance(error, ApiResponseError) and error.code == "dataset_not_found":
        clear_dataset_state()
        st.error(f"{action}失败：后端中的数据集已失效，请重新上传 CSV。")
        return
    st.error(f"{action}失败：{error}")


def filters_payload(
    rating_range,
    sentiment_range,
    selected_categories,
    keyword,
    high_risk_only,
):
    return {
        "rating_min": rating_range[0],
        "rating_max": rating_range[1],
        "sentiment_min": sentiment_range[0],
        "sentiment_max": sentiment_range[1],
        "categories": selected_categories,
        "keyword": keyword,
        "high_risk_only": high_risk_only,
    }


def review_dataframe(records):
    columns = ["rating", "sentiment", "category", "risk_label", "content"]
    return pd.DataFrame(records or [], columns=columns).rename(
        columns={
            "rating": RATING_COLUMN,
            "sentiment": SENTIMENT_COLUMN,
            "category": CATEGORY_COLUMN,
            "risk_label": RISK_LABEL_COLUMN,
            "content": CONTENT_COLUMN,
        }
    )


def keyword_dataframe(records):
    return pd.DataFrame(records or [], columns=["keyword", "weight"]).rename(
        columns={"keyword": "关键词", "weight": "权重"}
    )


def priority_dataframe(records):
    return pd.DataFrame(records or []).rename(
        columns={
            "category": CATEGORY_COLUMN,
            "priority_score": "优先级分数",
            "severity": "严重程度",
            "review_count": "相关评论数",
            "average_rating": "平均评分",
            "average_sentiment": "平均情绪指数",
            "ai_severity": "AI严重度",
            "ai_recommendation": "AI建议",
            "representative_review": "代表评论",
        }
    )


def load_full_summary(client, dataset_id):
    full_summary = client.get_summary(dataset_id, {})
    st.session_state["full_summary"] = full_summary
    st.session_state["available_categories"] = full_summary.get(
        "available_categories", []
    )
    return full_summary


client = get_api_client()

with st.sidebar:
    st.header("📂 数据接入")
    uploaded_file = st.file_uploader("请上传评论数据集 (CSV格式)", type=["csv"])
    st.info("数据需包含 [评分] 和 [内容] 两列。")


if uploaded_file is not None:
    uploaded_content = uploaded_file.getvalue()
    upload_signature = hashlib.sha256(uploaded_content).hexdigest()
    dataset_id = st.session_state.get("dataset_id")

    if st.session_state.get("uploaded_file_signature") != upload_signature or not dataset_id:
        try:
            with st.spinner("正在上传数据并等待后端完成清洗与情感计算..."):
                upload_result = client.upload_dataset(
                    uploaded_file.name,
                    uploaded_content,
                    uploaded_file.type or "text/csv",
                )
            clear_dataset_state()
            dataset_id = str(upload_result["dataset_id"])
            st.session_state["dataset_id"] = dataset_id
            st.session_state["dataset_metadata"] = upload_result
            st.session_state["uploaded_file_signature"] = upload_signature
        except (ApiClientError, KeyError, TypeError) as exc:
            error = (
                exc
                if isinstance(exc, ApiClientError)
                else InvalidApiResponseError("上传响应缺少 dataset_id。")
            )
            handle_api_error(error, "上传数据")
            st.stop()

    dataset_id = st.session_state.get("dataset_id")
    if not dataset_id:
        st.stop()

    metadata = st.session_state.get("dataset_metadata", {})
    with st.sidebar:
        st.caption(
            f"数据集：{dataset_id[:20]}…｜"
            f"有效评论：{metadata.get('valid_rows', '-')} 条"
        )

    try:
        full_summary = st.session_state.get("full_summary")
        if not isinstance(full_summary, dict):
            full_summary = load_full_summary(client, dataset_id)
    except ApiClientError as exc:
        handle_api_error(exc, "加载数据概览")
        st.stop()

    category_options = sorted(st.session_state.get("available_categories", []))
    with st.sidebar:
        st.header("🧭 产品看板筛选")
        rating_range = st.slider("评分范围", 1, 5, (1, 5))
        sentiment_range = st.slider("情绪指数范围", 0, 100, (0, 100))
        selected_categories = st.multiselect(
            "问题类型",
            category_options,
            default=category_options,
            key=f"selected_categories_{dataset_id}",
        )
        keyword_query = st.text_input("关键词搜索", placeholder="例如：封号、广告、客服")
        high_risk_only = st.checkbox("只看高风险评论")

    current_filters = filters_payload(
        rating_range,
        sentiment_range,
        selected_categories,
        keyword_query,
        high_risk_only,
    )
    try:
        summary = client.get_summary(
            dataset_id,
            current_filters,
            ai_insights=st.session_state.get("ai_insights"),
            ai_scope_signature=st.session_state.get("ai_insights_scope_signature"),
        )
    except ApiClientError as exc:
        handle_api_error(exc, "加载看板分析")
        st.stop()

    st.success("数据处理完成！")
    if summary.get("sample_size", 0) == 0:
        st.warning("当前筛选条件下没有评论，请放宽筛选条件。")

    st.header("📊 产品健康概览")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("评论数", summary.get("sample_size", 0))
    col2.metric("平均星级", summary.get("average_rating", 0.0))
    col3.metric("差评占比", f"{summary.get('negative_ratio', 0.0)}%")
    average_sentiment = summary.get("average_sentiment", 0.0)
    sentiment_delta = (
        "健康" if average_sentiment > 60 else "需警惕" if average_sentiment > 40 else "高风险"
    )
    col4.metric("平均情绪", f"{average_sentiment} 分", sentiment_delta)
    col5.metric("高风险评论", summary.get("high_risk_count", 0))
    st.caption(
        f"当前样本：{summary.get('sample_size', 0)} 条｜"
        f"范围指纹：{str(summary.get('scope_signature', ''))[:12]}…"
    )

    st.subheader("🎯 问题优先级 Top 5")
    priority_df = priority_dataframe(summary.get("issue_priorities", []))
    if priority_df.empty:
        st.info("当前筛选范围内没有足够数据生成问题优先级。")
    else:
        st.bar_chart(priority_df[[CATEGORY_COLUMN, "优先级分数"]].set_index(CATEGORY_COLUMN))
        st.dataframe(priority_df, use_container_width=True, hide_index=True)

    st.subheader("🔎 评分与情绪诊断")
    chart_col1, chart_col2 = st.columns(2)
    rating_chart = pd.DataFrame(summary.get("rating_distribution", [])).rename(
        columns={"rating": RATING_COLUMN, "review_count": "评论数"}
    )
    sentiment_chart = pd.DataFrame(summary.get("sentiment_distribution", [])).rename(
        columns={"range": "情绪区间", "review_count": "评论数"}
    )
    with chart_col1:
        if rating_chart.empty:
            st.info("暂无评分分布数据。")
        else:
            st.bar_chart(rating_chart.set_index(RATING_COLUMN))
    with chart_col2:
        if sentiment_chart.empty:
            st.info("暂无情绪分布数据。")
        else:
            st.bar_chart(sentiment_chart.set_index("情绪区间"))

    filtered_reviews = review_dataframe(summary.get("reviews", []))
    if filtered_reviews.empty:
        st.info("暂无评分与情绪散点数据。")
    else:
        st.scatter_chart(
            filtered_reviews,
            x=RATING_COLUMN,
            y=SENTIMENT_COLUMN,
            color=CATEGORY_COLUMN,
        )

    st.subheader("🔤 关键词对比")
    keyword_col1, keyword_col2 = st.columns(2)
    negative_keywords = keyword_dataframe(summary.get("negative_keywords", []))
    positive_keywords = keyword_dataframe(summary.get("positive_keywords", []))
    with keyword_col1:
        st.markdown("**差评关键词**")
        if negative_keywords.empty:
            st.info("当前筛选范围内没有差评关键词。")
        else:
            st.bar_chart(negative_keywords.set_index("关键词"))
    with keyword_col2:
        st.markdown("**好评关键词**")
        if positive_keywords.empty:
            st.info("当前筛选范围内没有好评关键词。")
        else:
            st.bar_chart(positive_keywords.set_index("关键词"))

    trend_df = pd.DataFrame(summary.get("trend", [])).rename(
        columns={
            "date": "日期",
            "average_sentiment": "平均情绪指数",
            "average_rating": "平均评分",
            "review_count": "评论数",
        }
    )
    if not trend_df.empty:
        st.subheader("📈 舆情趋势")
        st.line_chart(trend_df.set_index("日期")[["平均情绪指数", "平均评分"]])

    st.subheader("🧾 可行动评论池")
    if len(filtered_reviews) < summary.get("sample_size", 0):
        st.caption(f"当前展示后端返回的前 {len(filtered_reviews)} 条评论。")
    st.dataframe(filtered_reviews, use_container_width=True, hide_index=True)
    st.divider()

    tab1, tab2, tab3 = st.tabs(
        ["🚨 核心槽点分析 (1-3星)", "✨ 核心爽点分析 (4-5星)", "🕵️‍♂️ 异常用户抓取"]
    )
    full_reviews = review_dataframe(full_summary.get("reviews", []))
    full_negative_keywords = keyword_dataframe(full_summary.get("negative_keywords", []))
    full_positive_keywords = keyword_dataframe(full_summary.get("positive_keywords", []))
    with tab1:
        st.subheader("导致用户流失的核心因素")
        if not full_negative_keywords.empty:
            st.bar_chart(full_negative_keywords.set_index("关键词"))
        negative_examples = full_reviews[full_reviews[RATING_COLUMN] <= 3]
        if not negative_examples.empty:
            st.markdown("**高频差评原声：**")
            st.dataframe(
                negative_examples.sort_values(SENTIMENT_COLUMN).head(5)[
                    [RATING_COLUMN, SENTIMENT_COLUMN, CONTENT_COLUMN]
                ],
                use_container_width=True,
                hide_index=True,
            )
    with tab2:
        st.subheader("驱动用户好评的核心要素")
        if not full_positive_keywords.empty:
            st.bar_chart(full_positive_keywords.set_index("关键词"))
    with tab3:
        st.subheader("情绪严重错位预警 (高星级但情绪极度负面)")
        mismatched = full_reviews[
            full_reviews[RISK_LABEL_COLUMN].astype(str).str.contains("高星低情绪", na=False)
        ]
        if mismatched.empty:
            st.write("目前未发现明显的阴阳怪气评论。")
        else:
            st.dataframe(
                mismatched[[RATING_COLUMN, SENTIMENT_COLUMN, CONTENT_COLUMN]],
                use_container_width=True,
                hide_index=True,
            )

    st.divider()
    st.header("🧠 AI 舆情洞察")
    try:
        ai_config = client.get_ai_config()
    except ApiClientError as exc:
        ai_config = {"provider": "后端 AI", "model": "未知", "configured": False}
        st.warning(f"无法读取 AI 配置：{exc}")
    st.caption(f"当前 AI 引擎：{ai_config.get('provider')} / {ai_config.get('model')}")
    if not ai_config.get("configured"):
        st.warning("后端未检测到 DEEPSEEK_API_KEY，请配置后再生成 AI 洞察。")

    if st.button(
        "生成 AI 舆情洞察",
        type="primary",
        disabled=not ai_config.get("configured") or summary.get("sample_size", 0) == 0,
    ):
        try:
            with st.spinner("DeepSeek 正在阅读评论并生成结构化洞察..."):
                insight_result = client.generate_ai_insights(dataset_id, current_filters)
            st.session_state["ai_insights"] = insight_result.get("insights", {})
            st.session_state["ai_insights_scope_signature"] = insight_result.get(
                "scope_signature"
            )
            st.session_state["ai_insights_sample_size"] = insight_result.get("sample_size")
            st.rerun()
        except ApiClientError as exc:
            handle_api_error(exc, "生成 AI 洞察")

    stored_insights = st.session_state.get("ai_insights")
    stored_insight_signature = st.session_state.get("ai_insights_scope_signature")
    insights = (
        stored_insights
        if stored_insight_signature == summary.get("scope_signature")
        else None
    )
    if stored_insights and insights is None:
        st.info("当前筛选范围与已有 AI 洞察不一致，请重新生成 AI 洞察。")
    if insights:
        st.subheader("舆情总览")
        st.write(insights.get("summary", "暂无 AI 总览。"))
        pain_points = insights.get("pain_points", [])
        if pain_points:
            st.subheader("核心槽点")
            for index, item in enumerate(pain_points, start=1):
                item = item if isinstance(item, dict) else {"name": str(item)}
                title = item.get("name") or f"槽点 {index}"
                severity = item.get("severity")
                label = f"{index}. {title}" + (f" · {severity}" if severity else "")
                with st.expander(label, expanded=index == 1):
                    if item.get("explanation"):
                        st.write(item["explanation"])
                    if item.get("evidence"):
                        st.markdown("**代表原声**")
                        for quote in item["evidence"]:
                            st.write(f"- {quote}")
                    if item.get("suggestion"):
                        st.markdown("**建议**")
                        st.write(item["suggestion"])
        delighters = insights.get("delighters", [])
        if delighters:
            st.subheader("核心爽点")
            for index, item in enumerate(delighters, start=1):
                item = item if isinstance(item, dict) else {"name": str(item)}
                with st.expander(f"{index}. {item.get('name') or '爽点'}"):
                    if item.get("explanation"):
                        st.write(item["explanation"])
                    for quote in item.get("evidence") or []:
                        st.write(f"- {quote}")
        if insights.get("sentiment_drivers"):
            st.subheader("情绪归因")
            for driver in insights["sentiment_drivers"]:
                st.write(f"- {driver}")
        if insights.get("high_risk_reviews"):
            st.subheader("高风险评论")
            st.dataframe(pd.DataFrame(insights["high_risk_reviews"]), use_container_width=True)
        if insights.get("recommendations"):
            st.subheader("产品与运营建议")
            for recommendation in insights["recommendations"]:
                st.write(f"- {recommendation}")
        if insights.get("report_copy"):
            st.subheader("可复制汇报文案")
            st.text_area("汇报文案", value=insights["report_copy"], height=160)

    st.divider()
    st.header("🤖 自然语言分析 Agent")
    st.markdown(
        """
可尝试以下问题：

- 差评主要集中在哪些问题？
- 哪些评论需要人工优先处理？
- 用户最喜欢哪些功能？
- 哪个版本问题最多？
- 最近评分趋势有没有下降？
- 帮我生成产品优化建议。
- 帮我生成一份评论分析报告。
"""
    )
    agent_scope = st.radio(
        "Agent 分析范围",
        options=["完整上传数据", "当前筛选结果"],
        horizontal=True,
        help="选择当前筛选结果后，侧边栏筛选会同步影响 Agent 结论。",
    )
    agent_sample_size = (
        metadata.get("valid_rows", 0)
        if agent_scope == "完整上传数据"
        else summary.get("sample_size", 0)
    )
    st.caption(f"当前分析范围：{agent_scope}｜分析样本数：{agent_sample_size} 条")
    user_question = st.text_input(
        "请输入你的分析问题",
        placeholder="例如：差评主要集中在哪些问题？",
    )
    if st.button("让 Agent 分析"):
        if not user_question.strip():
            st.warning("请先输入分析问题。")
        elif agent_scope == "当前筛选结果" and summary.get("sample_size", 0) == 0:
            st.warning("当前筛选结果为空，请放宽侧边栏筛选条件后再分析。")
        else:
            try:
                with st.spinner("Agent 正在调用后端分析流程..."):
                    agent_result = client.query_agent(
                        dataset_id=dataset_id,
                        question=user_question,
                        filters=current_filters,
                        scope="full" if agent_scope == "完整上传数据" else "filtered",
                        ai_insights=st.session_state.get("ai_insights"),
                        ai_scope_signature=st.session_state.get(
                            "ai_insights_scope_signature"
                        ),
                    )
                st.caption(
                    f"识别意图：{agent_result.get('intent')}｜"
                    f"范围：{agent_result.get('scope_label')}｜"
                    f"样本数：{agent_result.get('sample_size')} 条"
                )
                st.markdown(agent_result.get("answer", "暂无回答。"))
                tool_calls = agent_result.get("tool_calls", [])
                if tool_calls:
                    with st.expander("工具调用记录", expanded=False):
                        for index, tool_call in enumerate(tool_calls, start=1):
                            st.markdown(
                                f"**{index}. {tool_call.get('name', '未知工具')}**｜"
                                f"状态：{tool_call.get('status', 'unknown')}｜"
                                f"耗时：{tool_call.get('duration_ms', 0)} ms"
                            )
                            st.json(tool_call.get("arguments", {}))
                            if tool_call.get("error"):
                                st.warning(tool_call["error"])
                for warning in agent_result.get("warnings", []):
                    st.caption(f"⚠️ {warning}")
                for name, records in agent_result.get("tables", {}).items():
                    st.subheader(name)
                    table = pd.DataFrame(records)
                    if table.empty:
                        st.info(f"暂无{name}数据。")
                    else:
                        st.dataframe(table, use_container_width=True, hide_index=True)
            except ApiClientError as exc:
                handle_api_error(exc, "Agent 分析")
else:
    st.info("👈 请在左侧上传你在上一步爬取的 `xiaohongshu_reviews.csv` 文件以生成分析报告。")
