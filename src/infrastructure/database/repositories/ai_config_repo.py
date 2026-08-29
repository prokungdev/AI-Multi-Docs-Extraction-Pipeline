"""AI Model & Provider Configuration Repository using Pure SQLAlchemy 2.0 ORM.

Provides dynamic AI credentials, concurrency limits, and token pricing lookup with
In-Memory TTL Caching and Strict Fail-Fast error handling.
"""

from typing import Optional, List, Dict, Any
from sqlalchemy import select, update
from src.infrastructure.core.logger import logger
from src.infrastructure.core.utils import ttl_cache
from src.infrastructure.core.user_context import get_current_user_id
from ..engine import get_db_session
from ..models import AIModelConfig, Company


@ttl_cache(seconds=60.0)
def get_resolved_ai_config(company_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Resolves active AIModelConfig for a given company with In-Memory TTL caching (60s).
    
    Strict Fail-Fast Rules (Zero Silent Fallback):
    1. If company has explicit ai_config_id, fetch it. If not found or inactive -> raise KeyError.
    2. If company has no ai_config_id or company_id is None, fetch default (is_default=1).
       If no active default exists -> raise RuntimeError.
    """
    with get_db_session() as session:
        target_config_id = None

        if company_id and str(company_id).strip():
            cid = str(company_id).strip()
            comp = session.scalars(select(Company).filter_by(company_id=cid)).first()
            if comp and comp.ai_config_id:
                target_config_id = comp.ai_config_id

        # 1. Fetch specific assigned config if designated
        if target_config_id:
            cfg = session.scalars(select(AIModelConfig).filter_by(config_id=target_config_id)).first()
            if not cfg or not cfg.is_active:
                raise KeyError(
                    f"AIModelConfig '{target_config_id}' assigned to company '{company_id}' "
                    f"was not found or is inactive in database (Fail-Fast)."
                )
            return cfg.to_dict()

        # 2. Fetch global active default config
        default_cfg = session.scalars(
            select(AIModelConfig).where(AIModelConfig.is_default == 1, AIModelConfig.is_active == 1)
        ).first()

        if not default_cfg:
            raise RuntimeError(
                "No active default AIModelConfig (is_default=1, is_active=1) found in database (Fail-Fast)."
            )

        return default_cfg.to_dict()


def get_ai_config_by_id(config_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves an AIModelConfig record by its primary key ID."""
    if not config_id:
        return None
    with get_db_session() as session:
        cfg = session.scalars(select(AIModelConfig).filter_by(config_id=config_id)).first()
        return cfg.to_dict() if cfg else None


def list_ai_configs(active_only: bool = False) -> List[Dict[str, Any]]:
    """Lists all AIModelConfig records in database."""
    with get_db_session() as session:
        stmt = select(AIModelConfig)
        if active_only:
            stmt = stmt.where(AIModelConfig.is_active == 1)
        stmt = stmt.order_by(AIModelConfig.is_default.desc(), AIModelConfig.config_name.asc())
        configs = session.scalars(stmt).all()
        return [c.to_dict() for c in configs]


def create_ai_config(
    config_id: str,
    config_name: str,
    provider: str,
    model_name: str,
    billing_tier: str,
    api_key_env_var: str,
    input_price_per_million: float = 0.0,
    output_price_per_million: float = 0.0,
    exchange_rate_thb: float = 36.0,
    max_concurrent_requests: int = 8,
    is_default: int = 0,
    is_active: int = 1,
    created_by: Optional[str] = None
) -> bool:
    """Creates a new AIModelConfig record in database and clears the TTL cache."""
    actor = created_by or get_current_user_id()
    try:
        with get_db_session() as session:
            existing = session.scalars(select(AIModelConfig).filter_by(config_id=config_id)).first()
            if existing:
                logger.warning(f"AIModelConfig with ID '{config_id}' already exists.")
                return False

            if is_default == 1:
                session.execute(update(AIModelConfig).values(is_default=0))

            new_cfg = AIModelConfig(
                config_id=config_id,
                config_name=config_name,
                provider=provider,
                model_name=model_name,
                billing_tier=billing_tier,
                api_key_env_var=api_key_env_var,
                input_price_per_million=input_price_per_million,
                output_price_per_million=output_price_per_million,
                exchange_rate_thb=exchange_rate_thb,
                max_concurrent_requests=max_concurrent_requests,
                is_default=is_default,
                is_active=is_active,
                created_by=actor
            )
            session.add(new_cfg)

        get_resolved_ai_config.cache_clear()
        logger.info(f"Created AIModelConfig '{config_id}' ({model_name}) successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to create AIModelConfig '{config_id}': {e}")
        return False


def update_ai_config(config_id: str, updated_by: Optional[str] = None, **kwargs) -> bool:
    """Updates an existing AIModelConfig record and clears the TTL cache."""
    actor = updated_by or get_current_user_id()
    try:
        with get_db_session() as session:
            cfg = session.scalars(select(AIModelConfig).filter_by(config_id=config_id)).first()
            if not cfg:
                logger.warning(f"Cannot update AIModelConfig '{config_id}': record not found.")
                return False

            if kwargs.get("is_default") == 1:
                session.execute(update(AIModelConfig).where(AIModelConfig.config_id != config_id).values(is_default=0))

            for key, val in kwargs.items():
                if hasattr(cfg, key) and key not in ("config_id", "created_at", "created_by"):
                    setattr(cfg, key, val)

            cfg.updated_by = actor

        get_resolved_ai_config.cache_clear()
        logger.info(f"Updated AIModelConfig '{config_id}' successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to update AIModelConfig '{config_id}': {e}")
        return False


def set_default_ai_config(config_id: str, updated_by: Optional[str] = None) -> bool:
    """Sets a designated AIModelConfig as the sole default and clears the TTL cache."""
    return update_ai_config(config_id, updated_by=updated_by, is_default=1)
