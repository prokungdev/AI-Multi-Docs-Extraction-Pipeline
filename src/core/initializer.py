import os
import json
import sys
import shutil
from src.core.db import initialize_db_schema, seed_initial_data

def validate_settings_config(settings_path: str = "configs/settings.json") -> tuple[bool, list[str]]:
    """
    Validates configs/settings.json structure and contents.
    
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
            settings = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"Settings file is not a valid JSON: {e}")
        return False, errors
        
    # 3. Check settings keys and types
    storage_root = settings.get("storage_root")
    pipeline_folders = settings.get("pipeline_folders")
    
    if not storage_root or not isinstance(storage_root, str):
        errors.append("Key 'storage_root' must be a non-empty string in settings.json.")
        
    if pipeline_folders is None or not isinstance(pipeline_folders, list):
        errors.append("Key 'pipeline_folders' must be a list in settings.json.")
    elif len(pipeline_folders) == 0:
        errors.append("Key 'pipeline_folders' list must contain at least one directory name in settings.json.")
        
    # Validate domains list inside settings.json as Single Source of Truth
    domains_data = settings.get("domains")
    if domains_data is None or not isinstance(domains_data, list):
        errors.append("Key 'domains' must be a list in settings.json.")
    elif len(domains_data) == 0:
        errors.append("Key 'domains' list must contain at least one domain object in settings.json.")
    else:
        active_domains = [d for d in domains_data if isinstance(d, dict) and d.get("is_active", True)]
        if len(active_domains) == 0:
            errors.append("No active domains configured in 'domains' list in settings.json.")
        for d in domains_data:
            if not isinstance(d, dict) or not d.get("domain_id"):
                errors.append("Each item in 'domains' must be an object with a non-empty 'domain_id'.")

    # Validate ai_provider config block
    ai_provider_cfg = settings.get("ai_provider")
    if ai_provider_cfg is None or not isinstance(ai_provider_cfg, dict):
        errors.append("Key 'ai_provider' must be a dictionary in settings.json.")
    else:
        active_provider = ai_provider_cfg.get("active_provider")
        if not active_provider or not isinstance(active_provider, str):
            errors.append("Key 'ai_provider.active_provider' must be a non-empty string in settings.json.")
        elif active_provider not in ai_provider_cfg or not isinstance(ai_provider_cfg[active_provider], dict):
            errors.append(f"Active provider '{active_provider}' configuration block is missing or not a dictionary in settings.json.")
        else:
            provider_cfg = ai_provider_cfg[active_provider]
            if not provider_cfg.get("model_name") or not isinstance(provider_cfg.get("model_name"), str):
                errors.append(f"Key 'ai_provider.{active_provider}.model_name' must be a non-empty string in settings.json.")
            if not provider_cfg.get("api_key_env") or not isinstance(provider_cfg.get("api_key_env"), str):
                errors.append(f"Key 'ai_provider.{active_provider}.api_key_env' must be a non-empty string in settings.json.")
            concurrency = provider_cfg.get("concurrency")
            if concurrency is not None and (not isinstance(concurrency, int) or concurrency <= 0):
                errors.append(f"Key 'ai_provider.{active_provider}.concurrency' must be a positive integer in settings.json.")
                
        max_retries = ai_provider_cfg.get("max_retries")
        if max_retries is not None and (not isinstance(max_retries, int) or max_retries <= 0):
            errors.append("Key 'ai_provider.max_retries' must be a positive integer in settings.json.")

    # Validate logging config block
    logging_cfg = settings.get("logging")
    if logging_cfg is None or not isinstance(logging_cfg, dict):
        errors.append("Key 'logging' must be a dictionary in settings.json.")
    else:
        logs_dir = logging_cfg.get("logs_dir")
        rotation = logging_cfg.get("rotation")
        retention = logging_cfg.get("retention")
        compression = logging_cfg.get("compression")
        level = logging_cfg.get("level")
        
        if not logs_dir or not isinstance(logs_dir, str):
            errors.append("Key 'logging.logs_dir' must be a non-empty string in settings.json.")
        if rotation is not None and not isinstance(rotation, str):
            errors.append("Key 'logging.rotation' must be a string or null in settings.json.")
        if retention is not None and not isinstance(retention, str):
            errors.append("Key 'logging.retention' must be a string or null in settings.json.")
        if compression is not None and not isinstance(compression, str):
            errors.append("Key 'logging.compression' must be a string or null in settings.json.")
        if not level or not isinstance(level, str):
            errors.append("Key 'logging.level' must be a non-empty string in settings.json.")
        
    # Validate image_processing config block
    img_cfg = settings.get("image_processing")
    if img_cfg is not None:
        if not isinstance(img_cfg, dict):
            errors.append("Key 'image_processing' must be a dictionary in settings.json.")
        else:
            supported_exts = img_cfg.get("supported_input_extensions")
            if supported_exts is not None and (not isinstance(supported_exts, list) or len(supported_exts) == 0):
                errors.append("Key 'image_processing.supported_input_extensions' must be a non-empty list in settings.json.")
                
            processing_format = img_cfg.get("processing_format")
            if processing_format is not None and not isinstance(processing_format, str):
                errors.append("Key 'image_processing.processing_format' must be a string in settings.json.")
                
            split_pattern = img_cfg.get("split_filename_pattern") or img_cfg.get("filename_pattern")
            if split_pattern is not None:
                if not isinstance(split_pattern, str):
                    errors.append("Key 'image_processing.split_filename_pattern' must be a string in settings.json.")
                else:
                    for ph in ["{domain}", "{source}", "{page_no}"]:
                        if ph not in split_pattern:
                            errors.append(f"Missing placeholder '{ph}' in 'image_processing.split_filename_pattern'.")
                            
            archive_pattern = img_cfg.get("archive_filename_pattern")
            if archive_pattern is not None:
                if not isinstance(archive_pattern, str):
                    errors.append("Key 'image_processing.archive_filename_pattern' must be a string in settings.json.")
                else:
                    for ph in ["{domain}", "{source}", "{doc_no}", "{page_no}"]:
                        if ph not in archive_pattern:
                            errors.append(f"Missing placeholder '{ph}' in 'image_processing.archive_filename_pattern'.")
                            
            use_ai_fallback = img_cfg.get("use_ai_fallback_matching")
            if use_ai_fallback is not None and not isinstance(use_ai_fallback, bool):
                errors.append("Key 'image_processing.use_ai_fallback_matching' must be a boolean in settings.json.")
        
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
    Initializes storage directories for all active domains defined in settings.json
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
    for dt in doc_types:
        for folder in folders:
            path = os.path.join(root, dt, folder)
            os.makedirs(path, exist_ok=True)
            
            gitkeep_path = os.path.join(path, ".gitkeep")
            if not os.path.exists(gitkeep_path):
                try:
                    with open(gitkeep_path, "w", encoding="utf-8") as gf:
                        gf.write("# Keep directory in git\n")
                except Exception as e:
                    logger.warning(f"Failed to create .gitkeep in {path}: {e}")
            ensured_count += 1
            
        # 1. Setup 01_drop_zone subfolders: Auto_Scanner and Upload
        drop_zone_path = os.path.join(root, dt, "01_drop_zone")
        for sub in ["Auto_Scanner", "Upload"]:
            sub_path = os.path.join(drop_zone_path, sub)
            os.makedirs(sub_path, exist_ok=True)
            with open(os.path.join(sub_path, ".gitkeep"), "w", encoding="utf-8") as gf:
                gf.write("# Keep directory in git\n")
            ensured_count += 1
            
        # 2. Setup 02_raw_data subfolders: PENDING, IGNORED, NO_TAXID, UNDEFINED
        raw_data_path = os.path.join(root, dt, "02_raw_data")
        for sub in ["PENDING", "IGNORED", "NO_TAXID", "UNDEFINED"]:
            sub_path = os.path.join(raw_data_path, sub)
            os.makedirs(sub_path, exist_ok=True)
            with open(os.path.join(sub_path, ".gitkeep"), "w", encoding="utf-8") as gf:
                gf.write("# Keep directory in git\n")
            ensured_count += 1
            
        # Try loading merchants from DB to create merchant subfolders under 02_raw_data
        try:
            from src.core.db import get_all_merchants
            merchants = get_all_merchants()
            for m in merchants:
                tax_id = m.get("tax_id") or "NO_TAXID"
                name = (m.get("merchant_name") or "merchant").lower().replace(" ", "_")
                m_folder = f"{tax_id}_{name}" if tax_id != "NO_TAXID" else name
                m_path = os.path.join(raw_data_path, m_folder)
                os.makedirs(m_path, exist_ok=True)
                with open(os.path.join(m_path, ".gitkeep"), "w", encoding="utf-8") as gf:
                    gf.write("# Keep directory in git\n")
                ensured_count += 1
        except Exception:
            pass
            
    # Ensure logging directory exists
    logging_cfg = settings.get("logging", {})
    logs_dir = logging_cfg.get("logs_dir", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Initialize centralized SQLite database
    try:
        initialize_db_schema()
        seed_initial_data()
    except Exception as de:
        logger.warning(f"Failed to initialize SQLite database: {de}")
            
    return ensured_count

