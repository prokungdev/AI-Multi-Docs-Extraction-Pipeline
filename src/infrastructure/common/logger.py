"""
Unified Application Logger Gateway.
Abstracts the underlying logging engine behind an enterprise Adapter / Gateway.
Allows swapping or extending logging engines without modifying business modules.
"""

import os
import sys
import json
from typing import Any, Optional
from loguru import logger as _backend_logger
from src.infrastructure.common.constants import DefaultPath


class AppLogger:
    """
    Standard Application Logger Adapter.
    Delegates calls to configured logging provider while exposing a uniform API.
    """

    def __init__(self, backend=None):
        self._backend = backend or _backend_logger

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._backend.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._backend.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._backend.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._backend.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._backend.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._backend.exception(msg, *args, **kwargs)

    def bind(self, **kwargs: Any) -> "AppLogger":
        return AppLogger(self._backend.bind(**kwargs))

    def opt(self, *args: Any, **kwargs: Any) -> "AppLogger":
        return AppLogger(self._backend.opt(*args, **kwargs))

    def catch(self, *args: Any, **kwargs: Any):
        return self._backend.catch(*args, **kwargs)


def setup_logger(settings_path: str = DefaultPath.SETTINGS) -> None:
    """
    Initializes and configures the underlying logger based on central configurations.
    Enforces dual logging: Console/File output and database logging.
    """
    # 1. Clear existing handlers
    _backend_logger.remove()

    # 2. Defaults in case of missing settings
    logs_dir = "logs"
    rotation = "00:00"
    retention = "30 days"
    compression = "zip"
    level = "INFO"

    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            logging_cfg = settings.get("logging", {})
            logs_dir = logging_cfg.get("logs_dir", "logs")
            rotation = logging_cfg.get("rotation", "00:00")
            retention = logging_cfg.get("retention", "30 days")
            compression = logging_cfg.get("compression", "zip")
            level = logging_cfg.get("level", "INFO")
        except Exception:
            pass

    # Ensure logs directory exists
    os.makedirs(logs_dir, exist_ok=True)

    # 3. Add Console Sink (Stderr)
    is_notebook = "ipykernel" in sys.modules or "IPython" in sys.modules
    is_tty = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

    if is_notebook or not is_tty:
        console_format = "[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}"
        colorize = False
    else:
        console_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )
        colorize = True

    _backend_logger.add(
        sys.stderr,
        format=console_format,
        level=level,
        colorize=colorize
    )

    # 4. Add Rotating File Sink
    log_file_path = os.path.join(logs_dir, "app.log")
    _backend_logger.add(
        log_file_path,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=rotation,
        retention=retention,
        compression=compression,
        level=level,
        encoding="utf-8"
    )

    # 5. Add Database Sink to capture application logs automatically via SQLAlchemy ORM
    # In testing environment (TEST_ENVIRONMENT == "1" or APP_ENV == "testing"), bypass DB sink to eliminate disk I/O
    is_test_env = (
        os.environ.get("TEST_ENVIRONMENT") == "1"
        or os.environ.get("APP_ENV", "").lower() == "testing"
    )

    if not is_test_env:
        def db_sink(message):
            try:
                record = message.record
                lvl = record["level"].name
                text = record["message"]
                module = record.get("module") or "app"
                func = record.get("function") or "main"
                created_at = record["time"].isoformat()

                from src.infrastructure.persistence import get_log_db_session, ApplicationLog
                with get_log_db_session() as session:
                    entry = ApplicationLog(
                        level=lvl,
                        message=text,
                        module=module,
                        function=func,
                        created_at=created_at
                    )
                    session.add(entry)
            except Exception:
                pass

        _backend_logger.add(
            db_sink,
            level=level,
            enqueue=True
        )


# Automatically initialize logging engine
setup_logger()

# Global AppLogger singleton instance
logger = AppLogger(_backend_logger)


def get_logger(name: Optional[str] = None) -> AppLogger:
    """Returns a contextual AppLogger instance."""
    if name:
        return logger.bind(module=name)
    return logger
