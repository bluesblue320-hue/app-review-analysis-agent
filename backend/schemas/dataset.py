"""Dataset upload response schemas."""

from datetime import datetime

from backend.schemas.common import StrictModel


class DatasetUploadResponse(StrictModel):
    dataset_id: str
    original_rows: int
    valid_rows: int
    columns: list[str]
    created_at: datetime
