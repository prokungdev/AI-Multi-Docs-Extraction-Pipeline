"""AI Cost calculation engine and multi-tier pricing estimator.

Resolves pricing rules, exchange rates, and billing tiers dynamically from AIModelConfig.
"""

from typing import Dict, Any, Optional
from sqlalchemy import select
from src.infrastructure.core.logger import logger
from src.infrastructure.database import get_resolved_ai_config, get_db_session, AIModelConfig

KNOWN_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gemini-3.5-flash-lite": {"input_per_million": 0.0375, "output_per_million": 0.15},
    "gemini-3.5-flash": {"input_per_million": 0.075, "output_per_million": 0.30},
    "gemini-2.5-flash": {"input_per_million": 0.075, "output_per_million": 0.30},
    "gemini-1.5-flash": {"input_per_million": 0.075, "output_per_million": 0.30},
    "gemini-1.5-pro": {"input_per_million": 1.25, "output_per_million": 5.00},
    "gpt-4o-mini": {"input_per_million": 0.15, "output_per_million": 0.60},
    "gpt-4o": {"input_per_million": 2.50, "output_per_million": 10.00},
}


def calculate_api_cost(
    provider: str,
    model_name: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    company_id: Optional[str] = None,
    override_tier: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates exact real-time cost for an AI API request using AIModelConfig.
    """
    input_rate = None
    output_rate = None
    exchange_rate = 36.0
    tier = override_tier

    # 1. Attempt to match model directly from database
    try:
        with get_db_session() as session:
            db_cfg = session.scalars(select(AIModelConfig).filter_by(model_name=model_name)).first()
            if db_cfg:
                input_rate = db_cfg.input_price_per_million
                output_rate = db_cfg.output_price_per_million
                exchange_rate = db_cfg.exchange_rate_thb
                if not tier:
                    tier = db_cfg.billing_tier
    except Exception as e:
        logger.debug(f"DB lookup note in calculate_api_cost: {e}")

    # 2. If not matched, try resolving company AI config
    if input_rate is None:
        try:
            cfg = get_resolved_ai_config(company_id=company_id)
            if cfg.get("model_name") == model_name or not model_name:
                input_rate = float(cfg.get("input_price_per_million", 0.0375))
                output_rate = float(cfg.get("output_price_per_million", 0.15))
                exchange_rate = float(cfg.get("exchange_rate_thb", 36.0))
                if not tier:
                    tier = cfg.get("billing_tier", "free")
        except Exception:
            pass

    # 3. If still unmatched, use known models table
    if input_rate is None:
        clean_model = (model_name or "").strip().lower()
        pricing = KNOWN_MODEL_PRICING.get(clean_model, {"input_per_million": 0.0375, "output_per_million": 0.15})
        input_rate = pricing["input_per_million"]
        output_rate = pricing["output_per_million"]

    tier = (tier or "paid").strip().lower()
    is_free = 1 if tier == "free" else 0

    nominal_cost_usd = (input_tokens / 1_000_000.0 * input_rate) + (output_tokens / 1_000_000.0 * output_rate)
    actual_cost_usd = 0.0 if is_free else nominal_cost_usd
    cost_thb = actual_cost_usd * exchange_rate

    return {
        "cost_usd": round(actual_cost_usd, 6),
        "nominal_value_usd": round(nominal_cost_usd, 6),
        "cost_thb": round(cost_thb, 4),
        "is_free_tier": is_free,
        "exchange_rate_thb": exchange_rate,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model_used": model_name,
        "provider": provider
    }


def format_cost_display(cost_dict: Optional[Dict[str, Any]] = None, cost_usd: float = 0.0, cost_thb: float = 0.0, is_free_tier: int = 0, nominal_value_usd: float = 0.0, **kwargs) -> str:
    """Formats cost dictionary or keyword arguments into readable string for CLI/UI logging."""
    if isinstance(cost_dict, dict):
        cost_usd = cost_dict.get("cost_usd", cost_usd)
        cost_thb = cost_dict.get("cost_thb", cost_thb)
        is_free_tier = cost_dict.get("is_free_tier", is_free_tier)
        nominal_value_usd = cost_dict.get("nominal_value_usd", nominal_value_usd)
    tag = " [FREE TIER]" if is_free_tier else ""
    return f"${cost_usd:.5f} (~{cost_thb:.4f} THB){tag}"
