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
    app_env: str = "development"
    access_token: str = ""
    database_url: str = "sqlite:///./data/app.db"
    storage_backend: str = "memory"
    redis_url: str = ""
    cache_ttl_seconds: int = 300
    data_retention_days: int = 30
    max_upload_size_mb: int = 10
    max_dataset_rows: int = 10_000
    max_dataset_columns: int = 50
    max_review_text_chars: int = 5_000
    max_summary_review_rows: int = 100
    llm_timeout_seconds: int = 60
    llm_max_tool_calls: int = 3
    agent_adapter: str = "direct"
    enable_docs: bool = True
    # Alembic locations relative to the project root (ready-check migration).
    alembic_config_path: str = "alembic.ini"
    alembic_script_location: str = "alembic"


def load_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development").strip().lower() or "development"
    access_token = os.getenv("APP_ACCESS_TOKEN", "").strip()
    if app_env == "production" and not access_token:
        raise ValueError("APP_ACCESS_TOKEN is required when APP_ENV=production")
    default_storage = "database" if app_env == "production" else "memory"
    storage_backend = os.getenv("STORAGE_BACKEND", default_storage).strip().lower()
    if storage_backend not in {"memory", "database"}:
        raise ValueError("STORAGE_BACKEND must be memory or database")
    raw_enable_docs = (
        os.getenv(
            "ENABLE_DOCS",
            "false" if app_env == "production" else "true",
        )
        .strip()
        .lower()
    )
    if raw_enable_docs not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError("ENABLE_DOCS must be a boolean")
    return Settings(
        app_env=app_env,
        access_token=access_token,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/app.db").strip(),
        storage_backend=storage_backend,
        redis_url=os.getenv("REDIS_URL", "").strip(),
        cache_ttl_seconds=_positive_int_from_env("CACHE_TTL_SECONDS", 300),
        data_retention_days=_positive_int_from_env("DATA_RETENTION_DAYS", 30),
        max_upload_size_mb=_positive_int_from_env("MAX_UPLOAD_SIZE_MB", 10),
        max_dataset_rows=_positive_int_from_env("MAX_DATASET_ROWS", 10_000),
        max_dataset_columns=_positive_int_from_env("MAX_DATASET_COLUMNS", 50),
        max_review_text_chars=_positive_int_from_env("MAX_REVIEW_TEXT_CHARS", 5_000),
        max_summary_review_rows=_positive_int_from_env(
            "MAX_SUMMARY_REVIEW_ROWS",
            100,
        ),
        llm_timeout_seconds=_positive_int_from_env("LLM_TIMEOUT_SECONDS", 60),
        llm_max_tool_calls=min(
            _positive_int_from_env("LLM_MAX_TOOL_CALLS", 3),
            3,
        ),
        agent_adapter=_validated_adapter(
            os.getenv("AGENT_ADAPTER", "direct").strip().lower()
        ),
        enable_docs=raw_enable_docs in {"true", "1", "yes"},
    )


def _validated_adapter(raw_adapter: str) -> str:
    if raw_adapter not in {"direct", "langchain"}:
        raise ValueError("AGENT_ADAPTER must be direct or langchain")
    return raw_adapter


settings = load_settings()
