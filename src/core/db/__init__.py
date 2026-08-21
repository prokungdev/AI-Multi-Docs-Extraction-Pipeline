from .connection import (
    get_db_connection,
    get_log_db_connection,
    get_db_connection_ctx,
    get_log_db_connection_ctx
)

from .schema import (
    initialize_db_schema,
    initialize_log_db_schema,
    seed_initial_data,
    reset_pipeline_database
)

from .documents import (
    calculate_file_hash,
    check_duplicate_document,
    create_batch,
    create_page,
    update_page,
    update_page_status,
    update_pages_status_batch,
    create_document,
    link_pages_to_document,
    get_document_by_id,
    get_document_pages,
    get_batch_pages,
    get_pending_documents,
    get_all_documents,
    update_document_to_approved,
    update_document_to_rejected,
    update_document_status,
    update_document_to_failed,
    update_document_payload,
    update_document_metadata,
    search_documents,
    get_unextracted_batches,
    get_pages_by_status,
    get_documents_for_export,
)

from .masters import (
    get_domains,
    get_sources,
    update_domain_active_status,
    update_source_active_status,
    get_active_credentials,
    update_credential_status,
    get_merchants,
    upsert_merchant,
    match_merchant,
    delete_merchant,
    insert_relational_receipt,
)

from .logs import (
    create_api_call_log,
    get_api_call_logs,
    get_application_logs,
)

__all__ = [
    # Connection
    "get_db_connection",
    "get_log_db_connection",
    "get_db_connection_ctx",
    "get_log_db_connection_ctx",
    # Schema
    "initialize_db_schema",
    "initialize_log_db_schema",
    "seed_initial_data",
    # Documents & Pages
    "calculate_file_hash",
    "check_duplicate_document",
    "create_batch",
    "create_page",
    "update_page",
    "update_page_status",
    "update_pages_status_batch",
    "create_document",
    "link_pages_to_document",
    "get_document_by_id",
    "get_document_pages",
    "get_batch_pages",
    "get_pending_documents",
    "get_all_documents",
    "update_document_to_approved",
    "update_document_to_rejected",
    "update_document_status",
    "update_document_to_failed",
    "update_document_payload",
    "update_document_metadata",
    "search_documents",
    "get_unextracted_batches",
    "get_pages_by_status",
    "get_documents_for_export",
    # Masters
    "get_domains",
    "get_sources",
    "update_domain_active_status",
    "update_source_active_status",
    "get_active_credentials",
    "update_credential_status",
    "get_merchants",
    "upsert_merchant",
    "match_merchant",
    "delete_merchant",
    "insert_relational_receipt",
    # Logs
    "create_api_call_log",
    "get_api_call_logs",
    "get_application_logs",
]

