"""System health check and readiness probe using SQLAlchemy engine inspector."""

import os
from dotenv import load_dotenv
from sqlalchemy import inspect

from .logger import logger
from .config import load_system_settings, get_ai_provider_config
from .constants import DefaultPath
def check_database_status() -> tuple[bool, str]:
    """
    Checks database connection and verifies table accessibility using SQLAlchemy inspector.
    """
    try:
        from src.infrastructure.database.engine import get_engine
        engine = get_engine()
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return True, f"Connected ({len(tables)} tables verified)"
    except Exception as e:
        return False, f"Database error: {str(e)}"


def check_api_ready(settings: dict = None) -> tuple[bool, str, list[str]]:
    """Checks AI API readiness and credential availability."""
    load_dotenv()
    remedies = []

    try:
        if isinstance(settings, dict) and "ai_provider" in settings:
            ai_prov = settings.get("ai_provider", {})
            provider = ai_prov.get("active_provider", "gemini")
            tier = ai_prov.get("billing_tier", "free").strip().lower()
            api_key_env = ai_prov.get(provider, {}).get(f"api_key_env_{tier}", "GEMINI_API_KEY_FREE")
        else:
            from src.infrastructure.database import get_resolved_ai_config
            ai_cfg = get_resolved_ai_config()
            provider = ai_cfg["provider"]
            api_key_env = ai_cfg["api_key_env_var"]
    except Exception as e:
        return False, f"Invalid AI configuration: {e}", [f"Fix AI configuration: {e}"]

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
    """Prints formatted healthcheck diagnostic report to console."""
    print("==========================================================")
    print(f" System Healthcheck Diagnostic Report — [{results.get('status', 'UNKNOWN')}]")
    print("==========================================================")
    for check_name, info in results.get("checks", {}).items():
        status_symbol = "✓" if info.get("ok") else "✗"
        print(f" [{status_symbol}] {check_name}: {info.get('message')}")
    
    if results.get("remedies"):
        print("\n[!] Recommended Actions / Remedies:")
        for remedy in results["remedies"]:
            print(f"  - {remedy}")
    print("==========================================================")

