"""Audit and API call telemetry logging service using Pure SQLAlchemy 2.0 ORM."""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from sqlalchemy import select

from .logger import logger
from .constants import DefaultPath


class ApiCallLogCreate(BaseModel):
    """
    Structured DTO for recording AI / API calls and telemetry in the database.
    """
    log_id: str = Field(description="Unique identifier for the API call log")
    batch_id: Optional[str] = Field(default=None, description="Parent batch ID associated with the call")
    provider: str = Field(description="AI service provider (e.g. gemini, openai)")
    model_name: str = Field(description="Model identifier")
    chunk_index: int = Field(default=1, description="Index of the chunk in multi-part requests")
    request_pages: str = Field(default="1 pages", description="Page count or description")
    status_code: str = Field(default="SUCCESS", description="Call outcome status (SUCCESS, FAILED)")
    input_tokens: int = Field(default=0, description="Number of prompt/input tokens")
    output_tokens: int = 0
    cost_usd: float = 0.0
    nominal_value_usd: float = 0.0
    is_free_tier: int = 0
    latency_ms: Optional[float] = None
    error_reason: Optional[str] = None
    raw_response: Optional[str] = None
    company_id: Optional[str] = None


class AuditLogService:
    """
    Enterprise Service Layer for persistent audit trails and telemetry logs.
    Decouples callers from direct SQLAlchemy session management.
    """

    @classmethod
    def log_api_call(cls, log_data: ApiCallLogCreate | dict) -> bool:
        """Persists an API call telemetry log entry to the database."""
        if isinstance(log_data, dict):
            dto = ApiCallLogCreate(**log_data)
        else:
            dto = log_data

        try:
            from src.infrastructure.database import get_db_session, ApiCallLog
            with get_db_session() as session:
                created_at = datetime.now(timezone.utc).isoformat()
                log_entry = ApiCallLog(
                    log_id=dto.log_id,
                    company_id=dto.company_id,
                    batch_id=dto.batch_id,
                    provider=dto.provider,
                    model_name=dto.model_name,
                    chunk_index=dto.chunk_index,
                    request_pages=dto.request_pages,
                    status_code=dto.status_code,
                    input_tokens=dto.input_tokens or 0,
                    output_tokens=dto.output_tokens or 0,
                    cost_usd=dto.cost_usd or 0.0,
                    nominal_value_usd=dto.nominal_value_usd or 0.0,
                    is_free_tier=dto.is_free_tier or 0,
                    latency_ms=dto.latency_ms,
                    error_reason=dto.error_reason,
                    raw_response=dto.raw_response,
                    created_at=created_at
                )
                session.add(log_entry)
                return True
        except Exception as e:
            logger.error(f"AuditLogService: Failed to persist API call log: {e}")
            return False

    @classmethod
    def get_api_call_logs(cls, limit: int = 100, company_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves the most recent API call log records."""
        try:
            from src.infrastructure.database import get_db_session, ApiCallLog
            with get_db_session() as session:
                stmt = select(ApiCallLog)
                if company_id:
                    stmt = stmt.where(ApiCallLog.company_id == company_id)
                stmt = stmt.order_by(ApiCallLog.created_at.desc()).limit(limit)
                logs = session.scalars(stmt).all()
                return [l.to_dict() for l in logs]
        except Exception as e:
            logger.error(f"AuditLogService: Failed to get API call logs: {e}")
            return []

    @classmethod
    def get_application_logs(cls, limit: int = 200) -> List[Dict[str, Any]]:
        """Retrieves the most recent application log records."""
        try:
            from src.infrastructure.database import get_log_db_session, ApplicationLog
            with get_log_db_session() as session:
                stmt = select(ApplicationLog).order_by(ApplicationLog.created_at.desc()).limit(limit)
                logs = session.scalars(stmt).all()
                return [l.to_dict() for l in logs]
        except Exception as e:
            logger.error(f"AuditLogService: Failed to get application logs: {e}")
            return []


def create_api_call_log(
    log_id: str,
    batch_id: str,
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
    company_id: str = None,
    credential_id: str = None,
) -> bool:
    """Backward-compatible procedural wrapper that delegates to AuditLogService."""
    final_status = status_code or status or "SUCCESS"
    dto = ApiCallLogCreate(
        log_id=log_id,
        batch_id=batch_id,
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
        company_id=company_id
    )
    return AuditLogService.log_api_call(dto)


def get_api_call_logs(limit: int = 100, company_id: str = None) -> list[dict]:
    """Retrieves API call logs via AuditLogService."""
    return AuditLogService.get_api_call_logs(limit=limit, company_id=company_id)


def get_application_logs(limit: int = 200, settings_path: str = DefaultPath.SETTINGS) -> list[dict]:
    """Retrieves application logs via AuditLogService."""
    return AuditLogService.get_application_logs(limit=limit)
