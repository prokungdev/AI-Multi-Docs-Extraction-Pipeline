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
from src.infrastructure.core.constants import DefaultIdentifier

Base = declarative_base()
LogBase = declarative_base()


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


class Company(Base, DictSerializableMixin):
    """Standardized client company entity model for multi-company isolation."""
    __tablename__ = "companies"

    company_id = Column(String(36), primary_key=True)
    company_code = Column(String(50), unique=True, nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    short_name = Column(String(50), nullable=False)
    tax_id = Column(String(13), unique=True, nullable=True, index=True)
    branch_code = Column(String(5), nullable=False, default="00000")
    is_active = Column(Integer, default=1)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(50), nullable=True)

    batches = relationship("Batch", back_populates="company", cascade="all, delete-orphan")
    documents = relationship("DocumentControl", back_populates="company", cascade="all, delete-orphan")
    merchants = relationship("Merchant", back_populates="company", cascade="all, delete-orphan")
    expense_receipts = relationship("ExpenseReceipt", back_populates="company", cascade="all, delete-orphan")
    api_call_logs = relationship("ApiCallLog", back_populates="company")
    users = relationship("User", back_populates="company", cascade="all, delete-orphan")


class User(Base, DictSerializableMixin):
    """User entity model for multi-tenant identity, Audit Trail, and RBAC."""
    __tablename__ = "users"

    user_id = Column(String(36), primary_key=True)
    company_id = Column(String(36), ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="ADMIN")
    is_active = Column(Integer, default=1)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(50), nullable=True)

    company = relationship("Company", back_populates="users")


class DocumentStatus(Base, DictSerializableMixin):
    """Document processing status reference model."""
    __tablename__ = "document_statuses"

    status_code = Column(String(50), primary_key=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)


class Batch(Base, DictSerializableMixin):
    """Processed document batch metadata model."""
    __tablename__ = "batches"

    batch_id = Column(String(100), primary_key=True)
    company_id = Column(String(36), ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=True, index=True)
    original_filename = Column(String(255), nullable=False)
    total_pages = Column(Integer, nullable=False)
    storage_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), unique=True, nullable=False)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

    company = relationship("Company", back_populates="batches")
    documents = relationship("DocumentControl", back_populates="batch", cascade="all, delete-orphan")
    pages = relationship("BatchPage", back_populates="batch", cascade="all, delete-orphan")


class DocumentControl(Base, DictSerializableMixin):
    """Universal Central Document Control & Lifecycle Supertype Model."""
    __tablename__ = "document_controls"

    document_id = Column(String(100), primary_key=True)
    company_id = Column(String(36), ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=True, index=True)
    batch_id = Column(String(100), ForeignKey("batches.batch_id", ondelete="CASCADE"), nullable=False)
    doc_type_id = Column(String(100), nullable=False)
    status_code = Column(String(50), ForeignKey("document_statuses.status_code"), nullable=False)
    search_text = Column(Text, nullable=True)
    data_payload = Column(Text, nullable=True)
    error_reason = Column(Text, nullable=True)
    is_closed = Column(Integer, default=0, server_default="0")
    is_locked = Column(Integer, default=0, server_default="0")
    locked_by = Column(String(36), nullable=True)
    locked_at = Column(String(50), nullable=True)
    is_manually_edited = Column(Integer, default=0, server_default="0")
    confirmed_by = Column(String(100), nullable=True)
    confirmed_at = Column(String(50), nullable=True)
    model_used = Column(String(100), nullable=True)
    input_tokens = Column(Integer, default=0, server_default="0")
    output_tokens = Column(Integer, default=0, server_default="0")
    cost_usd = Column(Float, default=0.0, server_default="0.0")
    cost_thb = Column(Float, default=0.0, server_default="0.0")
    is_free_tier = Column(Integer, default=0, server_default="0")
    overall_confidence = Column(Float, nullable=True)
    confidence_level = Column(String(50), nullable=True)
    is_blurry = Column(Integer, nullable=True)
    is_ambiguous = Column(Integer, nullable=True)
    confidence_notes = Column(Text, nullable=True)
    review_priority = Column(String(20), nullable=True)
    is_auto_approved = Column(Integer, default=0, server_default="0")
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(50), nullable=True)

    company = relationship("Company", back_populates="documents")
    batch = relationship("Batch", back_populates="documents")
    status = relationship("DocumentStatus")
    pages = relationship("BatchPage", back_populates="document")
    expense_receipts = relationship("ExpenseReceipt", back_populates="document", cascade="all, delete-orphan")


class BatchPage(Base, DictSerializableMixin):
    """Batch physical page image model."""
    __tablename__ = "batch_pages"

    page_id = Column(String(100), primary_key=True)
    batch_id = Column(String(100), ForeignKey("batches.batch_id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(100), ForeignKey("document_controls.document_id", ondelete="SET NULL"), nullable=True)
    page_number = Column(Integer, nullable=False)
    chunk_index = Column(Integer, default=1, server_default="1", nullable=False)
    image_path = Column(String(500), nullable=False)
    status_code = Column(String(50), ForeignKey("document_statuses.status_code"), nullable=False)
    error_reason = Column(Text, nullable=True)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

    batch = relationship("Batch", back_populates="pages")
    document = relationship("DocumentControl", back_populates="pages")
    status = relationship("DocumentStatus")


class Merchant(Base, DictSerializableMixin):
    """Standardized merchant entity model."""
    __tablename__ = "merchants"

    merchant_id = Column(String(100), primary_key=True)
    company_id = Column(String(36), ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=True, index=True)
    tax_id = Column(String(50), nullable=True)
    merchant_name = Column(String(200), nullable=False)
    short_name = Column(String(100), nullable=False, default=DefaultIdentifier.DEFAULT_SHORT_NAME)
    file_prefix = Column(String(100), nullable=False, default=DefaultIdentifier.DEFAULT_SHORT_NAME)
    status_code = Column(String(50), nullable=False, default=MerchantStatus.APPROVED.value)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(String(50), nullable=True)
    default_wht_rate = Column(Float, default=0.0)
    is_vat_registered = Column(Integer, default=1)
    is_active = Column(Integer, default=1, server_default="1")
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String(50), nullable=True)

    company = relationship("Company", back_populates="merchants")
    receipts = relationship("ExpenseReceipt", back_populates="merchant")

    __table_args__ = (
        Index("idx_merchants_company_tax_id", "company_id", "tax_id"),
        Index("idx_merchants_company_name", "company_id", "merchant_name"),
        Index("idx_merchants_company_short_name", "company_id", "short_name"),
        Index("idx_merchants_company_file_prefix", "company_id", "file_prefix"),
        Index("idx_merchants_status_code", "status_code"),
    )


class ExpenseReceipt(Base, DictSerializableMixin):
    """Standardized expense receipt header model."""
    __tablename__ = "expense_receipts"

    receipt_id = Column(String(100), primary_key=True)
    company_id = Column(String(36), ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(String(100), ForeignKey("document_controls.document_id", ondelete="CASCADE"), nullable=False)
    merchant_id = Column(String(100), ForeignKey("merchants.merchant_id"), nullable=False)
    doc_number = Column(String(100), nullable=True)
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

    company = relationship("Company", back_populates="expense_receipts")
    document = relationship("DocumentControl", back_populates="expense_receipts")
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


class ApiCallLog(Base, DictSerializableMixin):
    """API execution log model."""
    __tablename__ = "api_call_logs"

    log_id = Column(String(100), primary_key=True)
    company_id = Column(String(36), ForeignKey("companies.company_id", ondelete="SET NULL"), nullable=True, index=True)
    batch_id = Column(String(100), nullable=True)
    provider = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    chunk_index = Column(Integer, nullable=True)
    request_pages = Column(Text, nullable=True)
    status_code = Column(String(50), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0, server_default="0.0")
    nominal_value_usd = Column(Float, default=0.0, server_default="0.0")
    is_free_tier = Column(Integer, default=0, server_default="0")
    latency_ms = Column(Float, nullable=True)
    error_reason = Column(Text, nullable=True)
    raw_response = Column(Text, nullable=True)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

    company = relationship("Company", back_populates="api_call_logs")


class ApplicationLog(LogBase, DictSerializableMixin):
    """Application log model."""
    __tablename__ = "application_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(20), nullable=False)
    module = Column(String(100), nullable=False)
    function = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    extra_data = Column(Text, nullable=True)
    created_at = Column(String(50), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
