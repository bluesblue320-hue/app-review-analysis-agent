"""CSV validation and preprocessing shared by storage implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import pandas as pd

from backend.core.exceptions import (
    InvalidDatasetError,
    UnsupportedFileTypeError,
    UploadTooLargeError,
)
from review_fields import CONTENT_COLUMN, RATING_COLUMN, REQUIRED_REVIEW_COLUMNS
from review_preprocessing import preprocess_reviews
from visual_analysis import prepare_dashboard_data

SUPPORTED_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")

INVALID_RATING_REASON = "invalid_rating"
EMPTY_CONTENT_REASON = "empty_content"


@dataclass(frozen=True)
class IngestionStats:
    original_rows: int = 0
    valid_rows: int = 0
    removed_rows: int = 0
    invalid_rating_rows: int = 0
    invalid_reasons: dict[str, int] = field(default_factory=dict)


def parse_and_prepare_dataset(
    filename: str,
    content: bytes,
    settings,
) -> tuple[pd.DataFrame, pd.DataFrame, IngestionStats]:
    if Path(filename or "").suffix.lower() != ".csv":
        raise UnsupportedFileTypeError()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise UploadTooLargeError(settings.max_upload_size_mb)
    if not content:
        raise InvalidDatasetError("CSV 文件为空。")

    raw_dataframe: pd.DataFrame | None = None
    parse_errors: list[str] = []
    for encoding in SUPPORTED_ENCODINGS:
        try:
            candidate = pd.read_csv(BytesIO(content), encoding=encoding)
        except pd.errors.EmptyDataError as exc:
            raise InvalidDatasetError("CSV 文件为空或不包含字段。") from exc
        except (pd.errors.ParserError, UnicodeDecodeError) as exc:
            parse_errors.append(f"{encoding}: {exc}")
            continue
        raw_dataframe = candidate
        if set(candidate.columns) >= REQUIRED_REVIEW_COLUMNS:
            break

    if raw_dataframe is None:
        detail = parse_errors[-1] if parse_errors else "未知解析错误"
        raise InvalidDatasetError(f"CSV 文件无法解析：{detail}")

    if len(raw_dataframe.columns) > settings.max_dataset_columns:
        raise InvalidDatasetError(
            f"CSV 字段数不能超过 {settings.max_dataset_columns} 列。"
        )
    if len(raw_dataframe) > settings.max_dataset_rows:
        raise InvalidDatasetError(
            f"CSV 评论数不能超过 {settings.max_dataset_rows} 行。"
        )

    missing_columns = REQUIRED_REVIEW_COLUMNS - set(raw_dataframe.columns)
    if missing_columns:
        missing = "、".join(sorted(missing_columns))
        raise InvalidDatasetError(f"CSV 缺少必要列：{missing}")

    review_text = raw_dataframe[CONTENT_COLUMN].fillna("").astype(str)
    too_long = review_text.str.len() > settings.max_review_text_chars
    if bool(too_long.any()):
        first_row = int(too_long[too_long].index[0]) + 2
        raise InvalidDatasetError(
            f"第 {first_row} 行评论超过 {settings.max_review_text_chars} 个字符。"
        )

    processed = preprocess_reviews(raw_dataframe)
    prepared = prepare_dashboard_data(processed)
    stats = _build_ingestion_stats(raw_dataframe, prepared)
    return raw_dataframe, prepared, stats


def _build_ingestion_stats(
    raw_dataframe: pd.DataFrame,
    prepared: pd.DataFrame,
) -> IngestionStats:
    """Count rows dropped during strict rating validation and content checks.

    Ratings that cannot be parsed or fall outside 1..5 are counted as
    ``invalid_rating``; blank content rows are counted as ``empty_content``.
    """
    reasons: dict[str, int] = {}

    raw_content = raw_dataframe[CONTENT_COLUMN].fillna("").astype(str).str.strip()
    empty_count = int((raw_content == "").sum())
    if empty_count:
        reasons[EMPTY_CONTENT_REASON] = empty_count

    numeric_ratings = pd.to_numeric(
        raw_dataframe[RATING_COLUMN],
        errors="coerce",
    )
    invalid_rating_count = int(
        numeric_ratings.isna().sum()
        + ((~numeric_ratings.isna()) & (~numeric_ratings.between(1, 5))).sum()
    )
    if invalid_rating_count:
        reasons[INVALID_RATING_REASON] = invalid_rating_count

    original_rows = int(len(raw_dataframe))
    valid_rows = int(len(prepared))
    return IngestionStats(
        original_rows=original_rows,
        valid_rows=valid_rows,
        removed_rows=original_rows - valid_rows,
        invalid_rating_rows=invalid_rating_count,
        invalid_reasons=reasons,
    )
