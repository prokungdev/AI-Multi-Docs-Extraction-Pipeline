from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict

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

class ReviewPriority(str, Enum):
    """
    Standard priority levels for document manual review queue.
    """
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    def __str__(self) -> str:
        return self.value


# ==============================================================================
# Pydantic v2 Domain Models for Extraction & Validation
# ==============================================================================

class ReceiptInfoModel(BaseModel):
    """
    Receipt header metadata model.
    """
    receipt_number: Optional[str] = Field(default="", description="Invoice or receipt number")
    transaction_date: Optional[str] = Field(default="", description="Transaction date in YYYY-MM-DD or raw format")
    expense_category: Optional[str] = Field(default="", description="Expense classification category")
    payment_method: Optional[str] = Field(default="", description="Payment method used")


class MerchantModel(BaseModel):
    """
    Merchant master details model.
    """
    name: Optional[str] = Field(default="", description="Merchant or vendor name")
    tax_id: Optional[str] = Field(default="", description="Tax identification number (13 digits in TH)")
    branch_name: Optional[str] = Field(default="", description="Branch name")
    branch_code: Optional[str] = Field(default="", description="Branch code (e.g. 00000 for Head Office)")
    address: Optional[str] = Field(default="", description="Merchant full address")


class ReceiptItemModel(BaseModel):
    """
    Individual line item model for expense receipts.
    """
    name: str = Field(default="Unspecified Item", description="Item description")
    qty: float = Field(default=1.0, description="Quantity purchased")
    unit_price: float = Field(default=0.0, description="Unit price per item")
    total_price: float = Field(default=0.0, description="Total line item price")

    @field_validator("qty", "unit_price", "total_price", mode="before")
    @classmethod
    def sanitize_float(cls, v: Any) -> float:
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        try:
            cleaned = str(v).replace(",", "").strip()
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0


class TotalsModel(BaseModel):
    """
    Financial total summary model.
    """
    subtotal: float = Field(default=0.0, description="Subtotal amount before tax/discount")
    discount: float = Field(default=0.0, description="Discount amount")
    vat_amount: float = Field(default=0.0, description="VAT amount (7%)")
    net_amount: float = Field(default=0.0, description="Final net total amount")

    @field_validator("subtotal", "discount", "vat_amount", "net_amount", mode="before")
    @classmethod
    def sanitize_totals(cls, v: Any) -> float:
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        try:
            cleaned = str(v).replace(",", "").strip()
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0


class ExtractedReceiptPayloadModel(BaseModel):
    """
    Root payload model for AI extracted expense receipts.
    """
    model_config = ConfigDict(populate_by_name=True)

    receipt_info: ReceiptInfoModel = Field(default_factory=ReceiptInfoModel)
    merchant: MerchantModel = Field(default_factory=MerchantModel)
    items: list[ReceiptItemModel] = Field(default_factory=list)
    totals: TotalsModel = Field(default_factory=TotalsModel)
    validation_meta: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict, alias="_metadata")
