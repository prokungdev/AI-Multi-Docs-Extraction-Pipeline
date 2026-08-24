import copy
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from src.core.models import DocumentStatus, ReviewPriority
from src.core.post_processor import apply_source_rules
from src.core.storage_manager import StoragePathManager, storage_manager
from src.core.config_loader import get_validation_thresholds
from src.core.constants import (
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


def validate_and_process_payload(
    payload: dict,
    doc_type: str = None,
    source: str = None,
    settings_path: str = DefaultPath.SETTINGS
) -> tuple[dict, str, list[str]]:
    """
    Applies source validation rules, financial math checks, and sets review priority
    using strictly configured thresholds from settings.json.
    """
    validation_notes = []
    target_dt = doc_type or DefaultIdentifier.DOC_TYPE
    thresholds = get_validation_thresholds(settings_path)
    financial_tolerance = float(thresholds["financial_tolerance"])
    confidence_high = float(thresholds["confidence_high"])
    confidence_low = float(thresholds["confidence_low"])
    confidence_review = float(thresholds["confidence_review"])

    # 1. Apply Merchant Rules (Tax ID, Date BE->AD, Default Categories/Units)
    processed_payload, req_review, review_reason = apply_source_rules(payload, doc_type=target_dt, source=source)
    if req_review and review_reason:
        validation_notes.append(review_reason)

    # 2. Mathematical Validation Checks
    fin = processed_payload.get("totals") or processed_payload.get("financial_summary", {})
    subtotal = float(fin.get("subtotal", 0.0))
    discount = float(fin.get("discount", 0.0))
    vat_amount = float(fin.get("vat_amount", 0.0))
    net_amount = float(fin.get("net_amount", 0.0))

    calculated_net = subtotal - discount + vat_amount
    if abs(calculated_net - net_amount) > financial_tolerance:
        validation_notes.append(
            f"Financial formula mismatch: Calculated ({subtotal:.2f} - {discount:.2f} + {vat_amount:.2f} = {calculated_net:.2f}) != Net ({net_amount:.2f})"
        )

    items = processed_payload.get("items", [])
    if items:
        item_sum = sum(float(item.get("total_price", 0.0)) for item in items if isinstance(item, dict))
        if item_sum > 0 and abs(item_sum - subtotal) > financial_tolerance:
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

    # 4. Determine Review Priority
    if overall_confidence < confidence_low or is_blurry or has_ambiguous_fields or not is_complete:
        review_priority = ReviewPriority.HIGH.value
    elif overall_confidence < confidence_high:
        review_priority = ReviewPriority.MEDIUM.value
    else:
        review_priority = ReviewPriority.LOW.value

    # 5. Determine Final Status Code
    if validation_notes or is_blurry or not is_complete or overall_confidence < confidence_review:
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
