"""Small environment-backed configuration for the in-process API."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True)
class Settings:
    service_name: str = "app-review-analysis-agent"
    api_prefix: str = "/api/v1"
    max_upload_size_mb: int = 10
    max_summary_review_rows: int = 100
    llm_timeout_seconds: int = 60
    llm_max_tool_calls: int = 3


def load_settings() -> Settings:
    return Settings(
        max_upload_size_mb=_positive_int_from_env("MAX_UPLOAD_SIZE_MB", 10),
        max_summary_review_rows=_positive_int_from_env(
            "MAX_SUMMARY_REVIEW_ROWS",
            100,
        ),
        llm_timeout_seconds=_positive_int_from_env("LLM_TIMEOUT_SECONDS", 60),
        llm_max_tool_calls=min(
            _positive_int_from_env("LLM_MAX_TOOL_CALLS", 3),
            3,
        ),
    )


settings = load_settings()
