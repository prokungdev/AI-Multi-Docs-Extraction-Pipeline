"""SQLAlchemy ORM Entities and Data Models for AI Multi-Docs Extraction Pipeline.

Provides standardized declarative models for relational database mapping across SQLite and PostgreSQL.
"""

from datetime import datetime, timezone
import enum
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    DateTime,
    ForeignKey,
    Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class MerchantStatus(str, enum.Enum):
    """Strongly-typed merchant gatekeeper status."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    IGNORED = "IGNORED"


class DictSerializableMixin:
    """Mixin to serialize SQLAlchemy models to Python dictionaries."""
    def to_dict(self) -> dict:
        """Converts model columns into a dictionary."""
        result = {}
        for column in self.__table__.columns:
            val = getattr(self, column.name)
            result[column.name] = val
        return result


class DocumentStatus(Base, DictSerializableMixin):
    """Document processing status reference model."""
    __tablename__ = "document_statuses"

    status_code = Column(String(50), primary_key=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)


class DocumentSource(Base, DictSerializableMixin):
    """Merchant/Document source reference model."""
    __tablename__ = "document_sources"

    source_id = Column(String(100), primary_key=True)
    domain_id = Column(String(100), primary_key=True)
    display_name = Column(String(150), nullable=False)
    is_active = Column(Integer, default=1)


class ProcessedBatch(Base, DictSerializableMixin):
    """Processed document batch metadata model."""
    __tablename__ = "processed_batches"

    batch_id = Column(String(100), primary_key=True)
    original_filename = Column(String(255), nullable=False)
    total_pages = Column(Integer, nullable=False)
    storage_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), unique=True, nullable=False)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

    documents = relationship("Document", back_populates="batch", cascade="all, delete-orphan")
    pages = relationship("DocumentPage", back_populates="batch", cascade="all, delete-orphan")


class Document(Base, DictSerializableMixin):
    """Document master model."""
    __tablename__ = "documents"

    document_id = Column(String(100), primary_key=True)
    batch_id = Column(String(100), ForeignKey("processed_batches.batch_id", ondelete="CASCADE"), nullable=False)
    domain_id = Column(String(100), nullable=False)
    source_id = Column(String(100), nullable=False)
    status_code = Column(String(50), ForeignKey("document_statuses.status_code"), nullable=False)
    doc_number = Column(String(100), nullable=True)
    doc_date = Column(String(50), nullable=True)
    entity_name = Column(String(200), nullable=True)
    total_amount = Column(Float, nullable=True)
    search_text = Column(Text, nullable=True)
    data_payload = Column(Text, nullable=True)
    error_reason = Column(Text, nullable=True)
    is_locked = Column(Integer, default=0, server_default="0")
    is_manually_edited = Column(Integer, default=0, server_default="0")
    confirmed_by = Column(String(100), nullable=True)
    confirmed_at = Column(String(50), nullable=True)
    model_used = Column(String(100), nullable=True)
    input_tokens = Column(Integer, default=0, server_default="0")
    output_tokens = Column(Integer, default=0, server_default="0")
    overall_confidence = Column(Float, nullable=True)
    confidence_level = Column(String(50), nullable=True)
    is_blurry = Column(Integer, nullable=True)
    is_ambiguous = Column(Integer, nullable=True)
    confidence_notes = Column(Text, nullable=True)
    review_priority = Column(String(20), nullable=True)
    is_auto_approved = Column(Integer, default=0, server_default="0")
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(50), nullable=True)

    batch = relationship("ProcessedBatch", back_populates="documents")
    status = relationship("DocumentStatus")
    pages = relationship("DocumentPage", back_populates="document")
    expense_receipts = relationship("ExpenseReceipt", back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base, DictSerializableMixin):
    """Document page image model."""
    __tablename__ = "document_pages"

    page_id = Column(String(100), primary_key=True)
    batch_id = Column(String(100), ForeignKey("processed_batches.batch_id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(100), ForeignKey("documents.document_id", ondelete="SET NULL"), nullable=True)
    page_number = Column(Integer, nullable=False)
    image_path = Column(String(500), nullable=False)
    status_code = Column(String(50), ForeignKey("document_statuses.status_code"), nullable=False)
    error_reason = Column(Text, nullable=True)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

    batch = relationship("ProcessedBatch", back_populates="pages")
    document = relationship("Document", back_populates="pages")
    status = relationship("DocumentStatus")


class Merchant(Base, DictSerializableMixin):
    """Standardized merchant entity model."""
    __tablename__ = "merchants"

    merchant_id = Column(String(100), primary_key=True)
    tax_id = Column(String(50), nullable=True)
    merchant_name = Column(String(200), nullable=False)
    short_name = Column(String(100), nullable=False, default="merchant")
    file_prefix = Column(String(100), nullable=False, default="merchant")
    status_code = Column(String(50), nullable=False, default="APPROVED")  # APPROVED, PENDING, IGNORED
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(String(50), nullable=True)
    default_wht_rate = Column(Float, default=0.0)
    is_vat_registered = Column(Integer, default=1)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(50), nullable=True)

    receipts = relationship("ExpenseReceipt", back_populates="merchant")

    __table_args__ = (
        Index("idx_merchants_tax_id", "tax_id"),
        Index("idx_merchants_name", "merchant_name"),
        Index("idx_merchants_short_name", "short_name"),
        Index("idx_merchants_file_prefix", "file_prefix"),
        Index("idx_merchants_status_code", "status_code"),
    )


# Alias for backward compatibility if needed
MerchantMaster = Merchant


class ExpenseReceipt(Base, DictSerializableMixin):
    """Standardized expense receipt header model."""
    __tablename__ = "expense_receipts"

    receipt_id = Column(String(100), primary_key=True)
    document_id = Column(String(100), ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    merchant_id = Column(String(100), ForeignKey("merchants.merchant_id"), nullable=False)
    transaction_date = Column(String(50), nullable=True)
    merchant_name = Column(String(200), nullable=True)
    tax_id = Column(String(50), nullable=True)
    expense_category = Column(String(100), nullable=True)
    subtotal = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    vat_amount = Column(Float, default=0.0)
    net_amount = Column(Float, default=0.0)
    payment_method = Column(String(50), nullable=True)
    source_filename = Column(String(255), nullable=True)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(50), nullable=True)

    document = relationship("Document", back_populates="expense_receipts")
    merchant = relationship("Merchant", back_populates="receipts")
    items = relationship("ExpenseReceiptItem", back_populates="receipt", cascade="all, delete-orphan")


class ExpenseReceiptItem(Base, DictSerializableMixin):
    """Standardized expense receipt item detail model."""
    __tablename__ = "expense_receipt_items"

    item_id = Column(String(100), primary_key=True)
    receipt_id = Column(String(100), ForeignKey("expense_receipts.receipt_id", ondelete="CASCADE"), nullable=False)
    item_name = Column(String(255), nullable=False)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Float, default=0.0)
    total_price = Column(Float, default=0.0)

    receipt = relationship("ExpenseReceipt", back_populates="items")


class ApiCredential(Base, DictSerializableMixin):
    """API credentials model."""
    __tablename__ = "api_credentials"

    credential_id = Column(String(100), primary_key=True)
    provider = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    api_key_env = Column(String(100), nullable=False)
    is_active = Column(Integer, default=1)
    last_active_at = Column(String(50), nullable=True)
    error_count = Column(Integer, default=0)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(50), nullable=True)


class ApiCallLog(Base, DictSerializableMixin):
    """API execution log model."""
    __tablename__ = "api_call_logs"

    log_id = Column(String(100), primary_key=True)
    batch_id = Column(String(100), nullable=True)
    credential_id = Column(String(100), nullable=True)
    provider = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    chunk_index = Column(Integer, nullable=True)
    request_pages = Column(Text, nullable=True)
    status_code = Column(String(50), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    latency_ms = Column(Float, nullable=True)
    error_reason = Column(Text, nullable=True)
    raw_response = Column(Text, nullable=True)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())


class ApplicationLog(Base, DictSerializableMixin):
    """Application log model."""
    __tablename__ = "application_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(20), nullable=False)
    module = Column(String(100), nullable=False)
    function = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    extra_data = Column(Text, nullable=True)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
