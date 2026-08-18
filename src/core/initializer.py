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
    Validates schema.json, merchant rules, prompts, and output templates for a specific domain.
    
    Returns:
        A tuple of (is_valid, error_messages).
    """
    errors = []
    domain_dir = os.path.join(configs_dir, "domains", domain)
    
    # 1. Check if domain directory exists
    if not os.path.exists(domain_dir):
        errors.append(f"Domain config directory not found at: {domain_dir}")
        return False, errors
        
    # 2. Validate schema.json
    schema_path = os.path.join(domain_dir, "schema.json")
    if not os.path.exists(schema_path):
        errors.append(f"[{domain}] schema.json is missing.")
    else:
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            
            # Simple validation on schema fields
            if schema.get("type") != "object":
                errors.append(f"[{domain}] schema.json root type must be 'object'.")
            if not isinstance(schema.get("properties"), dict):
                errors.append(f"[{domain}] schema.json must contain a 'properties' object.")
        except json.JSONDecodeError as e:
            errors.append(f"[{domain}] schema.json is not valid JSON: {e}")
            
    # 3. Validate sources/ directory
    sources_dir = os.path.join(domain_dir, "sources")
    if not os.path.exists(sources_dir):
        errors.append(f"[{domain}] 'sources/' folder is missing.")
    else:
        # Check for _default
        default_dir = os.path.join(sources_dir, "_default")
        if not os.path.exists(default_dir):
            errors.append(f"[{domain}] Default fallback source 'sources/_default/' is missing.")
            
        # Loop through all sources folders
        for entry in os.listdir(sources_dir):
            entry_path = os.path.join(sources_dir, entry)
            if os.path.isdir(entry_path):
                rules_path = os.path.join(entry_path, "rules.json")
                prompt_path = os.path.join(entry_path, "prompt.txt")
                
                if not os.path.exists(prompt_path):
                    errors.append(f"[{domain}] Source '{entry}' is missing prompt.txt.")
                    
                if not os.path.exists(rules_path):
                    errors.append(f"[{domain}] Source '{entry}' is missing rules.json.")
                else:
                    try:
                        with open(rules_path, "r", encoding="utf-8") as f:
                            rules = json.load(f)
                            
                        # _default doesn't require matching rules keywords/tax_ids, but other sources do
                        if entry != "_default":
                            if not isinstance(rules.get("keywords"), list):
                                errors.append(f"[{domain}] Source '{entry}' rules.json 'keywords' must be a list.")
                            if not isinstance(rules.get("tax_ids"), list):
                                errors.append(f"[{domain}] Source '{entry}' rules.json 'tax_ids' must be a list.")
                    except json.JSONDecodeError as e:
                        errors.append(f"[{domain}] Source '{entry}' rules.json is not valid JSON: {e}")
                        
    # 4. Validate outputs/ directory
    outputs_dir = os.path.join(domain_dir, "outputs")
    if not os.path.exists(outputs_dir):
        errors.append(f"[{domain}] 'outputs/' conversion folder is missing.")
    else:
        templates = [f for f in os.listdir(outputs_dir) if f.endswith(".json")]
        if not templates:
            errors.append(f"[{domain}] 'outputs/' must contain at least one JSON mapping template.")
            
        for template in templates:
            template_path = os.path.join(outputs_dir, template)
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    tpl = json.load(f)
                
                granularity = tpl.get("granularity")
                columns = tpl.get("columns")
                
                if granularity not in ("summary", "line_items"):
                    errors.append(f"[{domain}] Template '{template}' granularity must be 'summary' or 'line_items'.")
                if not isinstance(columns, dict):
                    errors.append(f"[{domain}] Template '{template}' columns must be a key-value mapping object.")
            except json.JSONDecodeError as e:
                errors.append(f"[{domain}] Template '{template}' is not valid JSON: {e}")
                
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
        
    root = settings.get("storage_root", "pipeline_storage")
    
    # Load active domains from settings.json
    domains_data = settings.get("domains", [])
    domains = [d.get("domain_id") for d in domains_data if isinstance(d, dict) and d.get("is_active", True) and d.get("domain_id")]
    if not domains:
        domains = ["expense_receipt"]

    folders = settings.get("pipeline_folders", [])
    
    ensured_count = 0
    for domain in domains:
        for folder in folders:
            path = os.path.join(root, domain, folder)
            os.makedirs(path, exist_ok=True)
            
            # Ensure .gitkeep exists inside empty directory
            gitkeep_path = os.path.join(path, ".gitkeep")
            if not os.path.exists(gitkeep_path):
                try:
                    with open(gitkeep_path, "w", encoding="utf-8") as gf:
                        gf.write("# Keep directory in git\n")
                except Exception as e:
                    print(f"Warning: Failed to create .gitkeep in {path}: {e}")
            ensured_count += 1
            
        # Special setup for 01_raw_inbox merchant subfolders
        inbox_path = os.path.join(root, domain, "01_raw_inbox")
        if os.path.exists(inbox_path):
            # Create _uncategorized fallback folder
            uncat_path = os.path.join(inbox_path, "_uncategorized")
            os.makedirs(uncat_path, exist_ok=True)
            with open(os.path.join(uncat_path, ".gitkeep"), "w", encoding="utf-8") as gf:
                gf.write("# Keep directory in git\n")
            ensured_count += 1
            
            # Discover and create subfolder for each merchant
            sources_dir = os.path.join("configs", "domains", domain, "sources")
            if os.path.exists(sources_dir):
                for entry in os.listdir(sources_dir):
                    entry_path = os.path.join(sources_dir, entry)
                    if os.path.isdir(entry_path) and not entry.startswith("_"):
                        merchant_inbox_path = os.path.join(inbox_path, entry)
                        os.makedirs(merchant_inbox_path, exist_ok=True)
                        with open(os.path.join(merchant_inbox_path, ".gitkeep"), "w", encoding="utf-8") as gf:
                            gf.write("# Keep directory in git\n")
                        ensured_count += 1
            
    # Ensure logging directory exists
    logging_cfg = settings.get("logging", {})
    logs_dir = logging_cfg.get("logs_dir", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Initialize centralized SQLite database
    try:
        initialize_db_schema()
        seed_initial_data()
    except Exception as de:
        print(f"Warning: Failed to initialize SQLite database: {de}")
            
    return ensured_count

