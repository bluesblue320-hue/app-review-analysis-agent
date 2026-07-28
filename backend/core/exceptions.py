"""Typed backend errors translated to stable API responses."""

from __future__ import annotations


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class InvalidDatasetError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_dataset", message, 400)


class UnsupportedFileTypeError(AppError):
    def __init__(self, message: str = "仅支持 CSV 文件。") -> None:
        super().__init__("unsupported_file_type", message, 415)


class UploadTooLargeError(AppError):
    def __init__(self, max_size_mb: int) -> None:
        super().__init__(
            "upload_too_large",
            f"上传文件不能超过 {max_size_mb} MB。",
            413,
        )


class DatasetNotFoundError(AppError):
    def __init__(self, dataset_id: str) -> None:
        super().__init__(
            "dataset_not_found",
            f"数据集不存在或已失效：{dataset_id}",
            404,
        )


class AiServiceError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("ai_service_error", message, 503)
