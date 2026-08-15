import os
import sys
import json
from loguru import logger

def setup_logger(settings_path: str = "configs/settings.json") -> None:
    """
    Sets up Loguru logger sinks (Console & File) based on settings.json.
    Configures log rotation, retention, compression, and levels dynamically.
    """
    # 1. Clear any existing default handlers to avoid double logging
    logger.remove()
    
    # 2. Load settings and logging configuration
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
        except Exception as e:
            print(f"Warning: Failed to load logging configurations from settings.json: {e}. Using defaults.")
            
    # Ensure logs directory exists
    os.makedirs(logs_dir, exist_ok=True)
    
    # 3. Add Console Sink (Stderr) with colored tags
    # Format: [2026-08-15 23:55:07] [INFO] Message
    console_format = "<green>[{time:YYYY-MM-DD HH:mm:ss}]</green> <level>[{level}]</level> {message}"
    logger.add(
        sys.stderr,
        format=console_format,
        level=level,
        colorize=True
    )
    
    # 4. Add File Sink (Daily Rotation, Compression, Retention)
    # Filename format: logs_YYYYMMDD.txt (e.g. logs_20260815.txt)
    log_file_name = "logs_{time:YYYYMMDD}.txt"
    log_file_path = os.path.join(logs_dir, log_file_name).replace("\\", "/")
    
    file_format = "[{time:YYYY-MM-DD HH:mm:ss}] [{level}] {message}"
    
    logger.add(
        log_file_path,
        format=file_format,
        level=level,
        rotation=rotation,
        retention=retention,
        compression=compression,
        encoding="utf-8"
    )
