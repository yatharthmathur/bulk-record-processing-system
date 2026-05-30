from __future__ import annotations


class BulkProcessingError(Exception):
    """Base exception for bulk processing domain failures."""


class CsvValidationError(BulkProcessingError):
    def __init__(self, errors: list[str]) -> None:
        self.errors: list[str] = errors
        super().__init__("; ".join(errors))


class BatchNotFoundError(BulkProcessingError):
    def __init__(self, batch_id: str) -> None:
        super().__init__(f"Batch '{batch_id}' was not found.")
        self.batch_id: str = batch_id


class ExternalServiceError(BulkProcessingError):
    """Raised when the upstream hospital directory API fails or rejects a request."""
