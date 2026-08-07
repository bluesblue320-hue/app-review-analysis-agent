"""Strict rating validation and ingestion stats for dataset uploads."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.core.config import load_settings
from backend.services.dataset_ingestion import (
    EMPTY_CONTENT_REASON,
    INVALID_RATING_REASON,
    parse_and_prepare_dataset,
)
from review_fields import CONTENT_COLUMN, RATING_COLUMN


def _csv_bytes(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(index=False).encode("utf-8")


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def test_valid_ratings_1_to_5_are_kept(settings) -> None:
    raw = pd.DataFrame(
        {
            RATING_COLUMN: [1, 2, 3, 4, 5],
            CONTENT_COLUMN: ["a", "b", "c", "d", "e"],
        }
    )
    _, prepared, stats = parse_and_prepare_dataset(
        "ratings.csv", _csv_bytes(raw), settings
    )
    assert len(prepared) == 5
    assert stats.valid_rows == 5
    assert stats.removed_rows == 0
    assert stats.invalid_rating_rows == 0
    assert stats.invalid_reasons == {}


def test_ratings_outside_1_to_5_are_removed_and_counted(settings) -> None:
    raw = pd.DataFrame(
        {
            RATING_COLUMN: [0, 6, 10, 3],
            CONTENT_COLUMN: ["zero", "six", "ten", "ok"],
        }
    )
    _, prepared, stats = parse_and_prepare_dataset(
        "ratings.csv", _csv_bytes(raw), settings
    )
    assert len(prepared) == 1
    assert stats.original_rows == 4
    assert stats.valid_rows == 1
    assert stats.removed_rows == 3
    assert stats.invalid_rating_rows == 3
    assert stats.invalid_reasons[INVALID_RATING_REASON] == 3


def test_unparseable_and_blank_ratings_are_removed(settings) -> None:
    raw = pd.DataFrame(
        {
            RATING_COLUMN: ["abc", None, "", 5],
            CONTENT_COLUMN: ["bad", "blank rating", "also blank", "ok"],
        }
    )
    _, prepared, stats = parse_and_prepare_dataset(
        "ratings.csv", _csv_bytes(raw), settings
    )
    assert len(prepared) == 1
    assert stats.invalid_rating_rows == 3
    assert stats.invalid_reasons[INVALID_RATING_REASON] == 3


def test_blank_content_rows_are_removed_and_counted(settings) -> None:
    raw = pd.DataFrame(
        {
            RATING_COLUMN: [5, 4, 3],
            CONTENT_COLUMN: ["ok", "", "   "],
        }
    )
    _, prepared, stats = parse_and_prepare_dataset(
        "ratings.csv", _csv_bytes(raw), settings
    )
    assert len(prepared) == 1
    assert stats.removed_rows == 2
    assert stats.invalid_reasons[EMPTY_CONTENT_REASON] == 2
    assert INVALID_RATING_REASON not in stats.invalid_reasons


def test_mixed_reasons_are_counted_independently(settings) -> None:
    raw = pd.DataFrame(
        {
            RATING_COLUMN: [0, 5, "x", 4],
            CONTENT_COLUMN: ["low rating", "", "bad rating", "ok"],
        }
    )
    _, prepared, stats = parse_and_prepare_dataset(
        "ratings.csv", _csv_bytes(raw), settings
    )
    assert len(prepared) == 1
    assert stats.invalid_rating_rows == 2
    assert stats.invalid_reasons[INVALID_RATING_REASON] == 2
    assert stats.invalid_reasons[EMPTY_CONTENT_REASON] == 1
    assert stats.removed_rows == 3


def test_ingestion_stats_never_use_clip(settings) -> None:
    """Out-of-range ratings must be dropped, never clipped into 1..5."""
    raw = pd.DataFrame(
        {
            RATING_COLUMN: [0, 5.5, 5],
            CONTENT_COLUMN: ["zero", "over five", "ok"],
        }
    )
    _, prepared, stats = parse_and_prepare_dataset(
        "ratings.csv", _csv_bytes(raw), settings
    )
    assert stats.invalid_rating_rows == 2
    assert len(prepared) == 1
    assert prepared[RATING_COLUMN].tolist() == [5.0]
