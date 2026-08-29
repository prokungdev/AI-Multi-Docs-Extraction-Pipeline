"""Domain Document Type Registry.

Provides central registry, lookup, and metadata discovery for all supported document types.
"""

from typing import Dict, List, Optional, Union, Any, Type
from src.infrastructure.core.constants import DocTypeId
from .base import BaseDocType
from .expense_receipt import ExpenseReceiptDocType
from .tax_invoice import TaxInvoiceDocType
from .withholding_tax import WithholdingTaxDocType


class DocTypeRegistry:
    """Centralized Registry for Document Type Definitions."""

    _registry: Dict[str, BaseDocType] = {}

    @classmethod
    def register(cls, doc_type_instance: BaseDocType) -> BaseDocType:
        """Registers a document type instance into the central registry."""
        key = doc_type_instance.doc_type_id.value if isinstance(doc_type_instance.doc_type_id, DocTypeId) else str(doc_type_instance.doc_type_id).lower().strip()
        cls._registry[key] = doc_type_instance
        return doc_type_instance

    @classmethod
    def get(cls, doc_type_id: Union[str, DocTypeId]) -> BaseDocType:
        """
        Retrieves a document type definition by its Enum or String ID.
        Raises KeyError immediately if not found (Strict Fail-Fast).
        """
        key = doc_type_id.value if isinstance(doc_type_id, DocTypeId) else str(doc_type_id).lower().strip()
        if key not in cls._registry:
            valid_types = ", ".join([f"'{k}'" for k in cls._registry.keys()])
            raise KeyError(
                f"Unknown document type '{doc_type_id}'. "
                f"Valid registered document types are: [{valid_types}] (Fail-Fast)."
            )
        return cls._registry[key]

    @classmethod
    def list_all(cls) -> List[BaseDocType]:
        """Lists all registered document type instances sorted by sort_order."""
        return sorted(cls._registry.values(), key=lambda x: x.sort_order)

    @classmethod
    def get_active_doc_types(cls) -> List[Dict[str, Any]]:
        """Returns active document types serialized as dictionary list for UI and API."""
        return [dt.to_dict() for dt in cls.list_all() if dt.is_active]

    @classmethod
    def is_valid_type(cls, doc_type_id: Union[str, DocTypeId]) -> bool:
        """Checks if a given doc_type_id is registered."""
        key = doc_type_id.value if isinstance(doc_type_id, DocTypeId) else str(doc_type_id).lower().strip()
        return key in cls._registry

    @classmethod
    def get_default_doc_type(cls) -> str:
        """Returns default document type string identifier."""
        return DocTypeId.EXPENSE_RECEIPT.value


# ==============================================================================
# Auto-Registration of Built-in Document Types
# ==============================================================================
DocTypeRegistry.register(ExpenseReceiptDocType())
DocTypeRegistry.register(TaxInvoiceDocType())
DocTypeRegistry.register(WithholdingTaxDocType())


# ==============================================================================
# Convenience Helper Functions
# ==============================================================================
def get_doc_type(doc_type_id: Union[str, DocTypeId]) -> BaseDocType:
    """Retrieves document type definition."""
    return DocTypeRegistry.get(doc_type_id)


def list_doc_types() -> List[BaseDocType]:
    """Lists all document types."""
    return DocTypeRegistry.list_all()


def get_active_doc_types() -> List[Dict[str, Any]]:
    """Returns list of active document types."""
    return DocTypeRegistry.get_active_doc_types()


def is_doc_type_active(doc_type_id: Union[str, DocTypeId]) -> bool:
    """Checks if doc_type is registered and active."""
    try:
        dt = DocTypeRegistry.get(doc_type_id)
        return dt.is_active
    except KeyError:
        return False


def get_default_doc_type() -> str:
    """Returns default document type ID."""
    return DocTypeRegistry.get_default_doc_type()
