"""Pure Central Configuration Loader.

Zero circular database dependencies. Reads JSON and validates via Pydantic schemas.
"""

import os
import json
from functools import lru_cache
from .logger import logger
from .constants import (
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


def get_validation_thresholds(settings_path: str = DefaultPath.SETTINGS, doc_type: str = None) -> dict:
    """Returns validation thresholds dictionary with fallback to DocTypeRegistry or default standards."""
    settings = load_system_settings(settings_path)
    if "validation_thresholds" in settings and isinstance(settings["validation_thresholds"], dict):
        return settings["validation_thresholds"]

    # Fallback to DocTypeRegistry baseline
    try:
        from src.domain.doc_types import DocTypeRegistry
        target_dt = doc_type or get_default_doc_type()
        strategy = DocTypeRegistry.get(target_dt)
        return {
            "confidence_high": getattr(strategy, "confidence_high", 0.85),
            "confidence_review": getattr(strategy, "confidence_review", 0.70),
            "confidence_low": getattr(strategy, "confidence_low", 0.60),
            "financial_tolerance": getattr(strategy, "financial_tolerance", 0.05),
        }
    except Exception:
        return {
            "confidence_high": 0.85,
            "confidence_review": 0.70,
            "confidence_low": 0.60,
            "financial_tolerance": 0.05,
        }



def resolve_doc_type(doc_type: str = None) -> str:
    """Resolves target doc_type with fallback to configured default."""
    if doc_type and str(doc_type).strip():
        return str(doc_type).strip()
    return get_default_doc_type()


def resolve_company_code(company_code: str = None) -> str:
    """Resolves target company code with fallback to configured default."""
    if company_code and str(company_code).strip():
        return str(company_code).strip()
    return get_default_company_code()


def get_default_doc_type() -> str:
    """Returns default active document type ID from DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry
    return DocTypeRegistry.get_default_doc_type()


def get_active_doc_types() -> list[dict]:
    """Returns active document types from DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry
    return DocTypeRegistry.get_active_doc_types()


def is_doc_type_active(doc_type_id: str) -> bool:
    """Checks if a doc_type is registered and active in DocTypeRegistry."""
    from src.domain.doc_types import is_doc_type_active as _is_active
    return _is_active(doc_type_id)


def get_default_company_code() -> str:
    """Returns the default company code from settings.json."""
    settings = load_system_settings()
    return settings.get("default_company_code", DefaultIdentifier.COMPANY_CODE)


def get_doc_type_config_dir(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> str:
    """Locates configuration directory for doc_type_id via DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry
    dt = DocTypeRegistry.get(doc_type_id)
    return str(dt.get_config_dir(company_code=company_code, configs_dir=configs_dir))


def get_doctype_file_path(
    doc_type_id: str,
    file_key: str,
    company_code: str = None,
    configs_dir: str = "configs",
    settings_path: str = DefaultPath.SETTINGS
) -> str:
    """Resolves exact file path for a doc_type based on DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry
    dt = DocTypeRegistry.get(doc_type_id)
    cfg_dir = dt.get_config_dir(company_code=company_code, configs_dir=configs_dir)
    file_map = {
        "classify_prompt": "classify-prompt.txt",
        "classify_schema": "classify-schema.json",
        "extract_prompt": "extract-prompt.txt",
        "extract_schema": "extract-schema.json",
        "extract_rules": "extract-rules.json",
    }
    file_name = file_map.get(file_key, file_key)
    full_path = (cfg_dir / file_name).as_posix()
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"File '{file_name}' (key: '{file_key}') for doc_type '{doc_type_id}' not found at: '{full_path}'")
    return full_path


def load_doc_type_schema(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> dict:
    """Loads extraction JSON schema for a doc_type via DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry
    return DocTypeRegistry.get(doc_type_id).get_extract_schema(company_code=company_code, configs_dir=configs_dir)


def load_doc_type_classify_schema(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> dict:
    """Loads classifier JSON schema for a doc_type via DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry
    return DocTypeRegistry.get(doc_type_id).get_classify_schema(company_code=company_code, configs_dir=configs_dir)


def load_doc_type_prompt(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> str:
    """Loads extraction prompt text for a doc_type via DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry
    return DocTypeRegistry.get(doc_type_id).get_extract_prompt(company_code=company_code, configs_dir=configs_dir)


def load_doc_type_classify_prompt(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> str:
    """Loads classifier prompt text for a doc_type via DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry
    return DocTypeRegistry.get(doc_type_id).get_classify_prompt(company_code=company_code, configs_dir=configs_dir)


def load_doc_type_rules(doc_type_id: str, company_code: str = None, configs_dir: str = "configs") -> dict:
    """Loads extraction business rules JSON for a doc_type via DocTypeRegistry."""
    from src.domain.doc_types import DocTypeRegistry
    return DocTypeRegistry.get(doc_type_id).get_extract_rules(company_code=company_code, configs_dir=configs_dir)


def load_doc_type_ai_config(doc_type_id: str = None, company_id: str = None, settings: dict = None) -> tuple[str, str]:
    """Resolves AI provider and model name from database AIModelConfig."""
    from src.infrastructure.database import get_resolved_ai_config
    cfg = get_resolved_ai_config(company_id=company_id)
    return cfg["provider"], cfg["model_name"]


def get_ai_provider_config(company_id: str = None, settings: dict = None) -> dict:
    """Returns AI provider configuration dictionary resolved from database AIModelConfig."""
    from src.infrastructure.database import get_resolved_ai_config
    cfg = get_resolved_ai_config(company_id=company_id)
    return {
        "active_provider": cfg["provider"],
        "billing_tier": cfg["billing_tier"],
        "max_retries": 3,
        "max_images_per_request": 50,
        "model_name": cfg["model_name"],
        "api_key_env": cfg["api_key_env_var"],
        "max_concurrent_requests": cfg.get("max_concurrent_requests", 8),
    }


def get_image_processing_config(settings: dict = None) -> dict:
    """Returns image processing settings."""
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
    """Returns list of supported file extensions."""
    cfg = get_image_processing_config(settings)
    return [ext.lower() for ext in cfg.get("supported_input_extensions", [])]
