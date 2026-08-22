from loguru import logger
from src.core.config_loader import load_system_settings
from src.core.db import (
    initialize_db_schema,
    initialize_log_db_schema,
    seed_initial_data,
)
from src.core.initializer import (
    validate_settings_config,
    validate_domain_config,
    validate_environment,
    initialize_storage_directories,
)
from src.core.logger import setup_logger


def init_system(settings_path: str = "configs/settings.json") -> bool:
    """
    Stage 1: System Initialization & Health Check.
    Validates settings.json, domain configs, Python environment, storage folders, and database schemas.
    """
    setup_logger(settings_path)
    logger.info("Starting Stage 1 (Init): System Initialization & Health Check")

    # 1. Validate central settings.json
    logger.info("[1/4] Checking Central settings.json...")
    settings_valid, settings_errors = validate_settings_config(settings_path)
    if not settings_valid:
        logger.error("[FAIL] settings.json has validation errors:")
        for err in settings_errors:
            logger.error(f"     - {err}")
        return False
    logger.info("[PASS] settings.json is valid and complete.")

    # 2. Validate domains
    settings = load_system_settings(settings_path)
    domains_data = settings.get("domains", [])
    active_domains = [
        d.get("domain_id")
        for d in domains_data
        if isinstance(d, dict) and d.get("is_active", True) and d.get("domain_id")
    ]
    if not active_domains:
        active_domains = ["expense_receipt"]

    logger.info("[2/4] Checking Domain-specific configurations...")
    for domain in active_domains:
        logger.info(f"  * Checking domain '{domain}'...")
        domain_valid, domain_errors = validate_domain_config(domain)
        if not domain_valid:
            logger.error(f"    [FAIL] Domain '{domain}' has configuration errors:")
            for err in domain_errors:
                logger.error(f"       - {err}")
            return False
        logger.info(f"    [PASS] Domain '{domain}' configs are valid.")

    # 3. Check environment & packages
    logger.info("[3/4] Checking Environment & Package Dependencies...")
    env_warnings = validate_environment()
    has_errors = any("[ERROR]" in msg for msg in env_warnings)
    if has_errors:
        logger.error("[FAIL] System is missing required dependencies:")
        for msg in env_warnings:
            logger.error(f"     - {msg}")
        return False
    logger.info("[PASS] All required Python packages are installed.")
    for msg in env_warnings:
        if "[WARNING]" in msg:
            logger.warning(f"     - {msg}")

    # 4. Initialize storage directories & Database Schema
    logger.info("[4/4] Initializing Pipeline Storage Directories & DB Schema...")
    initialize_log_db_schema()
    initialize_db_schema()
    seed_initial_data()
    dir_count = initialize_storage_directories(settings_path)
    logger.info(f"[PASS] Ensured {dir_count} directories are created with .gitkeep.")

    logger.info("[SYSTEM STATUS] System is READY and fully configured!")
    return True
