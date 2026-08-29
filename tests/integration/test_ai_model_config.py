"""Integration tests for AIModelConfig, Automatic Audit Trails, TTL Cache, and Strict Fail-Fast Resolution."""

import pytest
from sqlalchemy import select, update
from src.infrastructure.core.constants import DefaultIdentifier, SystemUserId
from src.infrastructure.core.user_context import user_scope
from src.infrastructure.database.engine import get_db_session
from src.infrastructure.database.models import AIModelConfig, Company
from src.infrastructure.database.repositories.ai_config_repo import (
    get_resolved_ai_config,
    get_ai_config_by_id,
    list_ai_configs,
    create_ai_config,
    update_ai_config,
    set_default_ai_config,
)
from src.infrastructure.external.ai.cost_estimator import calculate_api_cost


@pytest.fixture(autouse=True)
def clear_ai_cache():
    """Ensure in-memory TTL cache is clean before and after each test."""
    get_resolved_ai_config.cache_clear()
    yield
    get_resolved_ai_config.cache_clear()


def test_ai_model_config_seeding():
    """Verifies that seed_ai_model_configs properly initializes the 2 master records."""
    with get_db_session() as session:
        configs = session.scalars(select(AIModelConfig).order_by(AIModelConfig.is_default.desc())).all()
        assert len(configs) >= 2

        free_cfg = session.scalars(select(AIModelConfig).filter_by(config_id=DefaultIdentifier.AI_CONFIG_FREE)).first()
        assert free_cfg is not None
        assert free_cfg.model_name == "gemini-3.5-flash-lite"
        assert free_cfg.billing_tier == "free"
        assert free_cfg.is_default == 1
        assert free_cfg.input_price_per_million == 0.0375
        assert free_cfg.output_price_per_million == 0.15
        assert free_cfg.created_by == SystemUserId.SYSTEM_ADMIN

        paid_cfg = session.scalars(select(AIModelConfig).filter_by(config_id=DefaultIdentifier.AI_CONFIG_PAID)).first()
        assert paid_cfg is not None
        assert paid_cfg.model_name == "gemini-3.5-flash"
        assert paid_cfg.billing_tier == "paid"
        assert paid_cfg.is_default == 0
        assert paid_cfg.input_price_per_million == 0.075


def test_automatic_audit_columns_on_update():
    """Verifies that updating an entity automatically stamps updated_at and updated_by via event listener."""
    test_actor = "usr_audit_tester"
    with user_scope(test_actor):
        with get_db_session() as session:
            cfg = session.scalars(select(AIModelConfig).filter_by(config_id=DefaultIdentifier.AI_CONFIG_PAID)).first()
            assert cfg is not None
            cfg.exchange_rate_thb = 35.8

        with get_db_session() as session:
            refreshed = session.scalars(select(AIModelConfig).filter_by(config_id=DefaultIdentifier.AI_CONFIG_PAID)).first()
            assert refreshed.exchange_rate_thb == 35.8
            assert refreshed.updated_at is not None
            assert refreshed.updated_by == test_actor


def test_default_ai_config_resolution():
    """Verifies that get_resolved_ai_config returns the default config when company_id is None."""
    resolved = get_resolved_ai_config(company_id=None)
    assert resolved["config_id"] == DefaultIdentifier.AI_CONFIG_FREE
    assert resolved["model_name"] == "gemini-3.5-flash-lite"
    assert resolved["is_default"] == 1


def test_company_custom_ai_config_resolution():
    """Verifies that a company with explicit ai_config_id resolves to that specific config."""
    with get_db_session() as session:
        comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
        assert comp is not None
        comp.ai_config_id = DefaultIdentifier.AI_CONFIG_PAID
        cid = comp.company_id

    get_resolved_ai_config.cache_clear()
    resolved = get_resolved_ai_config(company_id=cid)
    assert resolved["config_id"] == DefaultIdentifier.AI_CONFIG_PAID
    assert resolved["model_name"] == "gemini-3.5-flash"
    assert resolved["billing_tier"] == "paid"


def test_fail_fast_inactive_config_id():
    """Verifies that resolving a company with inactive ai_config_id raises KeyError immediately."""
    create_ai_config(
        config_id="conf_inactive_test",
        config_name="Inactive Config",
        provider="gemini",
        model_name="gemini-3.5-flash",
        billing_tier="free",
        api_key_env_var="api_key_env_default_free",
        is_active=0
    )
    with get_db_session() as session:
        comp = session.scalars(select(Company).filter_by(company_code=DefaultIdentifier.COMPANY_CODE)).first()
        comp.ai_config_id = "conf_inactive_test"
        cid = comp.company_id

    get_resolved_ai_config.cache_clear()
    with pytest.raises(KeyError) as exc_info:
        get_resolved_ai_config(company_id=cid)

    assert "conf_inactive_test" in str(exc_info.value)


def test_fail_fast_missing_default_config():
    """Verifies that when no default config is active, get_resolved_ai_config raises RuntimeError immediately."""
    with get_db_session() as session:
        session.execute(update(AIModelConfig).values(is_default=0))

    get_resolved_ai_config.cache_clear()
    with pytest.raises(RuntimeError) as exc_info:
        get_resolved_ai_config(company_id=None)

    assert "No active default AIModelConfig" in str(exc_info.value)

    # Restore default for subsequent tests
    set_default_ai_config(DefaultIdentifier.AI_CONFIG_FREE)


def test_in_memory_ttl_cache_invalidation():
    """Verifies that modifying config via repository clears the TTL cache."""
    res1 = get_resolved_ai_config(company_id=None)
    assert res1["config_name"] == "Gemini 3.5 Flash Lite (Free Tier)"

    # Update through repository function which invalidates cache
    update_ai_config(DefaultIdentifier.AI_CONFIG_FREE, config_name="Updated Free Tier Name")

    res2 = get_resolved_ai_config(company_id=None)
    assert res2["config_name"] == "Updated Free Tier Name"


def test_cost_estimator_with_db_config():
    """Verifies that calculate_api_cost computes cost using parameters from AIModelConfig."""
    cost_info = calculate_api_cost(
        provider="gemini",
        model_name="gemini-3.5-flash",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        override_tier="paid"
    )
    assert cost_info["nominal_value_usd"] > 0.0
    assert cost_info["cost_usd"] > 0.0
    assert cost_info["cost_thb"] > 0.0
    assert cost_info["is_free_tier"] == 0
