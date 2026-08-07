"""Offline NLP report CLI built on the same logic as the Streamlit workflow.

Importing this module is side-effect free. Run ``python nlp_analysis.py`` to
read the legacy CSV input and generate the existing offline report artifacts.
"""

from __future__ import annotations

import jieba
import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import WordCloud

from review_fields import (
    CONTENT_COLUMN,
    RATING_COLUMN,
    REQUIRED_REVIEW_COLUMNS,
    SENTIMENT_COLUMN,
    TOKEN_COLUMN,
)
from review_preprocessing import calculate_sentiment as calculate_sentiment_score
from review_preprocessing import clean_and_tokenize
from visual_analysis import extract_keyword_scores

INPUT_FILE = "xiaohongshu_reviews.csv"
OUTPUT_FILE = "xiaohongshu_reviews_with_sentiment.csv"
BAD_WORDCLOUD_FILE = "bad_reviews_wordcloud.html"
GOOD_WORDCLOUD_FILE = "good_reviews_wordcloud.html"

FORCED_WORDS = (
    "封号",
    "无故封号",
    "人工客服",
    "客服",
    "无故禁言",
    "禁言",
    "限流",
    "账号封禁",
    "实名认证",
    "恶意举报",
    "内容审核",
    "社区规范",
    "笔记违规",
    "敏感词",
)

BASE_STOP_WORDS = frozenset(
    {
        "的",
        "了",
        "是",
        "在",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "着",
        "没有",
        "看",
        "好",
        "自己",
        "这",
        "什么",
        "怎么",
        "还是",
        "那个",
        "这个",
        "真的",
        "太",
    }
)
BUSINESS_STOP_WORDS = frozenset(
    {
        "小红书",
        "软件",
        "非常",
        "可以",
        "不错",
        "不能",
        "希望",
        "喜欢",
        "垃圾",
        "无缘无故",
        "莫名其妙",
    }
)
OFFLINE_STOP_WORDS = BASE_STOP_WORDS | BUSINESS_STOP_WORDS


def register_forced_words() -> None:
    """Register the legacy domain phrases before offline tokenization."""
    for word in FORCED_WORDS:
        jieba.add_word(word, freq=999999)


def advanced_clean_and_cut(text: object) -> str:
    """Preserve the legacy offline stop-word policy using shared tokenization."""
    return clean_and_tokenize(text, stop_words=OFFLINE_STOP_WORDS)


def extract_top_keywords(
    text_series: pd.Series,
    top_n: int = 10,
) -> list[tuple[str, float]]:
    """Return the legacy unigram/bigram TF-IDF result shape."""
    keyword_scores = extract_keyword_scores(
        text_series,
        top_n=top_n,
        max_features=1000,
        ngram_range=(1, 2),
        round_digits=None,
    )
    return [
        (str(row["关键词"]), float(row["权重"]))
        for row in keyword_scores.to_dict(orient="records")
    ]


def calculate_sentiment(text: object) -> float:
    """Preserve the offline script's neutral handling for very short text."""
    return calculate_sentiment_score(text, neutral_short_text=True)


def _load_reviews(path: str) -> pd.DataFrame:
    try:
        dataframe = pd.read_csv(path)
    except FileNotFoundError:
        raise FileNotFoundError(
            "找不到 CSV 文件，请确保爬虫已成功运行并生成了文件。"
        ) from None
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise ValueError(f"CSV 文件无法解析：{exc}") from exc

    missing_columns = REQUIRED_REVIEW_COLUMNS - set(dataframe.columns)
    if missing_columns:
        missing = "、".join(sorted(missing_columns))
        raise ValueError(f"CSV 缺少必要列：{missing}")
    return dataframe


def _render_wordclouds(
    negative_keywords: list[tuple[str, float]],
    positive_keywords: list[tuple[str, float]],
) -> None:
    negative_cloud = (
        WordCloud()
        .add("", negative_keywords, word_size_range=[20, 100], shape="diamond")
        .set_global_opts(
            title_opts=opts.TitleOpts(title="🚨 竞品核心槽点分析 (差评词云)")
        )
    )
    negative_cloud.render(BAD_WORDCLOUD_FILE)

    positive_cloud = (
        WordCloud()
        .add("", positive_keywords, word_size_range=[20, 100], shape="star")
        .set_global_opts(
            title_opts=opts.TitleOpts(title="✨ 竞品核心爽点分析 (好评词云)")
        )
    )
    positive_cloud.render(GOOD_WORDCLOUD_FILE)


def main() -> int:
    print("🚀 正在加载数据并加载分词组件...")
    try:
        dataframe = _load_reviews(INPUT_FILE)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}")
        return 1

    register_forced_words()
    print("🧹 正在进行带有【词性过滤】的高阶文本清洗（这可能需要几秒钟）...")
    dataframe[TOKEN_COLUMN] = dataframe[CONTENT_COLUMN].apply(advanced_clean_and_cut)

    negative_reviews = dataframe[dataframe[RATING_COLUMN] <= 3]
    positive_reviews = dataframe[dataframe[RATING_COLUMN] >= 4]
    negative_keywords = extract_top_keywords(negative_reviews[TOKEN_COLUMN], top_n=10)
    positive_keywords = extract_top_keywords(positive_reviews[TOKEN_COLUMN], top_n=10)

    print("\n📊 核心文本特征提取完成！\n")
    print("🚨 【低分差评 - 核心槽点 Top 10】:")
    for word, score in negative_keywords:
        print(f"   - 关键词: [{word}]  (权重: {score:.2f})")

    print("\n✨ 【高分好评 - 核心爽点 Top 10】:")
    for word, score in positive_keywords:
        print(f"   - 关键词: [{word}]  (权重: {score:.2f})")

    print("\n🎨 正在生成高逼格的交互式词云图...")
    _render_wordclouds(negative_keywords, positive_keywords)
    print("✅ 可视化报告已生成！")
    print(
        "👉 请在左侧文件目录中找到 [bad_reviews_wordcloud.html] 文件，"
        "右键选择在浏览器中打开 (Open in Browser)。"
    )

    print("\n🧠 正在启动 AI 情感计算引擎，逐句阅读评论并打分（这可能需要十几秒）...")
    dataframe[SENTIMENT_COLUMN] = dataframe[CONTENT_COLUMN].apply(calculate_sentiment)
    print("✅ 情感计算完成！")

    most_angry = dataframe.sort_values(by=SENTIMENT_COLUMN).head(3)
    print("\n🔥 【高能预警：全场情绪最愤怒的 3 条评论】")
    for _, row in most_angry.iterrows():
        print(
            f"[{row[RATING_COLUMN]}星 | 情绪指数: {row[SENTIMENT_COLUMN]}分] : "
            f"{row[CONTENT_COLUMN]}"
        )

    mismatched_reviews = dataframe[
        (dataframe[RATING_COLUMN] >= 4) & (dataframe[SENTIMENT_COLUMN] < 30)
    ]
    if not mismatched_reviews.empty:
        print("\n🕵️‍♂️ 【PM 洞察：发现星级与情绪严重错位的评论】")
        for _, row in mismatched_reviews.head(3).iterrows():
            print(
                f"[{row[RATING_COLUMN]}星 | 情绪指数: {row[SENTIMENT_COLUMN]}分] : "
                f"{row[CONTENT_COLUMN]}"
            )
    else:
        print("\n🕵️‍♂️ 【PM 洞察：未发现明显的星级与情绪错位评论。】")

    dataframe.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"\n📂 包含情绪得分的完整数据集已保存至: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
