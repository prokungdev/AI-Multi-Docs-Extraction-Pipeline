"""Unit tests for Core Healthcheck and Readiness Probe.

Tests database inspector status, API credentials probe, storage write permissions,
and overall health orchestration without live network or production DB access.
"""

import os
from unittest.mock import patch, MagicMock
from src.infrastructure.core.healthcheck import (
    check_database_status,
    check_api_ready,
    check_storage_status,
    run_healthcheck,
)


def test_check_database_status_success():
    """Test database health check when engine inspection succeeds."""
    mock_inspector = MagicMock()
    mock_inspector.get_table_names.return_value = ["companies", "merchants", "documents"]

    with patch("src.infrastructure.database.engine.get_engine") as mock_get_engine, \
         patch("src.infrastructure.core.healthcheck.inspect", return_value=mock_inspector):
        ok, msg = check_database_status()

    assert ok is True
    assert "3 tables verified" in msg


def test_check_database_status_failure():
    """Test database health check gracefully captures engine exceptions."""
    with patch("src.infrastructure.database.engine.get_engine", side_effect=RuntimeError("Connection refused")):
        ok, msg = check_database_status()

    assert ok is False
    assert "Database error" in msg
    assert "Connection refused" in msg


def test_check_api_ready_with_valid_key(monkeypatch):
    """Test API readiness when required environment variable is present."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_valid_key_12345")
    settings = {
        "ai_provider": {
            "active_provider": "gemini",
            "billing_tier": "free",
            "gemini": {
                "model_name": "gemini-2.5-flash",
                "api_key_env_free": "GEMINI_API_KEY",
            }
        }
    }

    ok, msg, remedies = check_api_ready(settings)

    assert ok is True
    assert "Provider 'gemini' ready" in msg
    assert len(remedies) == 0


def test_check_api_ready_missing_key(monkeypatch):
    """Test API readiness fails fast with helpful remedies when API key is missing."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = {
        "ai_provider": {
            "active_provider": "gemini",
            "billing_tier": "free",
            "gemini": {
                "model_name": "gemini-2.5-flash",
                "api_key_env_free": "GEMINI_API_KEY",
            }
        }
    }

    with patch("src.infrastructure.core.healthcheck.load_dotenv"):
        ok, msg, remedies = check_api_ready(settings)

    assert ok is False
    assert "Missing API Key" in msg
    assert len(remedies) > 0
    assert "GEMINI_API_KEY" in remedies[0]



def test_check_storage_status_writable(tmp_path):
    """Test storage permissions check on writable temporary folders."""
    test_storage = str(tmp_path / "storage")
    test_logs = str(tmp_path / "logs")
    settings = {
        "storage_root": test_storage,
        "logging": {"logs_dir": test_logs}
    }

    ok, msg, remedies = check_storage_status(settings)

    assert ok is True
    assert "Writable" in msg
    assert len(remedies) == 0


def test_run_healthcheck_overall_success(tmp_path, monkeypatch):
    """Test complete run_healthcheck pipeline orchestration."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")
    test_storage = str(tmp_path / "storage")
    test_logs = str(tmp_path / "logs")

    mock_settings = {
        "storage_root": test_storage,
        "logging": {"logs_dir": test_logs},
        "ai_provider": {
            "active_provider": "gemini",
            "billing_tier": "free",
            "gemini": {
                "model_name": "gemini-2.5-flash",
                "api_key_env_free": "GEMINI_API_KEY"
            }
        }
    }

    mock_inspector = MagicMock()
    mock_inspector.get_table_names.return_value = ["companies", "merchants"]

    with patch("src.infrastructure.core.healthcheck.load_system_settings", return_value=mock_settings), \
         patch("src.infrastructure.database.engine.get_engine"), \
         patch("src.infrastructure.core.healthcheck.inspect", return_value=mock_inspector):
        report = run_healthcheck()

    assert report["healthy"] is True
    assert report["status"] == "OK"
    assert report["checks"]["database"]["ok"] is True
    assert report["checks"]["api_ready"]["ok"] is True
    assert report["checks"]["storage_ready"]["ok"] is True
