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
    active_domains = settings.get("active_domains")
    pipeline_folders = settings.get("pipeline_folders")
    
    if not storage_root or not isinstance(storage_root, str):
        errors.append("Key 'storage_root' must be a non-empty string in settings.json.")
        
    if active_domains is None or not isinstance(active_domains, list):
        errors.append("Key 'active_domains' must be a list in settings.json.")
    elif len(active_domains) == 0:
        errors.append("Key 'active_domains' list must contain at least one domain in settings.json.")
        
    if pipeline_folders is None or not isinstance(pipeline_folders, list):
        errors.append("Key 'pipeline_folders' must be a list in settings.json.")
    elif len(pipeline_folders) == 0:
        errors.append("Key 'pipeline_folders' list must contain at least one directory name in settings.json.")
        
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
        
    # Validate archiving config block
    archiving_cfg = settings.get("archiving")
    if archiving_cfg is not None:
        if not isinstance(archiving_cfg, dict):
            errors.append("Key 'archiving' must be a dictionary in settings.json.")
        else:
            keep_split_pages = archiving_cfg.get("keep_split_pages")
            split_format = archiving_cfg.get("split_format")
            
            if keep_split_pages is not None and not isinstance(keep_split_pages, bool):
                errors.append("Key 'archiving.keep_split_pages' must be a boolean in settings.json.")
            if split_format is not None:
                if not isinstance(split_format, str):
                    errors.append("Key 'archiving.split_format' must be a string in settings.json.")
                else:
                    valid_formats = ["pdf", "png", "jpg", "jpeg"]
                    parts = [p.strip().lower() for p in split_format.split(",") if p.strip()]
                    for part in parts:
                        if part not in valid_formats:
                            errors.append(f"Invalid format '{part}' in 'archiving.split_format'. Must be one of: {', '.join(valid_formats)}")
            
            filename_pattern = archiving_cfg.get("filename_pattern")
            if filename_pattern is not None:
                if not isinstance(filename_pattern, str):
                    errors.append("Key 'archiving.filename_pattern' must be a string in settings.json.")
                else:
                    required_placeholders = ["{domain}", "{source}", "{doc_no}", "{page_no}"]
                    for ph in required_placeholders:
                        if ph not in filename_pattern:
                            errors.append(f"Missing placeholder '{ph}' in 'archiving.filename_pattern'. Must include: {', '.join(required_placeholders)}")
            
            use_ai_fallback_matching = archiving_cfg.get("use_ai_fallback_matching")
            if use_ai_fallback_matching is not None and not isinstance(use_ai_fallback_matching, bool):
                errors.append("Key 'archiving.use_ai_fallback_matching' must be a boolean in settings.json.")
        
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
    critical_packages = ["fitz", "pandas", "google.genai", "streamlit", "PIL"]
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
    domains = settings.get("active_domains", [])
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

