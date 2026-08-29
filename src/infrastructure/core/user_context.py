"""
Universal User & Security Context Provider.

Provides thread-safe and async-safe current user resolution using Python standard contextvars.
Enforces Strict Zero-Default Policy: Fails fast with explicit RuntimeError if uninitialized.
"""

from contextvars import ContextVar, Token
from contextlib import contextmanager
from typing import Optional, Generator

_current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)


def get_current_user_id() -> str:
    """
    Retrieves the active user ID from the current execution context.
    
    Strict Zero-Default Policy:
    Raises RuntimeError immediately if context has not been initialized.
    """
    user_id = _current_user_id.get()
    if not user_id:
        raise RuntimeError(
            "UserContext is empty: No active user set. "
            "Wrap execution with 'with user_scope(...):' or call 'set_current_user_id(...)' at the entry point."
        )
    return user_id


def set_current_user_id(user_id: str) -> Token:
    """
    Sets the active user ID in the current execution context.
    Returns a Token for restoring the previous context state.
    """
    if not user_id or not str(user_id).strip():
        raise ValueError("User ID cannot be empty or None.")
    return _current_user_id.set(str(user_id).strip())


def reset_current_user_id(token: Token) -> None:
    """Resets the context to the state captured by the given Token."""
    if token is not None:
        _current_user_id.reset(token)


@contextmanager
def user_scope(user_id: str) -> Generator[str, None, None]:
    """
    Context manager for scoping operations to a specific user ID.
    Guarantees clean token reset and isolation even on unhandled exceptions.
    """
    token = set_current_user_id(user_id)
    try:
        yield str(user_id).strip()
    finally:
        reset_current_user_id(token)


def sync_streamlit_user_context(session_user_id: Optional[str] = None) -> str:
    """
    Convenience bridge for synchronizing Streamlit session_state user into UserContext.
    Returns the active user ID.
    """
    if not session_user_id or not str(session_user_id).strip():
        raise ValueError("Streamlit session user ID is empty.")
    clean_uid = str(session_user_id).strip()
    set_current_user_id(clean_uid)
    return clean_uid
