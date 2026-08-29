import copy
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from src.application.dtos.document_dto import DocumentStatus, ReviewPriority
from src.domain.policies.financial_rules import ValidationStrategyEngine
from src.infrastructure.external.storage.storage_manager import StoragePathManager, storage_manager
from src.infrastructure.core.config import get_validation_thresholds
from src.infrastructure.core.constants import (
    DefaultPath,
    DefaultIdentifier,
)


@dataclass
class PipelineContext:
    """
    Unified Data Transfer Object passed across all Pipeline Stages.
    Contains company scope, target doc_type, active batch tracking, and direct access to StoragePathManager.
    """
    company_code: str = DefaultIdentifier.COMPANY_CODE
    doc_type: str = DefaultIdentifier.DOC_TYPE
    batch_id: Optional[str] = None
    settings_path: str = DefaultPath.SETTINGS
    storage: StoragePathManager = field(default_factory=lambda: storage_manager)
    metadata: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, int] = field(default_factory=lambda: {
        "processed_batches": 0,
        "extracted_docs": 0,
        "auto_approved": 0,
        "needs_review": 0,
        "failed": 0
    })

    def get_stage_dir(self, stage_name: str) -> str:
        """Helper to get any stage folder under the current context company & doc_type."""
        return self.storage.get_stage_dir(stage_name, self.company_code, self.doc_type)

    def get_output_dir(self) -> str:
        """Helper to get 06_output folder for current context."""
        return self.storage.get_output_dir(self.company_code, self.doc_type)


def merge_chunk_payloads(payloads: list[dict]) -> dict:
    """
    Merges multiple extracted JSON payloads from different requests of the same batch.
    Combines item lists, aggregates token metadata, and computes composite validation status.
    """
    if not payloads:
        return {}

    if len(payloads) == 1:
        return payloads[0]

    merged = copy.deepcopy(payloads[0])

    # 1. Merge Line Items from subsequent chunks
    all_items = []
    for p in payloads:
        items = p.get("items", [])
        if isinstance(items, list):
            all_items.extend(items)
    merged["items"] = all_items

    # 2. Attribute and Aggregate Token Metadata across chunks
    total_input_tokens = 0
    total_output_tokens = 0
    model_name = None

    for p in payloads:
        meta = p.get("_metadata", {})
        if meta:
            total_input_tokens += meta.get("input_tokens", 0)
            total_output_tokens += meta.get("output_tokens", 0)
            if not model_name:
                model_name = meta.get("model_used")

    merged["_metadata"] = {
        "model_used": model_name,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_parts_merged": len(payloads),
    }

    # 3. Consolidate Validation Metadata across all parts
    is_complete = True
    missing_pages = []
    logical_page_order = []

    current_page_offset = 0
    for p in payloads:
        meta = p.get("validation_meta", {})
        part_complete = meta.get("is_complete", True)
        if not part_complete:
            is_complete = False
            missing_pages.extend(meta.get("missing_pages", []))

        part_order = meta.get("logical_page_order", [])
        offset_order = [idx + current_page_offset for idx in part_order]
        logical_page_order.extend(offset_order)

        current_page_offset += len(part_order) if part_order else 50

    merged["validation_meta"] = {
        "is_complete": is_complete,
        "missing_pages": sorted(list(set(missing_pages))),
        "logical_page_order": logical_page_order,
    }

    return merged


def resolve_doc_type_thresholds(doc_type: str = None, settings_path: str = DefaultPath.SETTINGS) -> dict:
    """
    Resolves validation thresholds and processing type from Database DocumentType table or DocTypeRegistry.
    """
    target_dt = doc_type or DefaultIdentifier.DOC_TYPE
    
    # 1. Try resolving from Database DocumentType table
    try:
        from src.infrastructure.database.engine import get_db_session
        from src.infrastructure.database.models import DocumentType
        from sqlalchemy import select

        with get_db_session() as session:
            dt_row = session.scalars(select(DocumentType).filter_by(doc_type_id=target_dt)).first()
            if dt_row:
                return {
                    "processing_type": dt_row.processing_type or "AI",
                    "confidence_high": dt_row.confidence_high,
                    "confidence_review": dt_row.confidence_review,
                    "confidence_low": dt_row.confidence_low,
                    "financial_tolerance": dt_row.financial_tolerance if dt_row.financial_tolerance is not None else 0.05,
                }
    except Exception:
        pass

    # 2. Fallback to DocTypeRegistry Strategy
    try:
        from src.domain.doc_types import DocTypeRegistry
        strategy = DocTypeRegistry.get(target_dt)
        proc_type = getattr(strategy, "processing_type", "AI")
        if hasattr(proc_type, "value"):
            proc_type = proc_type.value
        return {
            "processing_type": str(proc_type or "AI"),
            "confidence_high": getattr(strategy, "confidence_high", 0.85),
            "confidence_review": getattr(strategy, "confidence_review", 0.70),
            "confidence_low": getattr(strategy, "confidence_low", 0.60),
            "financial_tolerance": getattr(strategy, "financial_tolerance", 0.05),
        }
    except Exception:
        return {
            "processing_type": "AI",
            "confidence_high": 0.85,
            "confidence_review": 0.70,
            "confidence_low": 0.60,
            "financial_tolerance": 0.05,
        }


def validate_and_process_payload(
    payload: dict,
    doc_type: str = None,
    merchant_id: str = None,
    settings_path: str = DefaultPath.SETTINGS
) -> tuple[dict, str, list[str]]:
    """
    Applies domain validation strategies, financial math checks, and sets review priority
    using strictly configured thresholds from DocumentType table / DocTypeRegistry.
    """
    validation_notes = []
    target_dt = doc_type or DefaultIdentifier.DOC_TYPE
    thresholds = resolve_doc_type_thresholds(target_dt, settings_path=settings_path)
    
    processing_type = thresholds.get("processing_type", "AI")
    financial_tolerance = thresholds.get("financial_tolerance")
    confidence_high = thresholds.get("confidence_high")
    confidence_low = thresholds.get("confidence_low")
    confidence_review = thresholds.get("confidence_review")

    # 1. Apply Domain Validation Strategies (Date Normalization, Tax ID, Financial Math)
    engine = ValidationStrategyEngine()
    processed_payload, req_review, reasons = engine.run_validation(
        payload,
        context={"doc_type": target_dt, "merchant_id": merchant_id}
    )
    if req_review and reasons:
        validation_notes.extend(reasons)

    # 2. Mathematical Validation Checks (if applicable to this doc_type)
    if financial_tolerance is not None:
        fin = processed_payload.get("totals") or processed_payload.get("financial_summary", {})
        subtotal = float(fin.get("subtotal", 0.0))
        discount = float(fin.get("discount", 0.0))
        vat_amount = float(fin.get("vat_amount", 0.0))
        net_amount = float(fin.get("net_amount", 0.0))

        calculated_net = subtotal - discount + vat_amount
        if abs(calculated_net - net_amount) > float(financial_tolerance):
            validation_notes.append(
                f"Financial formula mismatch: Calculated ({subtotal:.2f} - {discount:.2f} + {vat_amount:.2f} = {calculated_net:.2f}) != Net ({net_amount:.2f})"
            )

        items = processed_payload.get("items", [])
        if items:
            item_sum = sum(float(item.get("total_price", 0.0)) for item in items if isinstance(item, dict))
            if item_sum > 0 and abs(item_sum - subtotal) > float(financial_tolerance):
                validation_notes.append(
                    f"Items total price sum ({item_sum:.2f}) does not match subtotal ({subtotal:.2f})"
                )

    # 3. Extraction Quality & Ambiguity Checks
    ext_meta = processed_payload.get("extraction_metadata", {})
    overall_confidence = float(ext_meta.get("overall_confidence", 0.75))
    is_blurry = ext_meta.get("is_blurry", False)
    has_ambiguous_fields = ext_meta.get("has_ambiguous_fields", False) or len(validation_notes) > 0
    confidence_notes = ext_meta.get("confidence_notes", "")

    val_meta = processed_payload.get("validation_meta", {})
    is_complete = val_meta.get("is_complete", True)

    # 4. Determine Review Priority and Final Status Code
    if processing_type == "ARCHIVE_ONLY" or confidence_review is None:
        # Non-AI / Archive-Only Processing
        review_priority = ReviewPriority.LOW.value
        status_code = DocumentStatus.PROCESSED.value if not validation_notes else DocumentStatus.NEEDS_REVIEW.value
    else:
        # AI-based Extraction Processing
        c_low = float(confidence_low if confidence_low is not None else 0.60)
        c_high = float(confidence_high if confidence_high is not None else 0.85)
        c_review = float(confidence_review if confidence_review is not None else 0.70)

        if overall_confidence < c_low or is_blurry or has_ambiguous_fields or not is_complete:
            review_priority = ReviewPriority.HIGH.value
        elif overall_confidence < c_high:
            review_priority = ReviewPriority.MEDIUM.value
        else:
            review_priority = ReviewPriority.LOW.value

        if validation_notes or is_blurry or not is_complete or overall_confidence < c_review:
            status_code = DocumentStatus.NEEDS_REVIEW.value
        else:
            status_code = DocumentStatus.PROCESSED.value

    if validation_notes:
        note_str = " | ".join(validation_notes)
        confidence_notes = f"{confidence_notes} [Validation: {note_str}]".strip()

    processed_payload["extraction_metadata"] = {
        **ext_meta,
        "overall_confidence": overall_confidence,
        "review_priority": review_priority,
        "is_blurry": is_blurry,
        "has_ambiguous_fields": has_ambiguous_fields,
        "confidence_notes": confidence_notes,
    }


    return processed_payload, status_code, validation_notes


def extract_page_document_payload(payload: dict, page_number: int = 1) -> dict:
    """
    Extracts/unwraps single-page document dictionary from multi-page AI payload.
    Matches by logical_page_number or 0-based page index.
    Preserves top-level _metadata if present.
    """
    if not isinstance(payload, dict):
        return {}

    docs = payload.get("extracted_documents")
    if isinstance(docs, list) and docs:
        target_doc = None
        for doc in docs:
            if isinstance(doc, dict) and doc.get("logical_page_number") == page_number:
                target_doc = copy.deepcopy(doc)
                break
        if target_doc is None:
            target_idx = min(max(0, page_number - 1), len(docs) - 1)
            if isinstance(docs[target_idx], dict):
                target_doc = copy.deepcopy(docs[target_idx])

        if target_doc:
            if "_metadata" in payload and "_metadata" not in target_doc:
                target_doc["_metadata"] = payload["_metadata"]
            return target_doc

    return payload
