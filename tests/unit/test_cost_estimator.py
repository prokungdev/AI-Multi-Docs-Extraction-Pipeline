"""
Unit tests for AI Token Pricing, Cost Estimation, and Display Formatting.
Tests multi-provider cost calculation formulas (Gemini, OpenAI) without API network calls.
"""

import pytest
from src.infrastructure.ai.cost_estimator import calculate_api_cost, format_cost_display
from src.infrastructure.ai.ai_service import AIService


@pytest.mark.parametrize("provider, model, input_tokens, output_tokens, override_tier, expected_cost", [
    ("gemini", "gemini-3.5-flash", 1000, 500, "paid", 0.000225),
    ("gemini", "gemini-3.5-flash", 1000, 500, "free", 0.0),
    ("openai", "gpt-4o", 2000, 1000, "paid", 0.015),
])
def test_cost_estimator_parameterized(provider, model, input_tokens, output_tokens, override_tier, expected_cost):
    """Test calculate_api_cost with different providers, models, tiers, and token counts."""
    # Act
    res = calculate_api_cost(
        provider=provider,
        model_name=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        override_tier=override_tier
    )
    # Assert
    assert round(res["cost_usd"], 6) == round(expected_cost, 6)


def test_format_cost_display():
    """Test human-readable cost formatting helper."""
    # Act & Assert
    display_free = format_cost_display(cost_usd=0.0, cost_thb=0.0, is_free_tier=1, nominal_value_usd=0.000225)
    assert "FREE TIER" in display_free

    display_paid = format_cost_display(cost_usd=0.000225, cost_thb=0.0081, is_free_tier=0)
    assert "$0.00022" in display_paid
    assert "THB" in display_paid


def test_ai_service_initialization():
    """Test AIService provider instantiation without live keys."""
    # Arrange & Act
    service = AIService()
    # Assert
    assert hasattr(service, "extract_with_credentials")
    assert hasattr(service, "extract_structured_json")
