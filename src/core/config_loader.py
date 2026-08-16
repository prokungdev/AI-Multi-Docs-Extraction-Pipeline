import os
import json
from loguru import logger
from src.core.db import get_domains, get_sources

def load_system_settings(settings_path: str = "configs/settings.json") -> dict:
    """
    Loads central settings.json.
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

def get_active_domains_hybrid() -> list[dict]:
    """
    Returns only domains that are present in document_domains.json AND marked active in DB.
    """
    try:
        db_domains = get_domains()
        # Filter domains that exist in DB and have is_active == 1
        active_db_domains = [d for d in db_domains if d["is_active"] == 1]
        return active_db_domains
    except Exception as e:
        logger.error(f"Error loading active domains in hybrid mode: {e}")
        # Fallback to local file if DB is not initialized yet
        fallback_path = "configs/document_domains.json"
        if os.path.exists(fallback_path):
            try:
                with open(fallback_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [d for d in data if d.get("is_active", True)]
            except Exception:
                pass
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
    rules_path = f"configs/domains/{domain_id}/sources/{source_id}/rules.json"
    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                rules = json.load(f)
                provider = rules.get("ai_provider")
                model = rules.get("ai_model")
        except Exception as e:
            logger.warning(f"Failed to read rules.json at {rules_path}: {e}")
            
    # 2. Fall back to settings.json
    ai_provider_cfg = settings.get("ai_provider", {})
    if not provider:
        provider = ai_provider_cfg.get("active_provider", "gemini")
    if not model:
        # Load default model name for the selected provider from settings.json
        provider_cfg = ai_provider_cfg.get(provider, {})
        model = provider_cfg.get("model_name", "gemini-2.5-flash")
        
    return provider, model
