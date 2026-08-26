import os
import json
from functools import lru_cache
from src.infrastructure.common.logger import logger
from src.infrastructure.persistence import get_doc_types
from src.infrastructure.common.constants import (
    DefaultPath,
    DefaultIdentifier,
    AppMetadata,
)


@lru_cache(maxsize=4)
def load_system_settings(settings_path: str = DefaultPath.SETTINGS) -> dict:
    """Loads central system settings from JSON with LRU caching."""
    if not os.path.exists(settings_path):
        raise FileNotFoundError(f"Required system configuration file not found at: '{settings_path}'")
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to parse settings.json at '{settings_path}': {e}")
        raise


def get_app_metadata(settings_path: str = DefaultPath.SETTINGS) -> dict:
    """Returns application metadata with fallback to static constants."""
    settings = load_system_settings(settings_path)
    return {
        "app_name": settings.get("app_name", AppMetadata.NAME),
        "app_version": settings.get("app_version", AppMetadata.VERSION),
        "app_description": settings.get("app_description", AppMetadata.DESCRIPTION),
    }


def get_validation_thresholds(settings_path: str = DefaultPath.SETTINGS) -> dict:
    """Returns validation thresholds dictionary from settings.json."""
    settings = load_system_settings(settings_path)
    if "validation_thresholds" not in settings:
        raise KeyError("Required configuration 'validation_thresholds' is missing in settings.json.")
    return settings["validation_thresholds"]


def resolve_doc_type(doc_type: str = None) -> str:
    """
    Resolves target doc_type with fallback to configured default.
    """
    if doc_type and str(doc_type).strip():
        return str(doc_type).strip()
    return get_default_doc_type()


def resolve_company_code(company_code: str = None) -> str:
    """
    Resolves target company code with fallback to configured default.
    """
    if company_code and str(company_code).strip():
        return str(company_code).strip()
    return get_default_company_code()


def get_default_doc_type() -> str:
    """
    Returns the primary active doc_type ID from configs/settings.json or database.
    """
    active = get_active_doc_types()
    if active:
        return active[0].get("doc_type_id") or active[0].get("domain_id", DefaultIdentifier.DOC_TYPE)
    return DefaultIdentifier.DOC_TYPE


def get_active_doc_types() -> list[dict]:
    """
    Returns only doc_types that are active from Database or settings.json.
    """
    try:
        doc_types = get_doc_types()
        if doc_types:
            return [d for d in doc_types if d.get("is_active") == 1]
    except Exception as e:
        logger.error(f"Error loading active doc_types from DB: {e}")

    # Fallback to settings.json
    settings = load_system_settings()
    doc_types = settings.get("doc_types", [])
    result = []
    for dt in doc_types:
        if isinstance(dt, dict) and dt.get("is_active", True):
            dt_id = dt.get("doc_type_id")
            if dt_id:
                result.append({
                    "doc_type_id": dt_id,
                    "display_name": dt.get("display_name", dt_id),
                    "is_active": 1,
                    "sort_order": dt.get("sort_order", 1)
                })
    return result


def is_doc_type_active(doc_type_id: str) -> bool:
    """
    Checks if a doc_type is active.
    """
    active_types = get_active_doc_types()
    return any(d.get("doc_type_id") == doc_type_id for d in active_types)



def get_default_company_code() -> str:
    """
    Returns the default company code from settings.json or defaults to DefaultIdentifier.COMPANY_CODE.
    """
    settings = load_system_settings()
    return settings.get("default_company_code", DefaultIdentifier.COMPANY_CODE)


def get_company_storage_dir(company_code: str = None, storage_root: str = None) -> str:
    """
    Returns the root storage directory for a specific company (e.g. storage/companies/C00000_SAMPLE).
    """
    if storage_root is None:
        settings = load_system_settings()
        storage_root = settings.get("storage_root", DefaultPath.STORAGE_ROOT)
    code = company_code or get_default_company_code()
    return os.path.join(storage_root, "companies", code)


def get_company_pipeline_folder(company_code: str = None, folder_name: str = "01_drop_zone", doc_type_id: str = None) -> str:
    """
    Returns the path to a specific pipeline folder for a company (e.g. storage/companies/C00000_SAMPLE/expense_receipt/01_drop_zone).
    """
    base_comp_dir = get_company_storage_dir(company_code)
    if doc_type_id:
        return os.path.join(base_comp_dir, doc_type_id, folder_name)
    return os.path.join(base_comp_dir, folder_name)


def get_doc_type_config_dir(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> str:
    """
    Locates the configuration directory for a given doc_type_id.
    Performs layered lookup:
      1. Checks configs/companies/{company_code}/doc_types/{doc_type_id} if company_code is provided.
      2. Falls back to configs/doc_types/{doc_type_id} (system standard).
    """
    if company_code:
        company_specific = os.path.join(configs_dir, "companies", company_code, "doc_types", doc_type_id)
        if os.path.exists(company_specific):
            return company_specific

    return os.path.join(configs_dir, "doc_types", doc_type_id)


def get_doctype_file_path(
    doc_type_id: str,
    file_key: str,
    company_code: str = None,
    configs_dir: str = "configs",
    settings_path: str = DefaultPath.SETTINGS
) -> str:
    """
    Resolves the exact file path for a doc_type based on settings.json 'files' configuration.
    Fail-Fast: Raises KeyError or FileNotFoundError if doc_type, file_key, or file on disk is missing.
    """
    settings = load_system_settings(settings_path)
    doc_types = settings.get("doc_types", [])
    matched_dt = next((dt for dt in doc_types if dt.get("doc_type_id") == doc_type_id), None)
    if not matched_dt:
        raise KeyError(f"DocType '{doc_type_id}' is not registered in 'doc_types' within '{settings_path}'")

    files_cfg = matched_dt.get("files")
    if not files_cfg or not isinstance(files_cfg, dict):
        raise KeyError(f"Missing required 'files' configuration for doc_type '{doc_type_id}' in '{settings_path}'")

    file_name = files_cfg.get(file_key)
    if not file_name:
        raise KeyError(f"File key '{file_key}' is not defined in 'files' for doc_type '{doc_type_id}' in '{settings_path}'")

    cfg_dir = get_doc_type_config_dir(doc_type_id, company_code=company_code, configs_dir=configs_dir)
    full_path = os.path.join(cfg_dir, file_name).replace("\\", "/")
    if not os.path.exists(full_path):
        raise FileNotFoundError(
            f"Configured file '{file_name}' (key: '{file_key}') for doc_type '{doc_type_id}' not found at: '{full_path}'"
        )

    return full_path


def load_doc_type_schema(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> dict:
    """Loads extraction JSON schema for a doc_type."""
    schema_path = get_doctype_file_path(doc_type_id, "extract_schema", company_code=company_code, configs_dir=configs_dir)
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_doc_type_classify_schema(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> dict:
    """Loads classifier JSON schema for a doc_type."""
    schema_path = get_doctype_file_path(doc_type_id, "classify_schema", company_code=company_code, configs_dir=configs_dir)
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_doc_type_prompt(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> str:
    """Loads extraction prompt text for a doc_type."""
    prompt_path = get_doctype_file_path(doc_type_id, "extract_prompt", company_code=company_code, configs_dir=configs_dir)
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_doc_type_classify_prompt(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> str:
    """Loads classifier prompt text for a doc_type."""
    prompt_path = get_doctype_file_path(doc_type_id, "classify_prompt", company_code=company_code, configs_dir=configs_dir)
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_doc_type_rules(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> dict:
    """Loads extraction business rules JSON for a doc_type."""
    rules_path = get_doctype_file_path(doc_type_id, "extract_rules", company_code=company_code, configs_dir=configs_dir)
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_doc_type_ai_config(doc_type_id: str, settings: dict = None) -> tuple[str, str]:
    """
    Resolves the AI provider and model name for a specific doc_type.
    """
    if settings is None:
        settings = load_system_settings()

    provider = None
    model = None

    try:
        rules = load_doc_type_rules(doc_type_id)
        if rules:
            provider = rules.get("ai_provider")
            model = rules.get("ai_model")
    except Exception:
        pass

    ai_provider_cfg = settings.get("ai_provider", {})
    if not provider:
        provider = ai_provider_cfg.get("active_provider")
        if not provider:
            raise ValueError(f"Missing 'active_provider' in 'ai_provider' settings.")

    if not model:
        provider_cfg = ai_provider_cfg.get(provider, {})
        model = provider_cfg.get("model_name")
        if not model:
            raise ValueError(f"Missing required 'model_name' for AI provider '{provider}' in settings.")

    return provider, model


def get_ai_provider_config(settings: dict = None) -> dict:
    """Returns AI provider configuration dictionary."""
    if settings is None:
        settings = load_system_settings()
    ai_cfg = settings.get("ai_provider", {})
    active_provider = ai_cfg.get("active_provider")
    if not active_provider:
        raise ValueError("Missing required 'active_provider' in 'ai_provider' settings.")

    provider_details = ai_cfg.get(active_provider, {})
    model_name = provider_details.get("model_name")
    if not model_name:
        raise ValueError(f"Missing required 'model_name' for AI provider '{active_provider}' in settings.")

    billing_tier = ai_cfg.get("billing_tier", "free").strip().lower()
    target_key = f"api_key_env_{billing_tier}"
    api_key_env = provider_details.get(target_key)
    if not api_key_env:
        raise ValueError(f"Missing required '{target_key}' for AI provider '{active_provider}' (billing_tier='{billing_tier}') in settings.")

    max_images = ai_cfg.get("max_images_per_request", settings.get("max_images_per_request", 50))
    max_concurrent = provider_details.get("max_concurrent_requests", provider_details.get("concurrency", 8))

    return {
        "active_provider": active_provider,
        "billing_tier": billing_tier,
        "max_retries": int(ai_cfg.get("max_retries", 3)),
        "max_images_per_request": int(max_images),
        "model_name": model_name,
        "api_key_env": api_key_env,
        "max_concurrent_requests": int(max_concurrent)
    }


def get_image_processing_config(settings: dict = None) -> dict:
    """
    Returns image processing settings (format, quality, max_dimension, dpi).
    """
    if settings is None:
        settings = load_system_settings()
    img_cfg = settings.get("image_processing", {})
    return {
        "supported_input_extensions": img_cfg.get("supported_input_extensions", [".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tiff"]),
        "processing_format": img_cfg.get("processing_format", "jpg").lower().replace(".", ""),
        "jpeg_quality": int(img_cfg.get("jpeg_quality", 85)),
        "max_dimension": int(img_cfg.get("max_dimension", 1800)),
        "dpi": int(img_cfg.get("dpi", 150)),
        "split_filename_pattern": img_cfg.get("split_filename_pattern") or img_cfg.get("filename_pattern", "{doc_type}_{tax_id}_{original_filename}_{batch_id}_p{page_no}"),
        "archive_filename_pattern": img_cfg.get("archive_filename_pattern", "{doc_type}_{tax_id}_{doc_no}_{batch_id}_p{page_no}"),
        "use_ai_fallback_matching": bool(img_cfg.get("use_ai_fallback_matching", True))
    }


def get_supported_extensions(settings: dict = None) -> list[str]:
    """
    Returns list of supported file extensions for raw inbox documents.
    """
    cfg = get_image_processing_config(settings)
    return [ext.lower() for ext in cfg.get("supported_input_extensions", [])]
