"""System health check and readiness probe using SQLAlchemy engine inspector."""

import os
from dotenv import load_dotenv
from src.core.logger import logger
from sqlalchemy import inspect

from src.core.config_loader import load_system_settings, get_ai_provider_config
from src.core.db.connection import get_engine


def check_database_status() -> tuple[bool, str]:
    """
    Checks database connection and verifies table accessibility using SQLAlchemy inspector.
    """
    try:
        engine = get_engine()
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return True, f"Connected ({len(tables)} tables verified)"
    except Exception as e:
        return False, f"Database error: {str(e)}"


def check_api_ready(settings: dict) -> tuple[bool, str, list[str]]:
    """
    Checks AI API readiness and credential availability.
    """
    load_dotenv()
    remedies = []

    ai_cfg = get_ai_provider_config(settings)
    provider = ai_cfg.get("active_provider", "gemini")
    api_key_env = ai_cfg.get("api_key_env", "GEMINI_API_KEY")
    api_key = os.getenv(api_key_env)
    has_credentials = bool(api_key and api_key.strip())

    if not has_credentials:
        remedy = f"Environment variable '{api_key_env}' is missing. Please set it in your .env file."
        remedies.append(remedy)
        return False, f"Missing API Key ('{api_key_env}')", remedies

    return True, f"Provider '{provider}' ready", []


def check_storage_status(settings: dict) -> tuple[bool, str, list[str]]:
    """
    Checks storage root and log directory write permissions.
    """
    remedies = []
    from src.core.constants import DefaultPath
    storage_root = settings.get("storage_root", DefaultPath.STORAGE_ROOT)
    logs_dir = settings.get("logging", {}).get("logs_dir", DefaultPath.LOGS_DIR)

    for dir_path, label in [(storage_root, "Storage Root"), (logs_dir, "Logs Directory")]:
        try:
            os.makedirs(dir_path, exist_ok=True)
            probe_file = os.path.join(dir_path, ".health_probe.tmp")
            with open(probe_file, "w", encoding="utf-8") as pf:
                pf.write("probe")
            if os.path.exists(probe_file):
                os.remove(probe_file)
        except Exception as we:
            remedies.append(f"Ensure directory '{dir_path}' has read/write permissions: {we}")
            return False, f"{label} '{dir_path}' write error", remedies

    return True, f"Writable ('{storage_root}', '{logs_dir}')", []


def run_healthcheck(configs_dir: str = "configs") -> dict:
    """
    Runs lightweight System Health Check (Database Status, API Ready, Storage Writable).
    Returns:
        dict containing 'healthy' boolean, 'status' string, 'checks' dict, and 'remedies' list.
    """
    settings_path = os.path.join(configs_dir, "settings.json")
    settings = load_system_settings(settings_path)

    db_ok, db_msg = check_database_status()
    api_ok, api_msg, api_remedies = check_api_ready(settings)
    storage_ok, storage_msg, storage_remedies = check_storage_status(settings)

    all_healthy = db_ok and api_ok and storage_ok
    remedies = api_remedies + storage_remedies

    return {
        "healthy": all_healthy,
        "status": "OK" if all_healthy else "ERROR",
        "checks": {
            "database": {"ok": db_ok, "message": db_msg},
            "api_ready": {"ok": api_ok, "message": api_msg},
            "storage_ready": {"ok": storage_ok, "message": storage_msg}
        },
        "remedies": remedies
    }


def print_healthcheck_report(results: dict) -> None:
    """
    Prints a clean CLI Health Check report to terminal.
    """
    status_title = "SYSTEM READY (OK)" if results["healthy"] else "SYSTEM UNHEALTHY (ERROR)"
    status_tag = "[PASS]" if results["healthy"] else "[FAIL]"

    logger.info(f"System Health Check: {status_tag} {status_title}")
    checks = results["checks"]
    for check_name, details in checks.items():
        symbol = "[OK]  " if details["ok"] else "[FAIL]"
        label = check_name.capitalize().ljust(15)
        logger.info(f" {symbol} {label} : {details['message']}")

    if results["remedies"]:
        logger.warning("Required Remedies / Fix Actions:")
        for idx, remedy in enumerate(results["remedies"], start=1):
            logger.warning(f"   {idx}. {remedy}")
