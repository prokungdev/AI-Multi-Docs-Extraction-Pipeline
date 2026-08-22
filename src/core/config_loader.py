import os
import json
from functools import lru_cache
from loguru import logger
from src.core.db import get_domains, get_sources

DEFAULT_STORAGE_ROOT = "storage"


@lru_cache(maxsize=4)
def load_system_settings(settings_path: str = "configs/settings.json") -> dict:
    """
    Loads central settings.json with caching.
    """
    if not os.path.exists(settings_path):
        logger.warning(f"Settings file not found at: {settings_path}")
        return {}
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to parse settings.json: {e}")
        return {}


def get_default_domain() -> str:
    """
    Returns the primary active doc_type/domain ID from configs/settings.json.
    Falls back to 'expense_receipt' if no active doc_type is configured.
    """
    active = get_active_domains_hybrid()
    if active:
        return active[0].get("domain_id") or active[0].get("doc_type_id", "expense_receipt")
    return "expense_receipt"


def get_default_doc_type() -> str:
    """
    Alias for get_default_domain().
    """
    return get_default_domain()


def get_active_domains_hybrid() -> list[dict]:
    """
    Returns only doc_types/domains that are active from Database or settings.json.
    """
    try:
        domains = get_domains()
        if domains:
            return [d for d in domains if d.get("is_active") == 1]
    except Exception as e:
        logger.error(f"Error loading active domains from DB: {e}")

    # Fallback to settings.json
    settings = load_system_settings()
    doc_types = settings.get("doc_types") or settings.get("domains", [])
    result = []
    for dt in doc_types:
        if isinstance(dt, dict) and dt.get("is_active", True):
            dt_id = dt.get("doc_type_id") or dt.get("domain_id")
            if dt_id:
                result.append({
                    "domain_id": dt_id,
                    "doc_type_id": dt_id,
                    "display_name": dt.get("display_name", dt_id),
                    "is_active": 1,
                    "sort_order": dt.get("sort_order", 1)
                })
    return result


def get_active_doc_types() -> list[dict]:
    """
    Alias for get_active_domains_hybrid().
    """
    return get_active_domains_hybrid()


def is_domain_active(domain_id: str) -> bool:
    """
    Checks if a domain/doc_type is active.
    """
    active_domains = get_active_domains_hybrid()
    return any(
        (d.get("domain_id") == domain_id or d.get("doc_type_id") == domain_id)
        for d in active_domains
    )


def is_doc_type_active(doc_type_id: str) -> bool:
    """
    Alias for is_domain_active().
    """
    return is_domain_active(doc_type_id)


def get_active_sources_hybrid(domain_id: str) -> list[str]:
    """
    Returns a list of active sources for a doc_type/domain.
    Defaults to ['_default'] when standardized doc_types configs are used.
    """
    try:
        db_sources = get_sources(domain_id)
        active_sources = [s["source_id"] for s in db_sources if s["is_active"] == 1]
        if active_sources:
            return active_sources
    except Exception as e:
        logger.error(f"Error loading active sources for '{domain_id}': {e}")
    return ["_default"]


def is_source_active(domain_id: str, source_id: str) -> bool:
    """
    Checks if a source is active.
    """
    if source_id in ["_default", "default", "standard"]:
        return True
    active_sources = get_active_sources_hybrid(domain_id)
    return source_id in active_sources


def get_doc_type_config_dir(doc_type_id: str, configs_dir: str = "configs") -> str:
    """
    Locates the configuration directory for a given doc_type_id.
    Checks configs/doc_types/{doc_type_id} first, then falls back to configs/domains/{doc_type_id}.
    """
    primary = os.path.join(configs_dir, "doc_types", doc_type_id)
    if os.path.exists(primary):
        return primary
    fallback = os.path.join(configs_dir, "domains", doc_type_id)
    if os.path.exists(fallback):
        return fallback
    return primary


def load_doc_type_schema(doc_type_id: str, configs_dir: str = "configs") -> dict:
    """
    Loads extract-schema.json (or schema.json fallback) for a doc_type.
    """
    cfg_dir = get_doc_type_config_dir(doc_type_id, configs_dir)
    for candidate in ["extract-schema.json", "schema.json"]:
        schema_path = os.path.join(cfg_dir, candidate)
        if os.path.exists(schema_path):
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading schema for '{doc_type_id}': {e}")
    return {}


def load_doc_type_prompt(doc_type_id: str, configs_dir: str = "configs") -> str:
    """
    Loads extract-prompt.txt (or prompt.txt fallback) for a doc_type.
    """
    cfg_dir = get_doc_type_config_dir(doc_type_id, configs_dir)
    for candidate in ["extract-prompt.txt", "prompt.txt"]:
        prompt_path = os.path.join(cfg_dir, candidate)
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"Error loading prompt for '{doc_type_id}': {e}")
    return ""


def load_doc_type_classify_prompt(doc_type_id: str, configs_dir: str = "configs") -> str:
    """
    Loads classify-prompt.txt for a doc_type.
    """
    cfg_dir = get_doc_type_config_dir(doc_type_id, configs_dir)
    prompt_path = os.path.join(cfg_dir, "classify-prompt.txt")
    if os.path.exists(prompt_path):
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading classify prompt for '{doc_type_id}': {e}")
    return ""


def load_doc_type_rules(doc_type_id: str, configs_dir: str = "configs") -> dict:
    """
    Loads extract-rules.json (or rules.json fallback) for a doc_type.
    """
    cfg_dir = get_doc_type_config_dir(doc_type_id, configs_dir)
    for candidate in ["extract-rules.json", "rules.json"]:
        rules_path = os.path.join(cfg_dir, candidate)
        if os.path.exists(rules_path):
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading rules for '{doc_type_id}': {e}")
    return {}


def load_source_rules(domain_id: str, source_id: str = "_default", configs_dir: str = "configs") -> dict:
    """
    Loads rules for a doc_type/domain (backward compatibility layer).
    """
    return load_doc_type_rules(domain_id, configs_dir)


def load_source_ai_config(domain_id: str, source_id: str = "_default", settings: dict = None) -> tuple[str, str]:
    """
    Resolves the AI provider and model name for a specific doc_type/source.
    """
    if settings is None:
        settings = load_system_settings()
        
    provider = None
    model = None
    
    rules = load_doc_type_rules(domain_id)
    if rules:
        provider = rules.get("ai_provider")
        model = rules.get("ai_model")
            
    ai_provider_cfg = settings.get("ai_provider", {})
    if not provider:
        provider = ai_provider_cfg.get("active_provider", "gemini")
    if not model:
        provider_cfg = ai_provider_cfg.get(provider, {})
        model = provider_cfg.get("model_name", "gemini-3.5-flash")
    return provider, model


def get_ai_provider_config(settings: dict = None) -> dict:
    """
    Returns AI provider configuration dictionary.
    """
    if settings is None:
        settings = load_system_settings()
    ai_cfg = settings.get("ai_provider", {})
    max_images = ai_cfg.get("max_images_per_request", settings.get("max_images_per_request", 50))
    active_provider = ai_cfg.get("active_provider", "gemini")
    provider_details = ai_cfg.get(active_provider, {})
    max_concurrent = provider_details.get("max_concurrent_requests", provider_details.get("concurrency", 8))

    return {
        "active_provider": active_provider,
        "max_retries": int(ai_cfg.get("max_retries", 3)),
        "max_images_per_request": int(max_images),
        "model_name": provider_details.get("model_name", "gemini-3.5-flash"),
        "api_key_env": provider_details.get("api_key_env", "GEMINI_API_KEY"),
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
        "split_filename_pattern": img_cfg.get("split_filename_pattern") or img_cfg.get("filename_pattern", "{domain}_{source}_{original_filename}_{batch_id}_p{page_no}"),
        "archive_filename_pattern": img_cfg.get("archive_filename_pattern", "{domain}_{source}_{doc_no}_{batch_id}_p{page_no}"),
        "use_ai_fallback_matching": bool(img_cfg.get("use_ai_fallback_matching", True))
    }


def get_supported_extensions(settings: dict = None) -> list[str]:
    """
    Returns list of supported file extensions for raw inbox documents.
    """
    cfg = get_image_processing_config(settings)
    return [ext.lower() for ext in cfg.get("supported_input_extensions", [])]
