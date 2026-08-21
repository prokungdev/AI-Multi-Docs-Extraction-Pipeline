import os
import json
from functools import lru_cache
from loguru import logger
from src.core.db import get_domains, get_sources

DEFAULT_STORAGE_ROOT = "pipeline_storage"

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
    Returns the primary active domain ID from configs/settings.json.
    Falls back to 'expense_receipt' if no active domain is configured.
    """
    active = get_active_domains_hybrid()
    if active:
        return active[0].get("domain_id", "expense_receipt")
    return "expense_receipt"

def get_active_domains_hybrid() -> list[dict]:
    """
    Returns only domains that are active from configs/settings.json.
    """
    try:
        domains = get_domains()
        return [d for d in domains if d.get("is_active") == 1]
    except Exception as e:
        logger.error(f"Error loading active domains: {e}")
        return []

def get_active_sources_hybrid(domain_id: str) -> list[str]:
    """
    Returns a list of source_ids for a domain that are marked active in DB.
    """
    try:
        db_sources = get_sources(domain_id)
        active_sources = [s["source_id"] for s in db_sources if s["is_active"] == 1]
        return active_sources
    except Exception as e:
        logger.error(f"Error loading active sources for domain '{domain_id}': {e}")
        # Fallback to scanning file system
        sources_dir = f"configs/domains/{domain_id}/sources"
        if os.path.exists(sources_dir):
            sources = ["_default"]
            for entry in os.listdir(sources_dir):
                entry_path = os.path.join(sources_dir, entry)
                if os.path.isdir(entry_path) and not entry.startswith("_"):
                    sources.append(entry)
            return sources
        return ["_default"]

def is_domain_active(domain_id: str) -> bool:
    """
    Checks if a domain is active.
    """
    active_domains = get_active_domains_hybrid()
    return any(d["domain_id"] == domain_id for d in active_domains)

def is_source_active(domain_id: str, source_id: str) -> bool:
    """
    Checks if a source is active.
    """
    if source_id == "_default":
        return True
    active_sources = get_active_sources_hybrid(domain_id)
    return source_id in active_sources

def load_source_rules(domain_id: str, source_id: str, configs_dir: str = "configs") -> dict:
    """
    Loads rules.json for a specific merchant source with fallback to _default.
    """
    rules_path = os.path.join(configs_dir, "domains", domain_id, "sources", source_id, "rules.json")
    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading source rules for '{source_id}' in domain '{domain_id}': {e}")
            
    # Fallback to _default rules
    default_rules_path = os.path.join(configs_dir, "domains", domain_id, "sources", "_default", "rules.json")
    if os.path.exists(default_rules_path):
        try:
            with open(default_rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading default source rules for domain '{domain_id}': {e}")
            
    return {}

def load_source_ai_config(domain_id: str, source_id: str, settings: dict = None) -> tuple[str, str]:
    """
    Resolves the AI provider and model name for a specific source.
    Falls back to settings.json defaults if not specified in source rules.json.
    Returns:
        (provider_name, model_name)
    """
    if settings is None:
        settings = load_system_settings()
        
    provider = None
    model = None
    
    # 1. Try to load rules.json for this source
    rules = load_source_rules(domain_id, source_id)
    if rules:
        provider = rules.get("ai_provider")
        model = rules.get("ai_model")
            
    # 2. Fall back to settings.json
    ai_provider_cfg = settings.get("ai_provider", {})
    if not provider:
        provider = ai_provider_cfg.get("active_provider", "gemini")
    if not model:
        provider_cfg = ai_provider_cfg.get(provider, {})
        model = provider_cfg.get("model_name", "gemini-3.5-flash")
    return provider, model

def get_ai_provider_config(settings: dict = None) -> dict:
    """
    Returns AI provider configuration dictionary including max_images_per_request,
    max_retries, active_provider, and provider-specific settings.
    """
    if settings is None:
        settings = load_system_settings()
    ai_cfg = settings.get("ai_provider", {})
    max_images = ai_cfg.get("max_images_per_request", settings.get("max_images_per_request", 50))
    active_provider = ai_cfg.get("active_provider", "gemini")
    provider_details = ai_cfg.get(active_provider, {})
    max_concurrent = provider_details.get("max_concurrent_requests", provider_details.get("concurrency", 5))

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
    Defaults to JPG, quality 85, max_dimension 1800, dpi 150.
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


