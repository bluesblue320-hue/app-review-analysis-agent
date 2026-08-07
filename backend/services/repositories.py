"""Repository Protocols and shared scope-signature helpers.

Services depend only on these Protocols so unit tests can use the in-memory
implementations while production uses the SQLAlchemy/PostgreSQL repositories.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from backend.core.exceptions import DatasetNotFoundError
from backend.services.dataset_service import DatasetRecord
from backend.services.insight_store import InsightNotFoundError, InsightRecord
from backend.services.model_config import (
    DEFAULT_AI_MODEL,
    DEFAULT_AI_PROVIDER,
)

ANALYSIS_VERSION = "v1"


@runtime_checkable
class DatasetRepository(Protocol):
    def create(self, filename: str, content: bytes) -> DatasetRecord: ...
    def get(self, dataset_id: str) -> DatasetRecord: ...
    def delete(self, dataset_id: str) -> None: ...
    def cleanup_expired(self) -> int: ...
    def ready(self) -> bool: ...
    def clear(self) -> None: ...


@runtime_checkable
class InsightRepository(Protocol):
    def create(
        self,
        *,
        dataset_id: str,
        scope_signature: str,
        sample_size: int,
        insights: dict[str, Any],
        analysis_version: str = ANALYSIS_VERSION,
        provider: str = DEFAULT_AI_PROVIDER,
        model_name: str = DEFAULT_AI_MODEL,
    ) -> InsightRecord: ...
    def get(self, insight_id: str) -> InsightRecord: ...
    def resolve(
        self,
        *,
        insight_id: str | None,
        dataset_id: str,
        scope_signature: str,
        sample_size: int,
    ) -> tuple[dict[str, Any] | None, str | None]: ...
    def find_by_fingerprint(self, fingerprint: str) -> InsightRecord | None: ...
    def get_by_fingerprint(
        self, fingerprint: str, *, include_expired: bool = False
    ) -> InsightRecord | None: ...
    def upsert_fingerprint(
        self,
        *,
        fingerprint: str,
        dataset_id: str,
        scope_signature: str,
        sample_size: int,
        insights: dict[str, Any],
        analysis_version: str = ANALYSIS_VERSION,
        provider: str = DEFAULT_AI_PROVIDER,
        model_name: str = DEFAULT_AI_MODEL,
    ) -> InsightRecord: ...
    def refresh_expired(
        self,
        *,
        fingerprint: str,
        insights: dict[str, Any],
        provider: str = DEFAULT_AI_PROVIDER,
        model_name: str = DEFAULT_AI_MODEL,
    ) -> InsightRecord: ...
    def delete_dataset(self, dataset_id: str) -> None: ...
    def cleanup_expired(self) -> int: ...
    def clear(self) -> None: ...


def compute_content_hash(prepared: pd.DataFrame, columns: tuple[str, ...]) -> str:
    """Deterministic content hash for a prepared dataset at upload time."""
    normalized = prepared.copy()
    for column in columns:
        if column in normalized.columns:
            normalized[column] = normalized[column].map(
                lambda value: "" if pd.isna(value) else str(value)
            )
    row_hashes = pd.util.hash_pandas_object(normalized, index=True).values.tobytes()
    header = f"{len(normalized)}|{'|'.join(sorted(columns))}|".encode()
    return hashlib.sha256(header + row_hashes).hexdigest()


def canonical_filters(filters: dict[str, Any] | None) -> str:
    """Stable canonical string for filter parameters.

    - Categories are deduplicated and sorted.
    - Empty list / empty string / null use a fixed representation.
    - Keywords are stripped of surrounding whitespace.
    - Floats use a fixed format.
    - JSON fields are sorted by key with stable separators.
    """
    if not filters:
        return "none"

    def normalize(value: Any) -> Any:
        if isinstance(value, list):
            items: list[Any] = []
            for item in value:
                if item is None or item == "":
                    continue
                if isinstance(item, str):
                    item = item.strip()
                items.append(item)
            if not items:
                return "__EMPTY__"
            unique = list(dict.fromkeys(items))
            return sorted(
                unique,
                key=lambda item: (str(item), type(item).__name__),
            )
        if isinstance(value, str):
            return value.strip() or "__EMPTY__"
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return f"{float(value):.6f}"
        return value

    normalized = {key: normalize(value) for key, value in sorted(filters.items())}
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_scope_signature(
    content_hash: str,
    filters: dict[str, Any] | None,
    analysis_version: str = ANALYSIS_VERSION,
) -> str:
    """scope_signature = sha256(content_hash + canonical_filters + analysis_version)."""
    raw = f"{content_hash}{canonical_filters(filters)}{analysis_version}".encode()
    return hashlib.sha256(raw).hexdigest()


def compute_insight_fingerprint(
    *,
    dataset_id: str,
    scope_signature: str,
    sample_size: int,
    analysis_version: str = ANALYSIS_VERSION,
    provider: str = DEFAULT_AI_PROVIDER,
    model_name: str = DEFAULT_AI_MODEL,
) -> str:
    """Fixed-field-order fingerprint for the insights UNIQUE constraint."""
    payload = json.dumps(
        [
            dataset_id,
            scope_signature,
            str(int(sample_size)),
            analysis_version,
            provider,
            model_name,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_not_found(dataset_id: str) -> DatasetNotFoundError:
    return DatasetNotFoundError(dataset_id)


def make_insight_not_found(insight_id: str) -> InsightNotFoundError:
    return InsightNotFoundError(insight_id)


def expires_in(days: int) -> datetime:
    from datetime import UTC, timedelta

    return datetime.now(UTC) + timedelta(days=days)
