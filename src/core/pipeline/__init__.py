import os
from typing import Optional, Dict, Any, List
from src.core.pipeline.stage_0_init import init_system
from src.core.pipeline.stage_1_ingestion import split_and_match, release_pending_merchant_files
from src.core.pipeline.stage_2_extraction import extract_documents, async_extract_documents
from src.core.pipeline.stage_3_transformation import transform_to_db
from src.core.pipeline.stage_4_validation import validate_documents
from src.core.pipeline.pipeline_reset import reset_pipeline_data
from src.core.pipeline.pipeline_helpers import merge_chunk_payloads, validate_and_process_payload
from src.core.healthcheck import run_healthcheck, print_healthcheck_report
from src.core.constants import DefaultIdentifier


# Backward-compatible stage aliases
run_init = init_system
run_split_and_match = split_and_match
run_extract = extract_documents
run_validate = validate_documents
run_transform_to_db = transform_to_db


def run_export_outputs(
    doc_type: str = None,
    company_code: str = DefaultIdentifier.COMPANY_CODE
) -> Dict[str, Any]:
    """Exports approved and processed documents to registered format strategies."""
    from src.core.db import get_documents_for_export, get_company_by_code
    from src.core.exporters.registry import list_exporters
    from src.core.storage_manager import storage_manager

    target_doc_type = doc_type or DefaultIdentifier.DOC_TYPE
    comp = get_company_by_code(company_code)
    comp_id = comp["company_id"] if comp else None
    approved_docs = get_documents_for_export(target_doc_type, company_id=comp_id)

    if not approved_docs:
        return {"status": "SKIPPED", "message": f"No approved/processed documents to export for doc_type '{target_doc_type}'."}

    exporters = list_exporters(target_doc_type)
    output_dir = storage_manager.get_output_dir(company_code, target_doc_type)
    exported_files = {}

    for exp_meta in exporters:
        exp_id = exp_meta["exporter_id"]
        handler = exp_meta["handler"]
        base_path = os.path.join(output_dir, f"{target_doc_type}_{exp_id}_export").replace("\\", "/")
        res = handler.export(approved_docs, base_path)
        if res:
            exported_files[exp_id] = res

    return {"status": "SUCCESS", "exported_documents": len(approved_docs), "outputs": exported_files}


def run_pipeline_all(
    doc_type: str = None,
    company_code: str = DefaultIdentifier.COMPANY_CODE
) -> Dict[str, Any]:
    """Executes full pipeline stages from Stage 0 to Stage 4 end-to-end."""
    target_doc_type = doc_type or DefaultIdentifier.DOC_TYPE
    results = {}
    results["stage_0_init"] = init_system(company_code=company_code)
    results["stage_1_ingestion"] = split_and_match(doc_type=target_doc_type, company_code=company_code)
    results["stage_2_extraction"] = extract_documents(doc_type=target_doc_type, company_code=company_code)
    results["stage_3_transformation"] = transform_to_db(doc_type=target_doc_type, company_code=company_code)
    results["stage_4_validation"] = validate_documents(doc_type=target_doc_type, company_code=company_code)
    results["export_outputs"] = run_export_outputs(doc_type=target_doc_type, company_code=company_code)
    return results


__all__ = [
    "init_system",
    "split_and_match",
    "release_pending_merchant_files",
    "extract_documents",
    "async_extract_documents",
    "validate_documents",
    "transform_to_db",
    "reset_pipeline_data",
    "merge_chunk_payloads",
    "validate_and_process_payload",
    "run_healthcheck",
    "print_healthcheck_report",
    "run_init",
    "run_split_and_match",
    "run_extract",
    "run_validate",
    "run_transform_to_db",
    "run_export_outputs",
    "run_pipeline_all",
]
