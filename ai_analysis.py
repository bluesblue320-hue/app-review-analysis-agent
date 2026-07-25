import json
import os
import re
from pathlib import Path

import pandas as pd
import requests


DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-v4-flash"
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
REQUIRED_COLUMNS = {"评分", "内容"}


class AiAnalysisError(Exception):
    """Raised when AI analysis cannot be completed safely."""


def load_env_file(path=".env"):
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_ai_config():
    load_env_file()
    provider = os.getenv("AI_PROVIDER", DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
    model = os.getenv("AI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return {
        "provider": provider,
        "model": model,
        "api_key": os.getenv("DEEPSEEK_API_KEY", "").strip(),
        "base_url": DEEPSEEK_CHAT_URL,
    }


def parse_json_content(content):
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise AiAnalysisError("AI 返回内容不是有效 JSON，请稍后重试。") from exc


def _as_list(value):
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def normalize_insights(data):
    if not isinstance(data, dict):
        raise AiAnalysisError("AI 返回结构异常，请稍后重试。")

    return {
        "summary": str(data.get("summary") or "暂无 AI 总览。"),
        "pain_points": _as_list(data.get("pain_points")),
        "delighters": _as_list(data.get("delighters")),
        "sentiment_drivers": _as_list(data.get("sentiment_drivers")),
        "high_risk_reviews": _as_list(data.get("high_risk_reviews")),
        "recommendations": _as_list(data.get("recommendations")),
        "report_copy": str(data.get("report_copy") or ""),
    }


def build_review_packet(df, max_reviews=100):
    missing_columns = REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        missing = "、".join(sorted(missing_columns))
        raise AiAnalysisError(f"CSV 缺少必要列：{missing}")

    clean_df = df.copy()
    clean_df["内容"] = clean_df["内容"].fillna("").astype(str).str.strip()
    clean_df = clean_df[clean_df["内容"] != ""].copy()
    clean_df["评分"] = pd.to_numeric(clean_df["评分"], errors="coerce")
    clean_df = clean_df.dropna(subset=["评分"])

    if clean_df.empty:
        raise AiAnalysisError("没有可分析的有效评论。")

    review_limit = max(1, int(max_reviews))
    negative_limit = max(1, review_limit // 2)
    positive_limit = max(1, review_limit // 4)
    mismatch_limit = max(0, review_limit - negative_limit - positive_limit)

    negative_pool = clean_df.sort_values(["评分"], ascending=True).head(negative_limit)
    positive_pool = clean_df.sort_values(["评分"], ascending=False).head(positive_limit)
    pools = [negative_pool, positive_pool]

    if mismatch_limit and "情绪指数" in clean_df.columns:
        scored_df = clean_df.copy()
        scored_df["情绪指数"] = pd.to_numeric(scored_df["情绪指数"], errors="coerce")
        mismatch_pool = scored_df[(scored_df["评分"] >= 4) & (scored_df["情绪指数"] < 30)]
        pools.append(mismatch_pool.sort_values(["情绪指数"], ascending=True).head(mismatch_limit))

    selected = pd.concat(pools).drop_duplicates().head(review_limit)
    include_columns = [col for col in ["评分", "情绪指数", "标题", "内容", "版本", "时间"] if col in selected.columns]
    reviews = []
    for row in selected[include_columns].to_dict(orient="records"):
        reviews.append({key: value for key, value in row.items() if pd.notna(value)})

    rating_distribution = {
        str(int(rating)): int(count)
        for rating, count in clean_df["评分"].round().astype(int).value_counts().sort_index().items()
    }

    packet = {
        "metrics": {
            "total_reviews": int(len(clean_df)),
            "average_rating": round(float(clean_df["评分"].mean()), 2),
            "rating_distribution": rating_distribution,
        },
        "reviews": reviews,
    }

    if "情绪指数" in clean_df.columns:
        sentiment = pd.to_numeric(clean_df["情绪指数"], errors="coerce").dropna()
        if not sentiment.empty:
            packet["metrics"]["average_sentiment"] = round(float(sentiment.mean()), 2)

    return packet


def build_messages(review_packet):
    system_prompt = (
        "你是一名中文产品经理和舆情分析师，擅长从 App Store 评论中提炼产品问题、"
        "用户情绪归因、风险评论和可执行建议。请只基于用户提供的数据分析，"
        "不要编造未提供的统计数据。必须输出严格 JSON，不要输出 Markdown。"
    )
    user_prompt = {
        "task": "分析小红书 App Store 评论，输出结构化舆情洞察。",
        "output_schema": {
            "summary": "舆情总览，中文字符串",
            "pain_points": [
                {
                    "name": "槽点类别",
                    "severity": "high | medium | low",
                    "evidence": ["代表性原声"],
                    "explanation": "用户不满原因",
                    "suggestion": "产品或运营建议",
                }
            ],
            "delighters": [
                {
                    "name": "爽点类别",
                    "evidence": ["代表性原声"],
                    "explanation": "用户喜欢原因",
                }
            ],
            "sentiment_drivers": ["情绪背后的主要因素"],
            "high_risk_reviews": [
                {"rating": 1, "content": "评论原文", "risk_reason": "风险原因"}
            ],
            "recommendations": ["具体改进建议"],
            "report_copy": "可直接复制进汇报的一段中文总结",
        },
        "review_packet": review_packet,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
    ]


def call_deepseek(messages, config, post_func=requests.post, timeout=60):
    if config["provider"] != "deepseek":
        raise AiAnalysisError(f"暂不支持 AI_PROVIDER={config['provider']}。")
    if not config["api_key"]:
        raise AiAnalysisError("未检测到 DEEPSEEK_API_KEY，请先配置 API Key。")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    }
    payload = {
        "model": config["model"],
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 4000,
        "stream": False,
        "thinking": {"type": "disabled"},
    }

    try:
        response = post_func(config["base_url"], headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise AiAnalysisError(f"DeepSeek 请求失败：{exc}") from exc

    if response.status_code != 200:
        raise AiAnalysisError(f"DeepSeek 返回异常状态码 {response.status_code}：{response.text}")

    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AiAnalysisError("DeepSeek 返回结构异常，请稍后重试。") from exc


def analyze_reviews(df, post_func=requests.post, max_reviews=100):
    config = load_ai_config()
    review_packet = build_review_packet(df, max_reviews=max_reviews)
    messages = build_messages(review_packet)
    content = call_deepseek(messages, config, post_func=post_func)
    return normalize_insights(parse_json_content(content))
