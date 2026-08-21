import os
from dotenv import load_dotenv
from loguru import logger

from src.core.config_loader import load_system_settings, get_ai_provider_config
from src.core.db.connection import get_database_url, get_db_connection

def check_database_status() -> tuple[bool, str]:
    """
    Checks database connection and basic table accessibility.
    """
    try:
        db_url = get_database_url()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]
        conn.close()
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
    
    # Check fallback credentials table if .env key is missing
    if not api_key:
        try:
            from src.core.db import get_active_credentials
            db_creds = get_active_credentials(provider)
            if db_creds:
                api_key = "DB_CREDENTIAL_FOUND"
        except Exception:
            pass
            
    if not api_key:
        remedy = f"Environment variable '{api_key_env}' is missing. Please set it in your .env file."
        remedies.append(remedy)
        return False, f"Missing API Key ('{api_key_env}')", remedies
        
    return True, f"Provider '{provider}' ready", []

def run_healthcheck(configs_dir: str = "configs") -> dict:
    """
    Runs lightweight System Health Check (Database Status & API Ready).
    Returns:
        dict containing 'healthy' boolean, 'status' string, 'checks' dict, and 'remedies' list.
    """
    settings_path = os.path.join(configs_dir, "settings.json")
    settings = load_system_settings(settings_path)
    
    db_ok, db_msg = check_database_status()
    api_ok, api_msg, api_remedies = check_api_ready(settings)
    
    all_healthy = db_ok and api_ok
    
    return {
        "healthy": all_healthy,
        "status": "OK" if all_healthy else "ERROR",
        "checks": {
            "database": {"ok": db_ok, "message": db_msg},
            "api_ready": {"ok": api_ok, "message": api_msg}
        },
        "remedies": api_remedies
    }

def print_healthcheck_report(results: dict) -> None:
    """
    Prints a clean CLI Health Check report to terminal.
    """
    status_title = "SYSTEM READY (OK)" if results["healthy"] else "SYSTEM UNHEALTHY (ERROR)"
    status_tag = "[PASS]" if results["healthy"] else "[FAIL]"
    
    print("\n==========================================================================")
    print(f"  System Health Check: {status_tag} {status_title}")
    print("==========================================================================")
    
    checks = results["checks"]
    for check_name, details in checks.items():
        symbol = "[OK]  " if details["ok"] else "[FAIL]"
        label = check_name.capitalize().ljust(15)
        print(f" {symbol} {label} : {details['message']}")
        
    if results["remedies"]:
        print("\n--------------------------------------------------------------------------")
        print(" Required Remedies / Fix Actions:")
        for idx, remedy in enumerate(results["remedies"], start=1):
            print(f"   {idx}. {remedy}")
            
    print("==========================================================================\n")
