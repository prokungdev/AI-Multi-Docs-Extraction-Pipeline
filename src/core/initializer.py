import os
import json
import sys
import shutil
from pydantic import ValidationError
from src.core.db import initialize_db_schema, seed_initial_data
from src.core.schemas.settings_schema import SystemSettingsModel

def validate_settings_config(settings_path: str = "configs/settings.json") -> tuple[bool, list[str]]:
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

    # 4. Check active domains
    active_domains = [d for d in validated_model.domains if d.is_active]
    if not active_domains:
        errors.append("No active domains configured in 'domains' list in settings.json.")

    # 5. Check filename pattern placeholders
    split_pattern = validated_model.image_processing.split_filename_pattern
    if "{doc_type}" not in split_pattern and "{domain}" not in split_pattern:
        errors.append("Missing placeholder '{doc_type}' or '{domain}' in 'image_processing.split_filename_pattern'.")
    if "{tax_id}" not in split_pattern and "{source}" not in split_pattern:
        errors.append("Missing placeholder '{tax_id}' or '{source}' in 'image_processing.split_filename_pattern'.")
    if "{page_no}" not in split_pattern:
        errors.append("Missing placeholder '{page_no}' in 'image_processing.split_filename_pattern'.")

    archive_pattern = validated_model.image_processing.archive_filename_pattern
    if "{doc_type}" not in archive_pattern and "{domain}" not in archive_pattern:
        errors.append("Missing placeholder '{doc_type}' or '{domain}' in 'image_processing.archive_filename_pattern'.")
    if "{tax_id}" not in archive_pattern and "{source}" not in archive_pattern:
        errors.append("Missing placeholder '{tax_id}' or '{source}' in 'image_processing.archive_filename_pattern'.")
    for ph in ["{doc_no}", "{page_no}"]:
        if ph not in archive_pattern:
            errors.append(f"Missing placeholder '{ph}' in 'image_processing.archive_filename_pattern'.")

    return len(errors) == 0, errors



def validate_domain_config(domain: str, configs_dir: str = "configs") -> tuple[bool, list[str]]:
    """
    Validates extract-schema.json, extract-prompt.txt, and extract-rules.json for a specific doc_type/domain.
    
    Returns:
        A tuple of (is_valid, error_messages).
    """
    errors = []
    
    # Locate doc_type config directory
    doc_type_dir = os.path.join(configs_dir, "doc_types", domain)
    if not os.path.exists(doc_type_dir):
        doc_type_dir = os.path.join(configs_dir, "domains", domain)
    
    # 1. Check if doc_type directory exists
    if not os.path.exists(doc_type_dir):
        errors.append(f"DocType config directory not found at: {doc_type_dir}")
        return False, errors
        
    # 2. Validate schema.json / extract-schema.json
    schema_path = os.path.join(doc_type_dir, "extract-schema.json")
    if not os.path.exists(schema_path):
        schema_path = os.path.join(doc_type_dir, "schema.json")

    if not os.path.exists(schema_path):
        errors.append(f"[{domain}] extract-schema.json (or schema.json) is missing.")
    else:
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            
            if schema.get("type") != "object":
                errors.append(f"[{domain}] schema.json root type must be 'object'.")
            if not isinstance(schema.get("properties"), dict):
                errors.append(f"[{domain}] schema.json must contain a 'properties' object.")
        except json.JSONDecodeError as e:
            errors.append(f"[{domain}] schema.json is not valid JSON: {e}")
            
    # 3. Validate prompt.txt / extract-prompt.txt
    prompt_path = os.path.join(doc_type_dir, "extract-prompt.txt")
    if not os.path.exists(prompt_path):
        prompt_path = os.path.join(doc_type_dir, "prompt.txt")

    if not os.path.exists(prompt_path):
        errors.append(f"[{domain}] extract-prompt.txt (or prompt.txt) is missing.")
            
    # 4. Validate rules.json / extract-rules.json (optional but recommended)
    rules_path = os.path.join(doc_type_dir, "extract-rules.json")
    if not os.path.exists(rules_path):
        rules_path = os.path.join(doc_type_dir, "rules.json")

    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"[{domain}] rules.json is not valid JSON: {e}")
                
    return len(errors) == 0, errors

def validate_environment() -> list[str]:
    """
    Checks environment configurations and package dependencies.
    
    Returns:
        A list of warning/error messages.
    """
    messages = []
    
    # 1. Check .env file
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            try:
                shutil.copy(".env.example", ".env")
                messages.append("[INFO] Generated .env file from .env.example. Please update your GEMINI_API_KEY in it.")
            except Exception as e:
                messages.append(f"[WARNING] Failed to copy .env.example to .env: {e}")
        else:
            messages.append("[WARNING] .env file is missing and .env.example is not found.")
            
    # 2. Check GEMINI_API_KEY in environment
    if not os.getenv("GEMINI_API_KEY"):
        messages.append("[WARNING] GEMINI_API_KEY is not set. Gemini API calls will fail.")
        
    # 3. Check critical python packages
    critical_packages = ["pymupdf", "pandas", "google.genai", "streamlit", "PIL", "openpyxl"]
    for pkg in critical_packages:
        try:
            __import__(pkg)
        except ImportError:
            messages.append(f"[ERROR] Required python library '{pkg}' is not installed in the environment.")
            
    return messages

def initialize_storage_directories(settings_path: str = "configs/settings.json") -> int:
    """
    Initializes storage directories for all active domains and companies defined in settings.json / database
    and ensures empty folders contain .gitkeep to remain tracked in Git.
    
    Returns:
        The number of directories ensured.
    """
    if not os.path.exists(settings_path):
        return 0
        
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        return 0
        
    root = settings.get("storage_root", "storage")
    default_company_code = settings.get("default_company_code", "C00000_SAMPLE")
    
    # Load active doc_types/domains from settings.json
    doc_types_data = settings.get("doc_types") or settings.get("domains", [])
    doc_types = [
        d.get("doc_type_id") or d.get("domain_id")
        for d in doc_types_data
        if isinstance(d, dict) and d.get("is_active", True) and (d.get("doc_type_id") or d.get("domain_id"))
    ]
    if not doc_types:
        doc_types = ["expense_receipt", "tax_invoice", "withholding_tax"]

    folders = settings.get("pipeline_folders", [
        "01_drop_zone",
        "02_raw_data",
        "03_preprocess",
        "04_processing",
        "05_archive"
    ])
    
    ensured_count = 0

    # 1. Initialize SQLite Database and initial seeds first
    try:
        initialize_db_schema()
        seed_initial_data()
    except Exception as de:
        logger.warning(f"Failed to initialize database during storage setup: {de}")

    # 2. Discover all companies from DB (fallback to default_company_code)
    company_codes = [default_company_code]
    try:
        from src.core.db import get_all_companies
        db_comps = get_all_companies(active_only=True)
        if db_comps:
            company_codes = list(set([c["company_code"] for c in db_comps]))
    except Exception:
        pass

    # Ensure central database directory exists
    db_dir = os.path.join(root, "database")
    os.makedirs(db_dir, exist_ok=True)
    gitkeep_db = os.path.join(db_dir, ".gitkeep")
    if not os.path.exists(gitkeep_db):
        try:
            with open(gitkeep_db, "w", encoding="utf-8") as gf:
                gf.write("# Central SQLite Database Directory\n")
        except Exception:
            pass

    # 3. Setup Company-Centric Storage Hierarchy: storage/companies/{company}/{doc_type}/01..06
    for comp_code in company_codes:
        comp_root = os.path.join(root, "companies", comp_code)
        os.makedirs(comp_root, exist_ok=True)

        # DocType stage folders
        for dt in doc_types:
            dt_root = os.path.join(comp_root, dt)
            os.makedirs(dt_root, exist_ok=True)
            
            for folder in folders:
                path = os.path.join(dt_root, folder)
                os.makedirs(path, exist_ok=True)
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

    # Ensure logging directory exists
    logging_cfg = settings.get("logging", {})
    logs_dir = logging_cfg.get("logs_dir", "logs")
    os.makedirs(logs_dir, exist_ok=True)
            
    return ensured_count

