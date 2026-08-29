"""Stage 3: Database Transformation Pipeline Stage.

Transforms verified/review-needed extracted records into relational SQLite tables.
Delegates core transformation logic to TransformerUseCase.
"""

from src.application.usecases.transformer import transform_batch_to_db


def transform_to_db(
    batch_id: str,
    doc_type: str = None,
    company_code: str = None
) -> dict:
    """
    Stage 3: Database Transformation entry point.
    Delegates to transform_batch_to_db usecase.
    """
    return transform_batch_to_db(batch_id=batch_id, doc_type=doc_type, company_code=company_code)
