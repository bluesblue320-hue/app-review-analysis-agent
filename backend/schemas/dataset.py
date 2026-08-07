"""Dataset upload response schemas."""

from datetime import datetime

from backend.schemas.common import StrictModel


class DatasetUploadResponse(StrictModel):
    dataset_id: str
    original_rows: int
    valid_rows: int
    removed_rows: int
    invalid_rating_rows: int
    invalid_reasons: dict[str, int]
    columns: list[str]
    created_at: datetime
    expires_at: datetime


class DatasetDeleteResponse(StrictModel):
    dataset_id: str
    deleted: bool
