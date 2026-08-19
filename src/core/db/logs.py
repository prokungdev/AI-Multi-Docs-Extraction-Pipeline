import sqlite3
from datetime import datetime
from loguru import logger
from .connection import get_db_connection, get_log_db_connection

def create_api_call_log(log_id: str, batch_id: str, credential_id: str, provider: str, model_name: str,
                        chunk_index: int, request_pages: str, status: str, input_tokens: int = 0,
                        output_tokens: int = 0, latency_ms: float = None, error_reason: str = None,
                        raw_response: str = None) -> bool:
    """
    Inserts a new API call log record into api_call_logs table.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        created_at = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO api_call_logs (
                log_id, batch_id, credential_id, provider, model_name, chunk_index,
                request_pages, status, input_tokens, output_tokens, latency_ms,
                error_reason, raw_response, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, batch_id, credential_id, provider, model_name, chunk_index,
              request_pages, status, input_tokens, output_tokens, latency_ms,
              error_reason, raw_response, created_at))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to create API call log: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_api_call_logs(limit: int = 100) -> list[dict]:
    """
    Retrieves the most recent API call log records.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_call_logs ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to get API call logs: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_application_logs(limit: int = 200, settings_path: str = "configs/settings.json") -> list[dict]:
    """
    Retrieves the most recent application log records from logs/logs.db.
    """
    conn = None
    try:
        conn = get_log_db_connection(settings_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM application_logs ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to get application logs: {e}")
        return []
    finally:
        if conn:
            conn.close()
