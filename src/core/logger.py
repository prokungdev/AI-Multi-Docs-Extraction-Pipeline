import os
import sys
from loguru import logger
from src.core.config_loader import load_system_settings


def setup_logger(settings_path: str = "configs/settings.json"):
    """
    Initializes and configures the Loguru logger based on central configurations.
    Enforces dual logging: Console/File output and database logging.
    """
    # 1. Clear existing handlers
    logger.remove()

    # 2. Defaults in case of missing settings
    logs_dir = "logs"
    rotation = "00:00"
    retention = "30 days"
    compression = "zip"
    level = "INFO"

    if os.path.exists(settings_path):
        try:
            settings = load_system_settings(settings_path)
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

    logger.add(
        sys.stderr,
        format=console_format,
        level=level,
        colorize=colorize
    )

    # 4. Add Rotating File Sink
    log_file_path = os.path.join(logs_dir, "app.log")
    logger.add(
        log_file_path,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=rotation,
        retention=retention,
        compression=compression,
        level=level,
        encoding="utf-8"
    )

    # 5. Add Database Sink to capture application logs automatically via SQLAlchemy ORM
    def db_sink(message):
        try:
            record = message.record
            lvl = record["level"].name
            text = record["message"]
            module = record.get("module") or "app"
            func = record.get("function") or "main"
            created_at = record["time"].isoformat()

            from src.core.db import get_db_session, ApplicationLog
            with get_db_session() as session:
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

    logger.add(
        db_sink,
        level=level,
        enqueue=True
    )


# Automatically initialize the logger when this module is imported
setup_logger()
