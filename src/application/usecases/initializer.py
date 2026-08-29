import os
import json
import sys
import shutil
from dotenv import load_dotenv
from pydantic import ValidationError
from src.infrastructure.core.logger import logger
from src.infrastructure.core.constants import (
    DefaultPath,
    DefaultIdentifier,
    PipelineStageFolder,
)
from src.application.dtos.settings_dto import SystemSettingsModel

def validate_settings_config(settings_path: str = DefaultPath.SETTINGS) -> tuple[bool, list[str]]:
    """
    Strictly validates configs/settings.json structure, required keys, and types using SystemSettingsModel.
    
    Returns:
        A tuple of (is_valid, error_messages).
    """
    errors = []
    
    # 1. Check if settings file exists
    if not os.path.exists(settings_path):
        errors.append(f"Settings file not found at: {settings_path}")
        return False, errors
        
    # 2. Try parsing settings.json
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings_dict = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"Settings file is not a valid JSON: {e}")
        return False, errors

    # 3. Strict Schema Validation via Pydantic v2
    try:
        validated_model = SystemSettingsModel.model_validate(settings_dict)
    except ValidationError as ve:
        for err in ve.errors():
            loc_str = " -> ".join(str(loc) for loc in err["loc"])
            errors.append(f"Field '{loc_str}': {err['msg']}")
        return False, errors

    # 4. Check filename pattern placeholders
    split_pattern = validated_model.image_processing.split_filename_pattern
    if "{doc_type}" not in split_pattern:
        errors.append("Missing placeholder '{doc_type}' in 'image_processing.split_filename_pattern'.")
    if "{tax_id}" not in split_pattern:
        errors.append("Missing placeholder '{tax_id}' in 'image_processing.split_filename_pattern'.")
    if "{page_no}" not in split_pattern:
        errors.append("Missing placeholder '{page_no}' in 'image_processing.split_filename_pattern'.")

    archive_pattern = validated_model.image_processing.archive_filename_pattern
    if "{doc_type}" not in archive_pattern:
        errors.append("Missing placeholder '{doc_type}' in 'image_processing.archive_filename_pattern'.")
    if "{tax_id}" not in archive_pattern:
        errors.append("Missing placeholder '{tax_id}' in 'image_processing.archive_filename_pattern'.")
    for ph in ["{doc_no}", "{page_no}"]:
        if ph not in archive_pattern:
            errors.append(f"Missing placeholder '{ph}' in 'image_processing.archive_filename_pattern'.")

    # 5. DocType Configuration & Directory Sync Check via DocTypeRegistry
    from pathlib import Path
    from src.domain.doc_types import DocTypeRegistry
    configs_dir = os.path.dirname(settings_path) or "configs"
    if not (Path(configs_dir) / "doc_types").exists() and Path("configs/doc_types").exists():
        configs_dir = "configs"

    for dt in DocTypeRegistry.list_all():
        if dt.is_active:
            cfg_dir = dt.get_config_dir(configs_dir=configs_dir)
            if not cfg_dir.exists():
                errors.append(f"Active doc_type '{dt.doc_type_id.value}' is missing config directory '{cfg_dir}'.")


    return len(errors) == 0, errors



def validate_doc_type_config(doc_type: str, configs_dir: str = "configs", settings_path: str = DefaultPath.SETTINGS) -> tuple[bool, list[str]]:
    """
    Validates all standard assets for a specific doc_type via DocTypeRegistry.
    
    Returns:
        A tuple of (is_valid, error_messages).
    """
    errors = []
    from src.domain.doc_types import DocTypeRegistry

    try:
        dt = DocTypeRegistry.get(doc_type)
    except KeyError as e:
        return False, [str(e)]

    doc_type_dir = dt.get_config_dir(configs_dir=configs_dir)
    if not doc_type_dir.exists():
        errors.append(f"DocType config directory not found at: {doc_type_dir}")
        return False, errors

    # Check required asset files
    for filename in ["classify-prompt.txt", "classify-schema.json", "extract-prompt.txt", "extract-schema.json", "extract-rules.json"]:
        file_path = doc_type_dir / filename
        if not file_path.exists():
            errors.append(f"[{doc_type}] Missing required asset '{filename}' at '{file_path}'.")
        elif filename.endswith(".json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
                if not isinstance(json_data, dict):
                    errors.append(f"[{doc_type}] '{filename}' must contain a valid JSON object.")
            except Exception as e:
                errors.append(f"[{doc_type}] Failed to parse JSON in '{filename}': {e}")
        elif filename.endswith(".txt"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    errors.append(f"[{doc_type}] Text prompt file '{filename}' is empty.")
            except Exception as e:
                errors.append(f"[{doc_type}] Failed to read prompt in '{filename}': {e}")

    return len(errors) == 0, errors


def validate_environment(settings_path: str = DefaultPath.SETTINGS) -> list[str]:
    """
    Checks environment configurations, active AI provider credentials, database connectivity,
    storage write permissions, and package dependencies.
    
    Returns:
        A list of warning/error messages.
    """
    messages = []
    load_dotenv()
    
    # 1. Load active AI provider configuration from settings.json
    from src.infrastructure.core.config import load_system_settings, get_ai_provider_config
    settings = load_system_settings(settings_path)
    ai_cfg = get_ai_provider_config(settings=settings)
    active_provider = ai_cfg.get("active_provider", "gemini")
    api_key_env = ai_cfg.get("api_key_env")
    
    # 2. Check .env file
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            try:
                shutil.copy(".env.example", ".env")
                messages.append(f"[INFO] Generated .env file from .env.example. Please set {api_key_env} in it.")
            except Exception as e:
                messages.append(f"[WARNING] Failed to copy .env.example to .env: {e}")
        else:
            messages.append("[WARNING] .env file is missing and .env.example is not found.")
            
    # 3. Check active AI Provider API Key in environment
    api_key_val = os.getenv(api_key_env)
    if not api_key_val or not api_key_val.strip():
        messages.append(f"[WARNING] Environment variable '{api_key_env}' for active provider '{active_provider}' is not set in .env. API calls will fail.")
        
    # 4. Check Database Environment Variables (for PostgreSQL production driver)
    db_cfg = settings.get("database", {})
    active_driver = db_cfg.get("active_driver", "sqlite")
    if active_driver == "postgresql":
        pg_url_env = db_cfg.get("postgresql", {}).get("url_env", "DATABASE_URL")
        if not os.getenv(pg_url_env):
            messages.append(f"[ERROR] Database driver is set to 'postgresql', but '{pg_url_env}' is missing in .env.")

    # 5. Storage & Logs Directory Write Permission Probes
    storage_root = settings.get("storage_root", DefaultPath.STORAGE_ROOT)
    logging_cfg = settings.get("logging", {})
    logs_dir = logging_cfg.get("logs_dir", DefaultPath.LOGS_DIR)
    
    for dir_path, label in [(storage_root, "Storage Root"), (logs_dir, "Logs Directory")]:
        try:
            os.makedirs(dir_path, exist_ok=True)
            probe_file = os.path.join(dir_path, ".write_probe.tmp")
            with open(probe_file, "w", encoding="utf-8") as pf:
                pf.write("probe")
            if os.path.exists(probe_file):
                os.remove(probe_file)
        except Exception as we:
            messages.append(f"[ERROR] {label} '{dir_path}' is not writable: {we}")

    # 6. Check critical python packages & image processing capabilities
    critical_packages = ["pymupdf", "pandas", "google.genai", "streamlit", "PIL", "openpyxl"]
    for pkg in critical_packages:
        try:
            __import__(pkg)
        except ImportError:
            messages.append(f"[ERROR] Required python library '{pkg}' is not installed in the environment.")

    # 7. Check image processing extension support
    img_cfg = settings.get("image_processing", {})
    supported_exts = img_cfg.get("supported_input_extensions", [])
    if ".pdf" in supported_exts:
        try:
            import fitz
        except ImportError:
            messages.append("[ERROR] '.pdf' input is supported in settings, but 'pymupdf' (fitz) is not available.")

    return messages

def initialize_storage_directories(settings_path: str = DefaultPath.SETTINGS, clean_staging: bool = False) -> int:
    """
    Initializes storage directories for all active domains and companies defined in settings.json / database
    and ensures empty folders contain .gitkeep to remain tracked in Git.
    If clean_staging is True, wipes all temporary files and staging merchant folders in 02_raw_data, 03_preprocess, 04_processing.
    
    Returns:
        The number of directories ensured.
    """
    if not os.path.exists(settings_path):
        return 0
        
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception as e:
        logger.warning(f"Could not load settings file at '{settings_path}': {e}")
        return 0
        
    root = settings.get("storage_root", "storage")
    default_company_code = settings.get("default_company_code", "C00000_SAMPLE")
    
    # Load active doc_types from settings.json or DocTypeRegistry
    doc_types_data = settings.get("doc_types", [])
    doc_types = [
        d.get("doc_type_id")
        for d in doc_types_data
        if isinstance(d, dict) and d.get("is_active", True) and d.get("doc_type_id")
    ]
    if not doc_types:
        try:
            from src.domain.doc_types import DocTypeRegistry
            doc_types = [dt.doc_type_id.value for dt in DocTypeRegistry.list_active()]
        except Exception:
            doc_types = []

    if not doc_types:
        doc_types = [DefaultIdentifier.DOC_TYPE]

    ensured_count = 0

    # 1. Discover all companies from DB (fallback to default_company_code)
    company_codes = [default_company_code]
    try:
        from src.infrastructure.database import get_all_companies
        db_comps = get_all_companies(active_only=True)
        if db_comps:
            company_codes = list(set([c["company_code"] for c in db_comps]))
    except Exception as e:
        logger.warning(f"Failed to query database companies for storage init (using fallback): {e}")

    # Ensure central database directory exists
    db_dir = os.path.join(root, "database")
    os.makedirs(db_dir, exist_ok=True)
    gitkeep_db = os.path.join(db_dir, ".gitkeep")
    if not os.path.exists(gitkeep_db):
        try:
            with open(gitkeep_db, "w", encoding="utf-8") as gf:
                gf.write("# Central SQLite Database Directory\n")
        except Exception as e:
            logger.warning(f"Failed to create .gitkeep in database directory: {e}")

    # 3. Setup Company-Centric Storage Hierarchy: storage/companies/{company}/{doc_type}/01..06
    from src.domain.doc_types import DocTypeRegistry

    for comp_code in company_codes:
        comp_root = os.path.join(root, "companies", comp_code)
        os.makedirs(comp_root, exist_ok=True)

        # DocType stage folders
        for dt in doc_types:
            dt_root = os.path.join(comp_root, dt)
            os.makedirs(dt_root, exist_ok=True)

            try:
                dt_instance = DocTypeRegistry.get(dt)
                stage_folders = dt_instance.get_stage_folders()
            except Exception:
                stage_folders = PipelineStageFolder.list_all()
            
            for folder in stage_folders:
                path = os.path.join(dt_root, folder)
                os.makedirs(path, exist_ok=True)

                # If clean_staging is requested, wipe staging files/merchant folders in 02, 03, 04
                if clean_staging and folder in ["02_raw_data", "03_preprocess", "04_processing"]:
                    for item in os.listdir(path):
                        if item.startswith(".gitkeep"):
                            continue
                        item_path = os.path.join(path, item).replace("\\", "/")
                        if folder == "02_raw_data" and item == "0000000000000_no_taxid":
                            for f in os.listdir(item_path):
                                if not f.startswith(".gitkeep"):
                                    try:
                                        os.remove(os.path.join(item_path, f))
                                    except Exception:
                                        pass
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path, ignore_errors=True)
                        else:
                            try:
                                os.remove(item_path)
                            except Exception:
                                pass

                gitkeep_path = os.path.join(path, ".gitkeep")
                if not os.path.exists(gitkeep_path):
                    try:
                        with open(gitkeep_path, "w", encoding="utf-8") as gf:
                            gf.write("# Keep directory in git\n")
                    except Exception as e:
                        logger.warning(f"Failed to create .gitkeep in {path}: {e}")
                ensured_count += 1

                # Subfolders inside 01_drop_zone
                if folder == "01_drop_zone":
                    for sub in ["Auto_Scanner", "Upload"]:
                        sub_path = os.path.join(path, sub)
                        os.makedirs(sub_path, exist_ok=True)
                        with open(os.path.join(sub_path, ".gitkeep"), "w", encoding="utf-8") as gf:
                            gf.write("# Keep directory in git\n")
                        ensured_count += 1

                # Subfolder for 02_raw_data/0000000000000_no_taxid
                if folder == "02_raw_data":
                    no_tax_path = os.path.join(path, "0000000000000_no_taxid")
                    os.makedirs(no_tax_path, exist_ok=True)
                    with open(os.path.join(no_tax_path, ".gitkeep"), "w", encoding="utf-8") as gf:
                        gf.write("# Default cash slip folder\n")
                    ensured_count += 1

    # Ensure logging directory exists
    logging_cfg = settings.get("logging", {})
    logs_dir = logging_cfg.get("logs_dir", "logs")
    os.makedirs(logs_dir, exist_ok=True)
            
    return ensured_count

