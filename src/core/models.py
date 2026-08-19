from enum import Enum

class DocumentStatus(str, Enum):
    """
    Standard status codes for document pages and extracted documents.
    """
    PENDING = "PENDING"
    PREPROCESSED = "PREPROCESSED"
    EXTRACTED = "EXTRACTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PROCESSED = "PROCESSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    def __str__(self) -> str:
        return self.value
