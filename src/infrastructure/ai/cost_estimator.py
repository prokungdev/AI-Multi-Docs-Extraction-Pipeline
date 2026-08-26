"""AI Cost calculation engine and multi-tier pricing estimator."""

from typing import Dict, Any, Optional
from src.infrastructure.common.logger import logger

from src.infrastructure.common.config_loader import load_system_settings

# Fallback pricing catalog — override via configs/settings.json > ai_pricing.models
# These are illustrative defaults only; update settings.json for production-accurate pricing.
# Keys are model identifiers used for fuzzy-match lookup, not vendor lock-in.
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

    Args:
        provider: AI provider name (e.g. 'gemini', 'openai')
        model_name: Model identifier (e.g. 'gemini-3.5-flash', 'gpt-4o')
        input_tokens: Number of prompt/input tokens used
        output_tokens: Number of generated/output tokens used
        override_tier: Optional override ('free' or 'paid'). Defaults to settings.json config.

    Returns:
        Dict containing:
            - cost_usd: Actual billable USD cost (0.0 if free tier)
            - nominal_value_usd: Market value of tokens in USD regardless of tier
            - cost_thb: Estimated cost in Thai Baht (THB)
            - is_free_tier: 1 if free tier, 0 if paid tier
            - exchange_rate_thb: Exchange rate used for conversion
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
        # Look up standard catalog before default generic rate
        pricing = DEFAULT_MODEL_PRICING.get(clean_model)

    if not pricing:
        # Default fallback to flash rate if completely unknown
        pricing = {"input_per_million": 0.075, "output_per_million": 0.30}

    in_rate = float(pricing.get("input_per_million", 0.075)) / 1_000_000.0
    out_rate = float(pricing.get("output_per_million", 0.30)) / 1_000_000.0

    in_tokens = max(0, int(input_tokens or 0))
    out_tokens = max(0, int(output_tokens or 0))

    nominal_value_usd = (in_tokens * in_rate) + (out_tokens * out_rate)
    actual_cost_usd = 0.0 if is_free else nominal_value_usd
    actual_cost_thb = actual_cost_usd * exchange_rate
    nominal_cost_thb = nominal_value_usd * exchange_rate

    return {
        "cost_usd": round(actual_cost_usd, 8),
        "nominal_value_usd": round(nominal_value_usd, 8),
        "cost_thb": round(actual_cost_thb, 4),
        "nominal_value_thb": round(nominal_cost_thb, 4),
        "is_free_tier": is_free,
        "exchange_rate_thb": exchange_rate,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "model_name": model_name
    }


def format_cost_display(cost_usd: float, cost_thb: float, is_free_tier: int = 0, nominal_value_usd: float = None) -> str:
    """
    Generates a concise, formatted cost string for UI and logging.
    """
    if is_free_tier:
        nominal_str = f" (${nominal_value_usd:.5f} nominal)" if nominal_value_usd else ""
        return f"FREE TIER ($0.00 / 0.00 THB){nominal_str}"
    return f"${cost_usd:.5f} (~{cost_thb:.3f} THB)"
