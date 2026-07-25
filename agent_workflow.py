"""基于真实评论统计的轻量级自然语言分析 Agent。"""

import hashlib

import pandas as pd

from intent_router import detect_intent
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
    prepare_dashboard_data,
    sentiment_trend,
)


VERSION_COLUMN = "版本"


def _result(intent, answer, dataframes=None):
    return {
        "intent": intent,
        "answer": str(answer),
        "dataframes": dataframes or {},
    }


def _prepare_agent_data(df):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(), "当前分析范围内没有评论可供分析。"

    missing_columns = {RATING_COLUMN, CONTENT_COLUMN} - set(df.columns)
    if missing_columns:
        missing = "、".join(sorted(missing_columns))
        return pd.DataFrame(), f"数据缺少必要列：{missing}。"

    try:
        prepared = prepare_dashboard_data(df)
    except (TypeError, ValueError) as exc:
        return pd.DataFrame(), f"评论数据无法完成准备：{exc}"

    if prepared.empty:
        return prepared, "当前分析范围内没有有效评论可供分析。"
    return prepared, ""


def _keyword_source(df):
    if df is None or df.empty:
        return pd.Series(dtype=str)
    source_column = TOKEN_COLUMN if TOKEN_COLUMN in df.columns else CONTENT_COLUMN
    return df[source_column].fillna("").astype(str)


def _safe_ai_list(ai_insights, key):
    if not isinstance(ai_insights, dict):
        return []
    value = ai_insights.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safe_ai_text(ai_insights, key):
    if not isinstance(ai_insights, dict):
        return ""
    value = ai_insights.get(key, "")
    return str(value).strip() if value is not None else ""


def _review_columns(df):
    columns = [
        RATING_COLUMN,
        SENTIMENT_COLUMN,
        CATEGORY_COLUMN,
        RISK_LABEL_COLUMN,
        CONTENT_COLUMN,
    ]
    return [column for column in columns if column in df.columns]


def _metrics_dataframe(metrics):
    return pd.DataFrame(
        [
            {
                "评论数": metrics["total_reviews"],
                "平均评分": metrics["average_rating"],
                "差评占比": metrics["negative_ratio"],
                "平均情绪指数": metrics["average_sentiment"],
                "高风险评论数": metrics["high_risk_count"],
            }
        ]
    )


def dataframe_scope_signature(df):
    if df is None or not isinstance(df, pd.DataFrame):
        return hashlib.sha256(b"no-dataframe").hexdigest()

    preferred_columns = [
        RATING_COLUMN,
        CONTENT_COLUMN,
        SENTIMENT_COLUMN,
        TOKEN_COLUMN,
        CATEGORY_COLUMN,
        RISK_LABEL_COLUMN,
        VERSION_COLUMN,
        "时间",
        "日期",
        "评论时间",
        "发布时间",
    ]
    columns = [column for column in preferred_columns if column in df.columns]
    if not columns:
        columns = sorted(df.columns.astype(str).tolist())

    normalized = df.loc[:, columns].copy()
    for column in columns:
        normalized[column] = normalized[column].map(
            lambda value: "" if pd.isna(value) else str(value)
        )

    row_hashes = pd.util.hash_pandas_object(normalized, index=True).values.tobytes()
    header = f"{len(df)}|{'|'.join(columns)}|".encode("utf-8")
    return hashlib.sha256(header + row_hashes).hexdigest()


def match_ai_insights(ai_insights, stored_signature, df):
    if not isinstance(ai_insights, dict) or not stored_signature:
        return None
    if stored_signature != dataframe_scope_signature(df):
        return None
    return ai_insights


def run_negative_review_analysis(question, df, ai_insights=None):
    intent = "negative_review_analysis"
    prepared, error = _prepare_agent_data(df)
    if error:
        return _result(
            intent,
            error,
            {
                "差评关键词": pd.DataFrame(),
                "问题优先级": pd.DataFrame(),
                "典型差评": pd.DataFrame(),
            },
        )

    metrics = calculate_health_metrics(prepared)
    negative = prepared[prepared[RATING_COLUMN] <= 3].copy()
    keywords = extract_keyword_scores(_keyword_source(negative), top_n=15)
    priority = calculate_priority_table(negative, ai_insights=ai_insights, top_n=5)
    typical = negative.sort_values(
        [RATING_COLUMN, SENTIMENT_COLUMN], ascending=[True, True]
    ).head(10)
    typical = typical[_review_columns(typical)].reset_index(drop=True)

    if negative.empty:
        answer = "当前分析范围内没有评分小于等于 3 的差评。"
    else:
        ratio = round(len(negative) / len(prepared) * 100, 2)
        top_category = (
            priority.iloc[0][CATEGORY_COLUMN] if not priority.empty else "暂未归类"
        )
        keyword_text = (
            "、".join(keywords["关键词"].head(5).astype(str))
            if not keywords.empty
            else "暂无有效关键词"
        )
        answer = (
            f"共识别 {len(negative)} 条差评，占当前样本的 {ratio}%。"
            f"整体平均评分为 {metrics['average_rating']}，最需要关注的问题类型是{top_category}。"
            f"高频差评关键词包括：{keyword_text}。建议优先核查问题优先级表中的高分项。"
        )
    return _result(
        intent,
        answer,
        {"差评关键词": keywords, "问题优先级": priority, "典型差评": typical},
    )


def run_risk_review_analysis(question, df):
    intent = "risk_review_analysis"
    prepared, error = _prepare_agent_data(df)
    if error:
        return _result(intent, error, {"高风险评论": pd.DataFrame()})

    risk_reviews = prepared[
        prepared[RISK_LABEL_COLUMN].astype(str) != "正常"
    ].copy()
    risk_reviews = risk_reviews.sort_values(
        [RATING_COLUMN, SENTIMENT_COLUMN], ascending=[True, True]
    )
    risk_reviews = risk_reviews[_review_columns(risk_reviews)].reset_index(drop=True)
    if risk_reviews.empty:
        answer = "当前分析范围内没有识别到高风险评论。"
    else:
        ratio = round(len(risk_reviews) / len(prepared) * 100, 2)
        answer = (
            f"共识别 {len(risk_reviews)} 条高风险评论，占当前样本的 {ratio}%。"
            "表格已按低评分、低情绪优先排序，建议人工先处理最前面的评论。"
        )
    return _result(intent, answer, {"高风险评论": risk_reviews})


def run_positive_review_analysis(question, df):
    intent = "positive_review_analysis"
    prepared, error = _prepare_agent_data(df)
    if error:
        return _result(intent, error, {"好评关键词": pd.DataFrame()})

    positive = prepared[prepared[RATING_COLUMN] >= 4].copy()
    keywords = extract_keyword_scores(_keyword_source(positive), top_n=15)
    if positive.empty:
        answer = "当前分析范围内没有评分大于等于 4 的好评。"
    else:
        ratio = round(len(positive) / len(prepared) * 100, 2)
        keyword_text = (
            "、".join(keywords["关键词"].head(5).astype(str))
            if not keywords.empty
            else "暂无有效关键词"
        )
        answer = (
            f"共识别 {len(positive)} 条好评，占当前样本的 {ratio}%。"
            f"用户正向反馈主要围绕：{keyword_text}。"
        )
    return _result(intent, answer, {"好评关键词": keywords})


def run_version_analysis(question, df):
    intent = "version_analysis"
    prepared, error = _prepare_agent_data(df)
    if error:
        return _result(intent, error, {"版本分析": pd.DataFrame()})
    if VERSION_COLUMN not in prepared.columns:
        return _result(
            intent,
            "数据中缺少“版本”字段，暂时无法进行版本对比。",
            {"版本分析": pd.DataFrame()},
        )

    version_data = prepared.dropna(subset=[VERSION_COLUMN]).copy()
    version_data[VERSION_COLUMN] = version_data[VERSION_COLUMN].astype(str).str.strip()
    version_data = version_data[version_data[VERSION_COLUMN] != ""]
    if version_data.empty:
        return _result(
            intent,
            "“版本”字段没有有效值，暂时无法进行版本对比。",
            {"版本分析": pd.DataFrame()},
        )

    version_table = (
        version_data.groupby(VERSION_COLUMN, dropna=False)
        .agg(
            评论数=(CONTENT_COLUMN, "count"),
            平均评分=(RATING_COLUMN, "mean"),
            平均情绪指数=(SENTIMENT_COLUMN, "mean"),
            差评数=(RATING_COLUMN, lambda values: int((values <= 3).sum())),
        )
        .reset_index()
    )
    version_table["差评占比"] = (
        version_table["差评数"] / version_table["评论数"] * 100
    ).round(2)
    version_table["平均评分"] = version_table["平均评分"].round(2)
    version_table["平均情绪指数"] = version_table["平均情绪指数"].round(2)
    version_table = version_table.sort_values(
        ["差评占比", "平均评分"], ascending=[False, True]
    ).reset_index(drop=True)
    worst = version_table.iloc[0]
    answer = (
        f"版本 {worst[VERSION_COLUMN]} 的问题最突出：共 {int(worst['评论数'])} 条评论，"
        f"平均评分 {worst['平均评分']}，差评占比 {worst['差评占比']}%。"
        "该结果反映评论相关性，仍建议结合版本发布内容进一步定位原因。"
    )
    return _result(intent, answer, {"版本分析": version_table})


def run_trend_analysis(question, df):
    intent = "trend_analysis"
    prepared, error = _prepare_agent_data(df)
    if error:
        return _result(intent, error, {"趋势分析": pd.DataFrame()})

    trend = sentiment_trend(prepared).sort_values("日期").reset_index(drop=True)
    if trend.empty:
        return _result(
            intent,
            "数据缺少可识别的时间字段或有效日期，暂时无法判断趋势。",
            {"趋势分析": trend},
        )
    latest = trend.iloc[-1]
    if len(trend) == 1:
        answer = (
            f"当前只有一个有效时间点：平均评分 {latest['平均评分']}，"
            f"平均情绪指数 {latest['平均情绪指数']}，不足以判断升降趋势。"
        )
    else:
        previous = trend.iloc[-2]
        rating_delta = round(float(latest["平均评分"] - previous["平均评分"]), 2)
        sentiment_delta = round(
            float(latest["平均情绪指数"] - previous["平均情绪指数"]), 2
        )
        rating_direction = (
            "上升" if rating_delta > 0 else "下降" if rating_delta < 0 else "持平"
        )
        sentiment_direction = (
            "上升"
            if sentiment_delta > 0
            else "下降"
            if sentiment_delta < 0
            else "持平"
        )
        answer = (
            f"最近两个时间点相比，平均评分{rating_direction} {abs(rating_delta)} 分，"
            f"平均情绪指数{sentiment_direction} {abs(sentiment_delta)} 分。"
            f"最新时间点共有 {int(latest['评论数'])} 条评论。"
        )
    return _result(intent, answer, {"趋势分析": trend})


def _statistical_recommendations(priority):
    recommendations = []
    for _, row in priority.head(3).iterrows():
        recommendations.append(
            f"优先处理{row[CATEGORY_COLUMN]}：该类优先级分数为 {row['优先级分数']}，"
            f"涉及 {int(row['相关评论数'])} 条评论；建议围绕代表评论复盘产品与运营链路。"
        )
    return recommendations


def run_product_suggestion(question, df, ai_insights=None):
    intent = "product_suggestion"
    prepared, error = _prepare_agent_data(df)
    if error:
        return _result(intent, error, {"问题优先级": pd.DataFrame()})

    metrics = calculate_health_metrics(prepared)
    priority = calculate_priority_table(prepared, ai_insights=ai_insights, top_n=5)
    recommendations = _safe_ai_list(ai_insights, "recommendations")
    if not recommendations:
        recommendations = _statistical_recommendations(priority)
    if not recommendations:
        recommendations = ["当前问题分类信息不足，建议先扩大评论样本并完善问题标签。"]
    lines = [f"{index}. {text}" for index, text in enumerate(recommendations, start=1)]
    report_copy = _safe_ai_text(ai_insights, "report_copy")
    answer_parts = [
        f"当前样本差评占比为 {metrics['negative_ratio']}%，建议按以下顺序推进：",
        *lines,
    ]
    if report_copy:
        answer_parts.extend(["范围一致的 AI 汇报补充：", report_copy])
    return _result(intent, "\n\n".join(answer_parts), {"问题优先级": priority})


def run_report_generation(question, df, ai_insights=None):
    intent = "report_generation"
    prepared, error = _prepare_agent_data(df)
    if error:
        return _result(
            intent,
            error,
            {"问题优先级": pd.DataFrame(), "高风险评论": pd.DataFrame()},
        )

    metrics = calculate_health_metrics(prepared)
    priority = calculate_priority_table(prepared, ai_insights=ai_insights, top_n=5)
    risks = prepared[prepared[RISK_LABEL_COLUMN].astype(str) != "正常"].copy()
    risks = risks.sort_values(
        [RATING_COLUMN, SENTIMENT_COLUMN], ascending=[True, True]
    )
    risk_table = risks[_review_columns(risks)].head(20).reset_index(drop=True)
    summary = _safe_ai_text(ai_insights, "summary") or (
        "本部分未使用在线 AI 洞察，结论来自当前评论统计。"
    )
    recommendations = _safe_ai_list(
        ai_insights, "recommendations"
    ) or _statistical_recommendations(priority)
    recommendation_text = (
        "\n".join(f"- {item}" for item in recommendations)
        or "- 暂无足够信息生成建议。"
    )
    if priority.empty:
        priority_text = "当前没有足够数据生成问题优先级。"
    else:
        priority_text = "\n".join(
            f"- {row[CATEGORY_COLUMN]}：优先级 {row['优先级分数']}，相关评论 {int(row['相关评论数'])} 条。"
            for _, row in priority.iterrows()
        )
    report = f"""# App 评论舆情分析报告

## 一、核心指标

- 评论数：{metrics['total_reviews']}
- 平均评分：{metrics['average_rating']}
- 差评占比：{metrics['negative_ratio']}%
- 平均情绪指数：{metrics['average_sentiment']}
- 高风险评论数：{metrics['high_risk_count']}

## 二、问题优先级

{priority_text}

## 三、高风险评论

共识别 {len(risks)} 条高风险评论，表格展示按低评分、低情绪排序的前 20 条。

## 四、AI 舆情总结

{summary}

## 五、产品优化建议

{recommendation_text}
"""
    return _result(
        intent, report, {"问题优先级": priority, "高风险评论": risk_table}
    )


def run_general_analysis(question, df, ai_insights=None):
    intent = "general_analysis"
    prepared, error = _prepare_agent_data(df)
    if error:
        return _result(intent, error, {"基础指标": pd.DataFrame()})

    metrics = calculate_health_metrics(prepared)
    answer = (
        f"当前共有 {metrics['total_reviews']} 条有效评论，平均评分 {metrics['average_rating']}，"
        f"差评占比 {metrics['negative_ratio']}%，平均情绪指数 {metrics['average_sentiment']}。\n\n"
        "可以继续提问：差评集中问题、高风险评论、用户喜欢的功能、版本对比、"
        "最近趋势、产品优化建议或完整分析报告。"
    )
    return _result(intent, answer, {"基础指标": _metrics_dataframe(metrics)})


WORKFLOWS = {
    "negative_review_analysis": run_negative_review_analysis,
    "risk_review_analysis": run_risk_review_analysis,
    "positive_review_analysis": run_positive_review_analysis,
    "version_analysis": run_version_analysis,
    "trend_analysis": run_trend_analysis,
    "product_suggestion": run_product_suggestion,
    "report_generation": run_report_generation,
    "general_analysis": run_general_analysis,
}


def run_agent(question, df, ai_insights=None, scope="完整上传数据"):
    intent = detect_intent(question)
    workflow = WORKFLOWS.get(intent, run_general_analysis)
    if intent in {
        "negative_review_analysis",
        "product_suggestion",
        "report_generation",
        "general_analysis",
    }:
        result = workflow(question, df, ai_insights=ai_insights)
    else:
        result = workflow(question, df)

    sample_size = len(df) if isinstance(df, pd.DataFrame) else 0
    normalized_scope = (
        "当前筛选结果" if scope == "当前筛选结果" else "完整上传数据"
    )
    if normalized_scope == "当前筛选结果":
        prefix = f"以下结论基于当前筛选后的 {sample_size} 条评论。"
    else:
        prefix = f"以下结论基于完整数据，共 {sample_size} 条评论。"
    result["answer"] = f"{prefix}\n\n{result['answer']}"
    result["meta"] = {"scope": normalized_scope, "sample_size": sample_size}
    return result
