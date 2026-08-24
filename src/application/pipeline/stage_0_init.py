from src.infrastructure.common.logger import logger
from src.infrastructure.common.config_loader import load_system_settings
from src.infrastructure.persistence import (
    initialize_db_schema,
    initialize_log_db_schema,
    seed_initial_data,
)
from src.application.usecases.initializer import (
    validate_settings_config,
    validate_doc_type_config,
    validate_environment,
    initialize_storage_directories,
)
from src.infrastructure.common.logger import setup_logger


def init_system(settings_path: str = "configs/settings.json", drop_and_recreate: bool = False) -> bool:
    """
    Stage 1: System Initialization & Health Check.
    Validates settings.json, doc_type configs, Python environment, storage folders, and database schemas.
    If drop_and_recreate is True, drops and recreates all operational database tables for a fresh start.
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

    # 2. Validate doc_types
    settings = load_system_settings(settings_path)
    doc_types_data = settings.get("doc_types", [])
    active_doc_types = [
        d.get("doc_type_id")
        for d in doc_types_data
        if isinstance(d, dict) and d.get("is_active", True) and d.get("doc_type_id")
    ]
    if not active_doc_types:
        active_doc_types = ["expense_receipt"]

    logger.info("[2/4] Checking DocType-specific configurations...")
    for dt in active_doc_types:
        logger.info(f"  * Checking doc_type '{dt}'...")
        dt_valid, dt_errors = validate_doc_type_config(dt)
        if not dt_valid:
            logger.error(f"    [FAIL] DocType '{dt}' has configuration errors:")
            for err in dt_errors:
                logger.error(f"       - {err}")
            return False
        logger.info(f"    [PASS] DocType '{dt}' configs are valid.")

    # 3. Check environment & packages
    logger.info("[3/4] Checking Environment & Package Dependencies...")
    env_warnings = validate_environment(settings_path)
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
    initialize_log_db_schema(settings_path)
    initialize_db_schema(drop_and_recreate=drop_and_recreate)
    seed_initial_data(configs_dir=settings_path)
    dir_count = initialize_storage_directories(settings_path)
    logger.info(f"[PASS] Ensured {dir_count} directories are created with .gitkeep.")

    logger.info("[SYSTEM STATUS] System is READY and fully configured!")
    return True
