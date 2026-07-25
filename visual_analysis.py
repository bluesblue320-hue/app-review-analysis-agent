import re

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


RATING_COLUMN = "评分"
CONTENT_COLUMN = "内容"
SENTIMENT_COLUMN = "情绪指数"
TOKEN_COLUMN = "分词内容"
CATEGORY_COLUMN = "问题类型"
RISK_LABEL_COLUMN = "风险标签"

ISSUE_KEYWORDS = {
    "账号类": ["封号", "禁言", "限流", "实名", "申诉", "账号", "登录", "注销"],
    "审核类": ["审核", "违规", "举报", "笔记", "内容规则", "误判"],
    "客服类": ["客服", "人工", "反馈", "没人处理", "无人处理", "回复"],
    "体验类": ["卡顿", "闪退", "加载", "广告", "推荐", "崩溃", "发热"],
    "内容类": ["搜索", "内容", "社区", "种草", "质量", "博主"],
}

HIGH_SEVERITY_SENTIMENT = 20
LOW_SENTIMENT = 30
NEGATIVE_RATING_MAX = 3


def classify_issue(text):
    content = str(text or "")
    for category, keywords in ISSUE_KEYWORDS.items():
        if any(keyword in content for keyword in keywords):
            return category
    return "其他类"


def build_risk_label(row):
    labels = []
    rating = float(row.get(RATING_COLUMN, 0) or 0)
    sentiment = float(row.get(SENTIMENT_COLUMN, 50) or 50)

    if rating <= 2:
        labels.append("低星差评")
    if sentiment <= HIGH_SEVERITY_SENTIMENT:
        labels.append("极端负面")
    if rating >= 4 and sentiment < LOW_SENTIMENT:
        labels.append("高星低情绪")

    return "、".join(labels) if labels else "正常"


def is_high_risk_label(label):
    return str(label or "") != "正常"


def prepare_dashboard_data(df):
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                RATING_COLUMN,
                CONTENT_COLUMN,
                SENTIMENT_COLUMN,
                CATEGORY_COLUMN,
                RISK_LABEL_COLUMN,
            ]
        )

    required_columns = {RATING_COLUMN, CONTENT_COLUMN}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        missing = "、".join(sorted(missing_columns))
        raise ValueError(f"缺少必要列：{missing}")

    prepared = df.copy()
    prepared[CONTENT_COLUMN] = prepared[CONTENT_COLUMN].fillna("").astype(str).str.strip()
    prepared = prepared[prepared[CONTENT_COLUMN] != ""].copy()
    prepared[RATING_COLUMN] = pd.to_numeric(prepared[RATING_COLUMN], errors="coerce")
    prepared = prepared.dropna(subset=[RATING_COLUMN]).copy()

    if SENTIMENT_COLUMN not in prepared.columns:
        prepared[SENTIMENT_COLUMN] = 50.0

    prepared[SENTIMENT_COLUMN] = (
        pd.to_numeric(prepared[SENTIMENT_COLUMN], errors="coerce")
        .fillna(50.0)
        .clip(lower=0, upper=100)
    )

    prepared[CATEGORY_COLUMN] = prepared[CONTENT_COLUMN].apply(classify_issue)
    prepared[RISK_LABEL_COLUMN] = prepared.apply(build_risk_label, axis=1)
    return prepared


def calculate_health_metrics(df):
    if df is None or df.empty:
        return {
            "total_reviews": 0,
            "average_rating": 0.0,
            "negative_ratio": 0.0,
            "average_sentiment": 0.0,
            "high_risk_count": 0,
        }

    total_reviews = int(len(df))
    negative_count = int((df[RATING_COLUMN] <= NEGATIVE_RATING_MAX).sum())
    high_risk_count = int(df[RISK_LABEL_COLUMN].apply(is_high_risk_label).sum())

    return {
        "total_reviews": total_reviews,
        "average_rating": round(float(df[RATING_COLUMN].mean()), 2),
        "negative_ratio": round(negative_count / total_reviews * 100, 2),
        "average_sentiment": round(float(df[SENTIMENT_COLUMN].mean()), 2),
        "high_risk_count": high_risk_count,
    }


def filter_reviews(
    df,
    rating_range=(1, 5),
    sentiment_range=(0, 100),
    categories=None,
    keyword="",
    high_risk_only=False,
):
    if df is None or df.empty:
        return pd.DataFrame(columns=df.columns if df is not None else [])

    filtered = df.copy()
    min_rating, max_rating = rating_range
    min_sentiment, max_sentiment = sentiment_range

    filtered = filtered[
        filtered[RATING_COLUMN].between(min_rating, max_rating)
        & filtered[SENTIMENT_COLUMN].between(min_sentiment, max_sentiment)
    ].copy()

    if categories is not None:
        filtered = filtered[filtered[CATEGORY_COLUMN].isin(categories)].copy()

    keyword = str(keyword or "").strip()
    if keyword:
        filtered = filtered[
            filtered[CONTENT_COLUMN].str.contains(re.escape(keyword), case=False, na=False)
        ].copy()

    if high_risk_only:
        filtered = filtered[filtered[RISK_LABEL_COLUMN].apply(is_high_risk_label)].copy()

    return filtered


AI_SEVERITY_SCORES = {
    "high": 100.0,
    "medium": 60.0,
    "low": 25.0,
}

PRIORITY_WEIGHTS = {
    "volume": 0.35,
    "sentiment": 0.25,
    "rating": 0.20,
    "ai": 0.15,
    "risk": 0.05,
}


def severity_label(score):
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def build_ai_category_map(ai_insights):
    category_map = {}
    if not ai_insights:
        return category_map
    if not isinstance(ai_insights, dict):
        return category_map

    pain_points = ai_insights.get("pain_points", [])
    if not isinstance(pain_points, list):
        return category_map

    for item in pain_points:
        if not isinstance(item, dict):
            continue

        text = " ".join(
            str(item.get(key, ""))
            for key in ("name", "explanation", "suggestion")
            if item.get(key)
        )
        category = classify_issue(text)
        severity = AI_SEVERITY_SCORES.get(str(item.get("severity", "")).lower(), 50.0)
        suggestion = str(item.get("suggestion") or "")

        current = category_map.get(category)
        if current is None or severity > current["severity_score"]:
            category_map[category] = {
                "severity_score": severity,
                "suggestion": suggestion,
            }

    return category_map


def representative_review(group):
    if group.empty:
        return ""

    sorted_group = group.sort_values([RATING_COLUMN, SENTIMENT_COLUMN], ascending=[True, True])
    return str(sorted_group.iloc[0][CONTENT_COLUMN])


def calculate_priority_table(df, ai_insights=None, top_n=5):
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                CATEGORY_COLUMN,
                "优先级分数",
                "严重程度",
                "相关评论数",
                "平均评分",
                "平均情绪指数",
                "AI严重度",
                "AI建议",
                "代表评论",
            ]
        )

    ai_category_map = build_ai_category_map(ai_insights)
    total_negative = max(int((df[RATING_COLUMN] <= NEGATIVE_RATING_MAX).sum()), 1)
    rows = []

    for category, group in df.groupby(CATEGORY_COLUMN):
        negative_count = int((group[RATING_COLUMN] <= NEGATIVE_RATING_MAX).sum())
        high_risk_count = int(group[RISK_LABEL_COLUMN].apply(is_high_risk_label).sum())
        average_rating = float(group[RATING_COLUMN].mean())
        average_sentiment = float(group[SENTIMENT_COLUMN].mean())

        volume_score = min(negative_count / total_negative, 1.0) * 100
        sentiment_score = max(0.0, min(100.0, 100 - average_sentiment))
        rating_score = max(0.0, min(100.0, (5 - average_rating) / 4 * 100))
        ai_data = ai_category_map.get(category, {"severity_score": 50.0, "suggestion": ""})
        ai_score = ai_data["severity_score"]
        risk_score = high_risk_count / max(len(group), 1) * 100

        priority_score = (
            volume_score * PRIORITY_WEIGHTS["volume"]
            + sentiment_score * PRIORITY_WEIGHTS["sentiment"]
            + rating_score * PRIORITY_WEIGHTS["rating"]
            + ai_score * PRIORITY_WEIGHTS["ai"]
            + risk_score * PRIORITY_WEIGHTS["risk"]
        )

        rows.append(
            {
                CATEGORY_COLUMN: category,
                "优先级分数": round(priority_score, 2),
                "严重程度": severity_label(priority_score),
                "相关评论数": int(len(group)),
                "平均评分": round(average_rating, 2),
                "平均情绪指数": round(average_sentiment, 2),
                "AI严重度": round(ai_score, 2),
                "AI建议": ai_data["suggestion"],
                "代表评论": representative_review(group),
            }
        )

    priority = pd.DataFrame(rows)
    if priority.empty:
        return priority

    return priority.sort_values("优先级分数", ascending=False).head(top_n).reset_index(drop=True)


def rating_distribution(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=[RATING_COLUMN, "评论数"])

    distribution = (
        df[RATING_COLUMN]
        .round()
        .astype(int)
        .value_counts()
        .sort_index()
        .rename_axis(RATING_COLUMN)
        .reset_index(name="评论数")
    )
    return distribution


def sentiment_distribution(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["情绪区间", "评论数"])

    bins = [0, 20, 40, 60, 80, 100]
    labels = ["0-20", "21-40", "41-60", "61-80", "81-100"]
    bucket = pd.cut(
        df[SENTIMENT_COLUMN],
        bins=bins,
        labels=labels,
        include_lowest=True,
        right=True,
    )
    distribution = bucket.value_counts(sort=False).rename_axis("情绪区间").reset_index(name="评论数")
    distribution["情绪区间"] = distribution["情绪区间"].astype(str)
    return distribution


def sentiment_scatter_data(df):
    columns = [RATING_COLUMN, SENTIMENT_COLUMN, CATEGORY_COLUMN, RISK_LABEL_COLUMN, CONTENT_COLUMN]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    return df[columns].copy()


def extract_keyword_scores(text_series, top_n=15):
    empty_result = pd.DataFrame(columns=["关键词", "权重"])
    if text_series is None or text_series.empty:
        return empty_result

    clean_series = text_series.fillna("").astype(str)
    clean_series = clean_series[clean_series.str.strip() != ""]
    if clean_series.empty:
        return empty_result

    vectorizer = TfidfVectorizer(max_features=500)
    try:
        tfidf_matrix = vectorizer.fit_transform(clean_series)
    except ValueError:
        return empty_result
    words = vectorizer.get_feature_names_out()
    scores = tfidf_matrix.sum(axis=0).A1

    keyword_df = (
        pd.DataFrame({"关键词": words, "权重": scores})
        .sort_values("权重", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    keyword_df["权重"] = keyword_df["权重"].round(4)
    return keyword_df


def sentiment_trend(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["日期", "平均情绪指数", "平均评分", "评论数"])

    time_column = None
    for candidate in ["时间", "日期", "评论时间", "发布时间"]:
        if candidate in df.columns:
            time_column = candidate
            break

    if time_column is None:
        return pd.DataFrame(columns=["日期", "平均情绪指数", "平均评分", "评论数"])

    trend_df = df.copy()
    trend_df["日期"] = pd.to_datetime(trend_df[time_column], errors="coerce").dt.date
    trend_df = trend_df.dropna(subset=["日期"])
    if trend_df.empty:
        return pd.DataFrame(columns=["日期", "平均情绪指数", "平均评分", "评论数"])

    return (
        trend_df.groupby("日期")
        .agg(
            平均情绪指数=(SENTIMENT_COLUMN, "mean"),
            平均评分=(RATING_COLUMN, "mean"),
            评论数=(CONTENT_COLUMN, "count"),
        )
        .reset_index()
        .round({"平均情绪指数": 2, "平均评分": 2})
    )
