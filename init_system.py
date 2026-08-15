import sys
import os

# Set Python path to ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.core.initializer import (
    validate_settings_config,
    validate_domain_config,
    validate_environment,
    initialize_storage_directories
)
from src.core.logger import setup_logger
from loguru import logger

def run_system_initialization():
    """
    Performs full system check and directory setup, reporting diagnostics
    via Loguru logger to console and daily log files.
    """
    # 1. Initialize logging
    setup_logger()
    
    logger.info("=========================================================")
    logger.info("  AI-Multi-Docs-Extraction-Pipeline System Initialization")
    logger.info("=========================================================")
    
    has_errors = False
    
    # 2. Validate settings.json
    logger.info("[1/4] Checking Central settings.json...")
    settings_valid, settings_errors = validate_settings_config()
    if not settings_valid:
        logger.error("[FAIL] settings.json has validation errors:")
        for err in settings_errors:
            logger.error(f"     - {err}")
        logger.critical("System initialization stopped due to invalid settings.json.")
        sys.exit(1)
    else:
        logger.info("[PASS] settings.json is valid and complete.")
        
    # Read settings to get active domains
    import json
    with open("configs/settings.json", "r", encoding="utf-8") as f:
        settings = json.load(f)
    active_domains = settings.get("active_domains", [])
    
    # 3. Validate active domains
    logger.info("[2/4] Checking Domain-specific configurations...")
    for domain in active_domains:
        logger.info(f"  * Checking domain '{domain}'...")
        domain_valid, domain_errors = validate_domain_config(domain)
        if not domain_valid:
            logger.error(f"    [FAIL] Domain '{domain}' has configuration errors:")
            for err in domain_errors:
                logger.error(f"       - {err}")
            has_errors = True
        else:
            logger.info(f"    [PASS] Domain '{domain}' configs are valid.")
            
    # 4. Validate environment & dependencies
    logger.info("[3/4] Checking Environment & Package Dependencies...")
    env_warnings = validate_environment()
    
    # Separate errors and warnings from environment check
    env_errors = [msg for msg in env_warnings if "[ERROR]" in msg]
    env_warns = [msg for msg in env_warnings if "[WARNING]" in msg or "[INFO]" in msg]
    
    if env_errors:
        logger.error("[FAIL] System is missing required dependencies:")
        for err in env_errors:
            logger.error(f"     - {err}")
        has_errors = True
    else:
        logger.info("[PASS] All required Python packages are installed.")
        
    if env_warns:
        for warn in env_warns:
            logger.warning(f"     - {warn}")
            
    # 5. Initialize storage directories
    logger.info("[4/4] Initializing Pipeline Storage Directories...")
    ensured_folders = initialize_storage_directories()
    logger.info(f"[PASS] Ensured {ensured_folders} directories are created with .gitkeep.")
    logger.info("=========================================================")
    
    if has_errors:
        logger.error("[SYSTEM STATUS] Initialization completed with errors.")
        logger.error("   Please fix the configuration or dependency issues listed above.")
        sys.exit(1)
    else:
        logger.info("[SYSTEM STATUS] System is READY and fully configured!")
        logger.info("   You can start using the application by running run_app.bat")
        sys.exit(0)

if __name__ == "__main__":
    run_system_initialization()
