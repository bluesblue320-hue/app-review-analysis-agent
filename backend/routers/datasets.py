"""Dataset upload endpoint."""

from fastapi import APIRouter, File, UploadFile, status

from backend.core.config import settings
from backend.schemas.dataset import DatasetUploadResponse
from backend.services.dataset_service import dataset_store


router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post(
    "",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(file: UploadFile = File(...)) -> DatasetUploadResponse:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    record = dataset_store.create(file.filename or "", content)
    return DatasetUploadResponse(
        dataset_id=record.dataset_id,
        original_rows=record.original_rows,
        valid_rows=record.valid_rows,
        columns=list(record.columns),
        created_at=record.created_at,
    )
