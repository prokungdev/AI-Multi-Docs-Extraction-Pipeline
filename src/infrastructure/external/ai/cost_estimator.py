"""AI Cost calculation engine and multi-tier pricing estimator."""

from typing import Dict, Any, Optional
from src.infrastructure.core.logger import logger
from src.infrastructure.core.config import load_system_settings

DEFAULT_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gemini-3.5-flash": {"input_per_million": 0.075, "output_per_million": 0.30},
    "gemini-2.5-flash": {"input_per_million": 0.075, "output_per_million": 0.30},
    "gemini-1.5-flash": {"input_per_million": 0.075, "output_per_million": 0.30},
    "gemini-1.5-pro": {"input_per_million": 1.25, "output_per_million": 5.00},
    "gpt-4o-mini": {"input_per_million": 0.15, "output_per_million": 0.60},
    "gpt-4o": {"input_per_million": 2.50, "output_per_million": 10.00},
}

DEFAULT_EXCHANGE_RATE_THB: float = 36.0


def get_pricing_config() -> Dict[str, Any]:
    """
    Loads AI pricing configuration from settings.json, resolving billing_tier
    from the global ai_provider configuration with fallback to paid tier.
    """
    try:
        settings = load_system_settings()
        pricing_cfg = settings.get("ai_pricing", {})
        models = pricing_cfg.get("models", DEFAULT_MODEL_PRICING)
        exchange_rate = pricing_cfg.get("exchange_rate_thb", DEFAULT_EXCHANGE_RATE_THB)

        ai_cfg = settings.get("ai_provider", {})
        active_prov = ai_cfg.get("active_provider")
        prov_cfg = ai_cfg.get(active_prov, {}) if active_prov else {}
        billing_tier = prov_cfg.get("billing_tier") or ai_cfg.get("billing_tier", "paid")

        return {
            "models": models,
            "exchange_rate_thb": float(exchange_rate),
            "billing_tier": str(billing_tier).strip().lower()
        }
    except Exception as e:
        logger.warning(f"Failed to load pricing config from settings, using defaults: {e}")
        return {
            "models": DEFAULT_MODEL_PRICING,
            "exchange_rate_thb": DEFAULT_EXCHANGE_RATE_THB,
            "billing_tier": "paid"
        }


def calculate_api_cost(
    provider: str,
    model_name: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    override_tier: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculates exact real-time cost for an AI API request.
    """
    cfg = get_pricing_config()
    tier = (override_tier or cfg.get("billing_tier", "paid")).strip().lower()
    is_free = 1 if tier == "free" else 0
    exchange_rate = cfg.get("exchange_rate_thb", DEFAULT_EXCHANGE_RATE_THB)

    # Normalize model name for lookup
    clean_model = (model_name or "").strip().lower()
    models_dict = cfg.get("models", DEFAULT_MODEL_PRICING)

    # Find matching pricing rule
    pricing = models_dict.get(clean_model)
    if not pricing:
        # Fuzzy match prefix
        for k, v in models_dict.items():
            if k in clean_model or clean_model in k:
                pricing = v
                break

    if not pricing:
        pricing = DEFAULT_MODEL_PRICING.get(clean_model)

    if not pricing:
        pricing = {"input_per_million": 0.075, "output_per_million": 0.30}

    input_rate = float(pricing.get("input_per_million", 0.075))
    output_rate = float(pricing.get("output_per_million", 0.30))

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

