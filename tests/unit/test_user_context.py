"""
Unit Test Suite: UserContext Centralized Actor Provider.

Tests Thread-Safety, Scope Isolation, Nested Scopes, Fail-Fast Zero-Default Rule,
Multi-Thread Isolation, and Streamlit Session Binding across 6 Edge Cases.
"""

import pytest
import concurrent.futures
from src.infrastructure.core.user_context import (
    get_current_user_id,
    set_current_user_id,
    reset_current_user_id,
    user_scope,
    sync_streamlit_user_context,
    _current_user_id,
)
from src.infrastructure.core.constants import SystemUserId


def test_edge_case_e1_empty_context_fails_fast():
    """🛡️ Edge Case E1: Empty context without scope/set MUST raise RuntimeError immediately (Pure Fail-Fast)."""
    # Reset context explicitly to None
    token = _current_user_id.set(None)
    try:
        with pytest.raises(RuntimeError) as exc_info:
            get_current_user_id()
        assert "UserContext is empty: No active user set" in str(exc_info.value)
    finally:
        _current_user_id.reset(token)


def test_edge_case_e2_scope_isolation_and_token_cleanup():
    """🛡️ Edge Case E2: user_scope sets context and guarantees clean teardown even on exception."""
    token = _current_user_id.set("usr_initial")
    try:
        assert get_current_user_id() == "usr_initial"

        # 1. Normal scope execution
        with user_scope("usr_scoped_01") as scoped_uid:
            assert scoped_uid == "usr_scoped_01"
            assert get_current_user_id() == "usr_scoped_01"

        # Restored after normal exit
        assert get_current_user_id() == "usr_initial"

        # 2. Scope teardown on unhandled exception
        with pytest.raises(ZeroDivisionError):
            with user_scope("usr_scoped_error"):
                assert get_current_user_id() == "usr_scoped_error"
                _ = 1 / 0

        # Restored after exception
        assert get_current_user_id() == "usr_initial"
    finally:
        _current_user_id.reset(token)


def test_edge_case_e3_multithreading_isolation():
    """🛡️ Edge Case E3: Each thread maintains completely isolated UserContext without race conditions."""
    results = {}

    def worker_task(thread_name: str, user_id: str):
        with user_scope(user_id):
            import time
            time.sleep(0.02)
            results[thread_name] = get_current_user_id()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f1 = executor.submit(worker_task, "T1", "usr_actor_alpha")
        f2 = executor.submit(worker_task, "T2", "usr_actor_beta")
        f3 = executor.submit(worker_task, "T3", "usr_actor_gamma")
        f4 = executor.submit(worker_task, "T4", "usr_actor_delta")
        concurrent.futures.wait([f1, f2, f3, f4])

    assert results["T1"] == "usr_actor_alpha"
    assert results["T2"] == "usr_actor_beta"
    assert results["T3"] == "usr_actor_gamma"
    assert results["T4"] == "usr_actor_delta"


def test_edge_case_e4_nested_context_scopes():
    """🛡️ Edge Case E4: Nested user_scopes do not corrupt outer scopes."""
    token = _current_user_id.set("usr_level_0")
    try:
        assert get_current_user_id() == "usr_level_0"

        with user_scope("usr_level_1"):
            assert get_current_user_id() == "usr_level_1"

            with user_scope("usr_level_2"):
                assert get_current_user_id() == "usr_level_2"

                with user_scope("usr_level_3"):
                    assert get_current_user_id() == "usr_level_3"

                assert get_current_user_id() == "usr_level_2"

            assert get_current_user_id() == "usr_level_1"

        assert get_current_user_id() == "usr_level_0"
    finally:
        _current_user_id.reset(token)


def test_edge_case_e5_streamlit_session_binding():
    """🛡️ Edge Case E5: Streamlit session bridge syncs user ID or rejects invalid input."""
    # Valid session user
    active_uid = sync_streamlit_user_context("usr_reviewer_01")
    assert active_uid == "usr_reviewer_01"
    assert get_current_user_id() == "usr_reviewer_01"

    # Empty or None session user
    with pytest.raises(ValueError):
        sync_streamlit_user_context("")

    with pytest.raises(ValueError):
        sync_streamlit_user_context(None)


def test_edge_case_e6_invalid_user_id_rejection():
    """🛡️ Edge Case E6: set_current_user_id rejects empty, None, or whitespace-only inputs."""
    with pytest.raises(ValueError):
        set_current_user_id("")

    with pytest.raises(ValueError):
        set_current_user_id("   ")

    with pytest.raises(ValueError):
        set_current_user_id(None)
