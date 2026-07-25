import streamlit as st
import pandas as pd
import re
import jieba.posseg as pseg
from snownlp import SnowNLP
from ai_analysis import AiAnalysisError, analyze_reviews, load_ai_config
from agent_workflow import (
    dataframe_scope_signature,
    match_ai_insights,
    run_agent,
)
from visual_analysis import (
    CATEGORY_COLUMN,
    CONTENT_COLUMN,
    RATING_COLUMN,
    RISK_LABEL_COLUMN,
    SENTIMENT_COLUMN,
    TOKEN_COLUMN,
    calculate_health_metrics,
    calculate_priority_table,
    extract_keyword_scores,
    filter_reviews,
    prepare_dashboard_data,
    rating_distribution,
    sentiment_distribution,
    sentiment_scatter_data,
    sentiment_trend,
)

# ==========================
# 0. 页面全局配置
# ==========================
st.set_page_config(page_title="竞品舆情分析罗盘", page_icon="🧭", layout="wide")
st.title("🧭 竞品舆情自动化分析罗盘")
st.markdown("上传应用商店评论数据，一键提取核心槽点与情感健康度。")

# ==========================
# 1. 核心处理函数 (使用 st.cache_data 缓存计算，让网页飞起来)
# ==========================
@st.cache_data
def process_data(df):
    # 停用词库
    stop_words = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '小红书', '软件', '非常', '可以', '不错', '不能'}

    # 清洗与分词
    def advanced_clean_and_cut(text):
        text = str(text)
        text = re.sub(r'[^\u4e00-\u9fa5]', '', text)
        words = pseg.lcut(text)
        useful_words = [w for w, f in words if len(w) > 1 and w not in stop_words and (f.startswith('n') or f.startswith('v') or f.startswith('a'))]
        return " ".join(useful_words)

    df['分词内容'] = df['内容'].apply(advanced_clean_and_cut)

    # 情感打分
    def get_sentiment(text):
        try:
            return round(SnowNLP(str(text)).sentiments * 100, 2)
        except:
            return 50.0

    df['情绪指数'] = df['内容'].apply(get_sentiment)
    return df

@st.cache_data
def extract_keywords(text_series, top_n=10):
    keyword_scores = extract_keyword_scores(text_series, top_n=top_n)
    if keyword_scores.empty:
        return pd.DataFrame()
    return keyword_scores.rename(columns={"关键词": "特征词"}).set_index("特征词")

# ==========================
# 2. 前端交互界面
# ==========================
# 侧边栏：上传文件
with st.sidebar:
    st.header("📂 数据接入")
    uploaded_file = st.file_uploader("请上传评论数据集 (CSV格式)", type=['csv'])
    st.info("数据需包含 [评分] 和 [内容] 两列。")

# 主界面逻辑
if uploaded_file is not None:
    # 读取数据
    raw_df = pd.read_csv(uploaded_file)
    required_columns = {"评分", "内容"}
    missing_columns = required_columns - set(raw_df.columns)
    if missing_columns:
        st.error(f"CSV 缺少必要列：{', '.join(sorted(missing_columns))}")
        st.stop()

    with st.spinner('AI 引擎正在进行自然语言处理与情感计算，请稍候...'):
        df = process_data(raw_df)

    try:
        dashboard_df = prepare_dashboard_data(df)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    with st.sidebar:
        st.header("🧭 产品看板筛选")
        rating_range = st.slider("评分范围", 1, 5, (1, 5))
        sentiment_range = st.slider("情绪指数范围", 0, 100, (0, 100))
        category_options = sorted(dashboard_df[CATEGORY_COLUMN].dropna().unique().tolist())
        selected_categories = st.multiselect("问题类型", category_options, default=category_options)
        keyword_query = st.text_input("关键词搜索", placeholder="例如：封号、广告、客服")
        high_risk_only = st.checkbox("只看高风险评论")

    filtered_df = filter_reviews(
        dashboard_df,
        rating_range=rating_range,
        sentiment_range=sentiment_range,
        categories=selected_categories,
        keyword=keyword_query,
        high_risk_only=high_risk_only,
    )

    st.success("数据处理完成！")

    if filtered_df.empty:
        st.warning("当前筛选条件下没有评论，请放宽筛选条件。")

    metrics = calculate_health_metrics(filtered_df)

    st.header("📊 产品健康概览")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("评论数", metrics["total_reviews"])
    col2.metric("平均星级", metrics["average_rating"])
    col3.metric("差评占比", f"{metrics['negative_ratio']}%")
    sentiment_delta = "健康" if metrics["average_sentiment"] > 60 else "需警惕" if metrics["average_sentiment"] > 40 else "高风险"
    col4.metric("平均情绪", f"{metrics['average_sentiment']} 分", sentiment_delta)
    col5.metric("高风险评论", metrics["high_risk_count"])

    st.subheader("🎯 问题优先级 Top 5")
    current_insights = match_ai_insights(
        st.session_state.get("ai_insights"),
        st.session_state.get("ai_insights_scope_signature"),
        filtered_df,
    )
    priority_df = calculate_priority_table(filtered_df, ai_insights=current_insights, top_n=5)

    if priority_df.empty:
        st.info("当前筛选范围内没有足够数据生成问题优先级。")
    else:
        priority_chart = priority_df[[CATEGORY_COLUMN, "优先级分数"]].set_index(CATEGORY_COLUMN)
        st.bar_chart(priority_chart)
        st.dataframe(priority_df, use_container_width=True, hide_index=True)

    st.subheader("🔎 评分与情绪诊断")
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        rating_chart = rating_distribution(filtered_df)
        if rating_chart.empty:
            st.info("暂无评分分布数据。")
        else:
            st.bar_chart(rating_chart.set_index(RATING_COLUMN))

    with chart_col2:
        sentiment_chart = sentiment_distribution(filtered_df)
        if sentiment_chart.empty:
            st.info("暂无情绪分布数据。")
        else:
            st.bar_chart(sentiment_chart.set_index("情绪区间"))

    scatter_df = sentiment_scatter_data(filtered_df)
    if scatter_df.empty:
        st.info("暂无评分与情绪散点数据。")
    else:
        st.scatter_chart(scatter_df, x=RATING_COLUMN, y=SENTIMENT_COLUMN, color=CATEGORY_COLUMN)

    st.subheader("🔤 关键词对比")
    keyword_col1, keyword_col2 = st.columns(2)
    negative_keywords = extract_keyword_scores(
        filtered_df[filtered_df[RATING_COLUMN] <= 3].get(TOKEN_COLUMN, pd.Series(dtype=str)),
        top_n=15,
    )
    positive_keywords = extract_keyword_scores(
        filtered_df[filtered_df[RATING_COLUMN] >= 4].get(TOKEN_COLUMN, pd.Series(dtype=str)),
        top_n=15,
    )

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

    trend_df = sentiment_trend(filtered_df)
    if not trend_df.empty:
        st.subheader("📈 舆情趋势")
        st.line_chart(trend_df.set_index("日期")[["平均情绪指数", "平均评分"]])

    st.subheader("🧾 可行动评论池")
    display_columns = [
        RATING_COLUMN,
        SENTIMENT_COLUMN,
        CATEGORY_COLUMN,
        RISK_LABEL_COLUMN,
        CONTENT_COLUMN,
    ]
    st.dataframe(filtered_df[display_columns], use_container_width=True, hide_index=True)

    st.divider()

    # 业务下钻区 (使用标签页)
    tab1, tab2, tab3 = st.tabs(["🚨 核心槽点分析 (1-3星)", "✨ 核心爽点分析 (4-5星)", "🕵️‍♂️ 异常用户抓取"])

    with tab1:
        st.subheader("导致用户流失的核心因素")
        bad_df = dashboard_df[dashboard_df[RATING_COLUMN] <= 3]
        if not bad_df.empty:
            bad_keywords = extract_keywords(bad_df[TOKEN_COLUMN], 15)
            # 使用 Streamlit 自带的炫酷横向柱状图
            st.bar_chart(bad_keywords)

            st.markdown("**高频差评原声：**")
            st.dataframe(bad_df.sort_values(by=SENTIMENT_COLUMN).head(5)[[RATING_COLUMN, SENTIMENT_COLUMN, CONTENT_COLUMN]], use_container_width=True)

    with tab2:
        st.subheader("驱动用户好评的核心要素")
        good_df = dashboard_df[dashboard_df[RATING_COLUMN] >= 4]
        if not good_df.empty:
            good_keywords = extract_keywords(good_df[TOKEN_COLUMN], 15)
            st.bar_chart(good_keywords)

    with tab3:
        st.subheader("情绪严重错位预警 (高星级但情绪极度负面)")
        fake_good = dashboard_df[(dashboard_df[RATING_COLUMN] >= 4) & (dashboard_df[SENTIMENT_COLUMN] < 30)]
        if not fake_good.empty:
            st.dataframe(fake_good[[RATING_COLUMN, SENTIMENT_COLUMN, CONTENT_COLUMN]], use_container_width=True)
        else:
            st.write("目前未发现明显的阴阳怪气评论。")

    st.divider()
    st.header("🧠 AI 舆情洞察")
    config = load_ai_config()
    st.caption(f"当前 AI 引擎：{config['provider']} / {config['model']}")
    if not config["api_key"]:
        st.warning("未检测到 DEEPSEEK_API_KEY。请在系统环境变量或 .env 中配置后再生成 AI 洞察。")

    if st.button(
        "生成 AI 舆情洞察",
        type="primary",
        disabled=not bool(config["api_key"]) or filtered_df.empty,
    ):
        try:
            with st.spinner("DeepSeek 正在阅读评论并生成结构化洞察..."):
                st.session_state["ai_insights"] = analyze_reviews(filtered_df)
                st.session_state["ai_insights_scope_signature"] = dataframe_scope_signature(
                    filtered_df
                )
                st.session_state["ai_insights_sample_size"] = len(filtered_df)
                st.rerun()
        except AiAnalysisError as exc:
            st.error(str(exc))

    insights = current_insights
    if st.session_state.get("ai_insights") and current_insights is None:
        st.info("当前筛选范围与已有 AI 洞察不一致，请重新生成 AI 洞察。")
    if insights:
        st.subheader("舆情总览")
        st.write(insights.get("summary", "暂无 AI 总览。"))

        pain_points = insights.get("pain_points", [])
        if pain_points:
            st.subheader("核心槽点")
            for index, item in enumerate(pain_points, start=1):
                if not isinstance(item, dict):
                    item = {"name": str(item)}
                title = item.get("name") or f"槽点 {index}"
                severity = item.get("severity")
                label = f"{index}. {title}" + (f" · {severity}" if severity else "")
                with st.expander(label, expanded=index == 1):
                    if item.get("explanation"):
                        st.write(item["explanation"])
                    evidence = item.get("evidence") or []
                    if evidence:
                        st.markdown("**代表原声**")
                        for quote in evidence:
                            st.write(f"- {quote}")
                    if item.get("suggestion"):
                        st.markdown("**建议**")
                        st.write(item["suggestion"])

        delighters = insights.get("delighters", [])
        if delighters:
            st.subheader("核心爽点")
            for index, item in enumerate(delighters, start=1):
                if not isinstance(item, dict):
                    item = {"name": str(item)}
                with st.expander(f"{index}. {item.get('name') or '爽点'}"):
                    if item.get("explanation"):
                        st.write(item["explanation"])
                    evidence = item.get("evidence") or []
                    if evidence:
                        st.markdown("**代表原声**")
                        for quote in evidence:
                            st.write(f"- {quote}")

        sentiment_drivers = insights.get("sentiment_drivers", [])
        if sentiment_drivers:
            st.subheader("情绪归因")
            for driver in sentiment_drivers:
                st.write(f"- {driver}")

        high_risk_reviews = insights.get("high_risk_reviews", [])
        if high_risk_reviews:
            st.subheader("高风险评论")
            st.dataframe(pd.DataFrame(high_risk_reviews), use_container_width=True)

        recommendations = insights.get("recommendations", [])
        if recommendations:
            st.subheader("产品与运营建议")
            for recommendation in recommendations:
                st.write(f"- {recommendation}")

        report_copy = insights.get("report_copy")
        if report_copy:
            st.subheader("可复制汇报文案")
            st.text_area("汇报文案", value=report_copy, height=160)

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
        help="选择当前筛选结果后，侧边栏的评分、情绪、问题类型、关键词和高风险筛选会同步影响 Agent 结论。",
    )
    agent_df = dashboard_df if agent_scope == "完整上传数据" else filtered_df
    st.caption(f"当前分析范围：{agent_scope}｜分析样本数：{len(agent_df)} 条")

    matched_ai_insights = match_ai_insights(
        st.session_state.get("ai_insights"),
        st.session_state.get("ai_insights_scope_signature"),
        agent_df,
    )
    if st.session_state.get("ai_insights") and matched_ai_insights is None:
        st.caption("当前分析范围与已有 AI 洞察样本不一致，本次 Agent 将仅使用统计结果。")

    user_question = st.text_input(
        "请输入你的分析问题",
        placeholder="例如：差评主要集中在哪些问题？",
    )

    if st.button("让 Agent 分析"):
        if not user_question.strip():
            st.warning("请先输入分析问题。")
        elif agent_scope == "当前筛选结果" and agent_df.empty:
            st.warning("当前筛选结果为空，请放宽侧边栏筛选条件后再分析。")
        else:
            try:
                with st.spinner("Agent 正在调用数据分析流程..."):
                    agent_result = run_agent(
                        question=user_question,
                        df=agent_df,
                        ai_insights=matched_ai_insights,
                        scope=agent_scope,
                    )
                st.caption(
                    f"识别意图：{agent_result['intent']}｜"
                    f"范围：{agent_result['meta']['scope']}｜"
                    f"样本数：{agent_result['meta']['sample_size']} 条"
                )
                st.markdown(agent_result["answer"])
                for name, result_df in agent_result["dataframes"].items():
                    st.subheader(name)
                    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
                        st.dataframe(result_df, use_container_width=True, hide_index=True)
                    else:
                        st.info(f"暂无{name}数据。")
            except (KeyError, TypeError, ValueError) as exc:
                st.error(f"Agent 分析失败：{exc}")
else:
    # 默认引导提示
    st.info("👈 请在左侧上传你在上一步爬取的 `xiaohongshu_reviews.csv` 文件以生成分析报告。")
