from datetime import datetime, timezone
from loguru import logger
from sqlalchemy import select

from .connection import get_db_session
from .models import ApiCallLog, ApplicationLog
from src.core.constants import DEFAULT_SETTINGS_PATH


def create_api_call_log(
    log_id: str,
    batch_id: str,
    credential_id: str,
    provider: str,
    model_name: str,
    chunk_index: int,
    request_pages: str,
    status: str = None,
    status_code: str = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    nominal_value_usd: float = 0.0,
    is_free_tier: int = 0,
    latency_ms: float = None,
    error_reason: str = None,
    raw_response: str = None,
    company_id: str = None
) -> bool:
    """
    Inserts a new API call log record using Pure SQLAlchemy 2.0 ORM.
    """
    final_status = status_code or status or "SUCCESS"
    try:
        with get_db_session() as session:
            created_at = datetime.now(timezone.utc).isoformat()
            log_entry = ApiCallLog(
                log_id=log_id,
                company_id=company_id,
                batch_id=batch_id,
                credential_id=credential_id,
                provider=provider,
                model_name=model_name,
                chunk_index=chunk_index,
                request_pages=request_pages,
                status_code=final_status,
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
                cost_usd=cost_usd or 0.0,
                nominal_value_usd=nominal_value_usd or 0.0,
                is_free_tier=is_free_tier or 0,
                latency_ms=latency_ms,
                error_reason=error_reason,
                raw_response=raw_response,
                created_at=created_at
            )
            session.add(log_entry)
            return True
    except Exception as e:
        logger.error(f"Failed to create API call log: {e}")
        return False


def get_api_call_logs(limit: int = 100, company_id: str = None) -> list[dict]:
    """
    Retrieves the most recent API call log records using Pure SQLAlchemy 2.0 ORM.
    Optionally filters by company_id.
    """
    try:
        with get_db_session() as session:
            stmt = select(ApiCallLog)
            if company_id:
                stmt = stmt.where(ApiCallLog.company_id == company_id)
            stmt = stmt.order_by(ApiCallLog.created_at.desc()).limit(limit)
            logs = session.scalars(stmt).all()
            return [l.to_dict() for l in logs]
    except Exception as e:
        logger.error(f"Failed to get API call logs: {e}")
        return []


def get_application_logs(limit: int = 200, settings_path: str = DEFAULT_SETTINGS_PATH) -> list[dict]:
    """
    Retrieves the most recent application log records using Pure SQLAlchemy 2.0 ORM.
    """
    try:
        with get_db_session() as session:
            stmt = select(ApplicationLog).order_by(ApplicationLog.created_at.desc()).limit(limit)
            logs = session.scalars(stmt).all()
            return [l.to_dict() for l in logs]
    except Exception as e:
        logger.error(f"Failed to get application logs: {e}")
        return []
