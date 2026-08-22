"""Log data access operations using SQLAlchemy 2.0 ORM."""

from datetime import datetime, timezone
from loguru import logger

from .connection import get_db_session
from .models import ApiCallLog, ApplicationLog


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
    latency_ms: float = None,
    error_reason: str = None,
    raw_response: str = None
) -> bool:
    """
    Inserts a new API call log record using SQLAlchemy ORM.
    """
    final_status = status_code or status or "SUCCESS"
    try:
        with get_db_session() as session:
            created_at = datetime.now(timezone.utc).isoformat()
            log_entry = ApiCallLog(
                log_id=log_id,
                batch_id=batch_id,
                credential_id=credential_id,
                provider=provider,
                model_name=model_name,
                chunk_index=chunk_index,
                request_pages=request_pages,
                status_code=final_status,
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
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


def get_api_call_logs(limit: int = 100) -> list[dict]:
    """
    Retrieves the most recent API call log records using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            logs = session.query(ApiCallLog).order_by(ApiCallLog.created_at.desc()).limit(limit).all()
            return [l.to_dict() for l in logs]
    except Exception as e:
        logger.error(f"Failed to get API call logs: {e}")
        return []


def get_application_logs(limit: int = 200, settings_path: str = "configs/settings.json") -> list[dict]:
    """
    Retrieves the most recent application log records using SQLAlchemy ORM.
    """
    try:
        with get_db_session() as session:
            logs = session.query(ApplicationLog).order_by(ApplicationLog.created_at.desc()).limit(limit).all()
            return [l.to_dict() for l in logs]
    except Exception as e:
        logger.error(f"Failed to get application logs: {e}")
        return []
