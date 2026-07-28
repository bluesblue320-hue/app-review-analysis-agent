"""Shared text preprocessing and sentiment analysis for review data."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Collection
from typing import Any

import jieba.posseg as pseg
import pandas as pd
from snownlp import SnowNLP

from review_fields import CONTENT_COLUMN, SENTIMENT_COLUMN, TOKEN_COLUMN


logger = logging.getLogger(__name__)

DEFAULT_SENTIMENT_SCORE = 50.0
DEFAULT_STOP_WORDS = frozenset(
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
        "小红书",
        "软件",
        "非常",
        "可以",
        "不错",
        "不能",
    }
)

_EXPECTED_SENTIMENT_ERRORS = (
    TypeError,
    ValueError,
    IndexError,
    ZeroDivisionError,
    OverflowError,
)


def clean_and_tokenize(
    text: object,
    *,
    stop_words: Collection[str] = DEFAULT_STOP_WORDS,
) -> str:
    """Keep useful Chinese nouns, verbs and adjectives as space-separated tokens."""
    chinese_text = re.sub(r"[^\u4e00-\u9fa5]", "", str(text))
    words = pseg.lcut(chinese_text)
    useful_words = [
        word
        for word, flag in words
        if len(word) > 1
        and word not in stop_words
        and (flag.startswith("n") or flag.startswith("v") or flag.startswith("a"))
    ]
    return " ".join(useful_words)


def calculate_sentiment(
    text: object,
    *,
    analyzer_factory: Callable[[str], Any] = SnowNLP,
    neutral_short_text: bool = False,
) -> float:
    """Return the SnowNLP sentiment score on the existing 0-100 scale.

    Known invalid-input/model arithmetic failures retain the historical neutral
    fallback. Unexpected programming errors are deliberately allowed to surface.
    """
    normalized_text = str(text)
    if neutral_short_text and len(normalized_text.strip()) < 2:
        return DEFAULT_SENTIMENT_SCORE

    try:
        sentiment = analyzer_factory(normalized_text).sentiments
        return round(float(sentiment) * 100, 2)
    except _EXPECTED_SENTIMENT_ERRORS as exc:
        logger.warning(
            "Sentiment analysis failed; using neutral fallback (error_type=%s)",
            type(exc).__name__,
        )
        return DEFAULT_SENTIMENT_SCORE


def preprocess_reviews(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add token and sentiment columns without modifying the caller's DataFrame."""
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame")
    if CONTENT_COLUMN not in dataframe.columns:
        raise ValueError(f"缺少必要列：{CONTENT_COLUMN}")

    processed = dataframe.copy()
    processed[TOKEN_COLUMN] = processed[CONTENT_COLUMN].apply(clean_and_tokenize)
    processed[SENTIMENT_COLUMN] = processed[CONTENT_COLUMN].apply(calculate_sentiment)
    return processed
