"""Pipeline Singleton Process Lock Manager.

Guarantees single execution for pipeline scanning and ingestion across OS processes.
"""

import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from .logger import logger

DEFAULT_LOCK_TTL_SECONDS = 1800  # 30 minutes


class PipelineProcessLock:
    """
    File-based singleton process lock preventing concurrent pipeline executions.
    """

    def __init__(
        self,
        lock_file_path: Optional[str] = None,
        ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.lock_file_path = (
            lock_file_path or os.path.join("storage", ".pipeline_scanner.lock")
        ).replace("\\", "/")
        self.ttl_seconds = ttl_seconds
        self.metadata = metadata or {}
        self._acquired = False

    @property
    def is_acquired(self) -> bool:
        """Returns True if the lock is currently held by this instance."""
        return self._acquired

    def is_process_running(self, pid: int) -> bool:
        """Checks if a process with the given PID is currently active on OS."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
        except Exception:
            return True

    def acquire(self) -> bool:
        """
        Attempts to acquire the singleton process lock.
        """
        os.makedirs(os.path.dirname(self.lock_file_path) or ".", exist_ok=True)

        if os.path.exists(self.lock_file_path):
            try:
                with open(self.lock_file_path, "r", encoding="utf-8") as f:
                    lock_data = json.load(f)

                lock_pid = lock_data.get("pid")
                started_at_str = lock_data.get("started_at")
                is_stale = False

                if started_at_str:
                    try:
                        started_at = datetime.fromisoformat(started_at_str)
                        if started_at.tzinfo is None:
                            started_at = started_at.replace(tzinfo=timezone.utc)
                        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                        if elapsed > self.ttl_seconds:
                            logger.warning(
                                f"PipelineProcessLock: Stale lock detected (elapsed {elapsed:.1f}s > TTL {self.ttl_seconds}s). Reclaiming lock."
                            )
                            is_stale = True
                    except Exception:
                        is_stale = True

                if not is_stale and lock_pid and not self.is_process_running(lock_pid):
                    logger.warning(
                        f"PipelineProcessLock: Lock holder PID {lock_pid} is no longer running. Reclaiming lock."
                    )
                    is_stale = True

                if not is_stale:
                    logger.warning(
                        f"PipelineProcessLock: Pipeline is already active by PID {lock_pid} since {started_at_str}. Skipping concurrent execution."
                    )
                    return False
                else:
                    try:
                        os.remove(self.lock_file_path)
                    except Exception:
                        pass
            except Exception as read_err:
                logger.warning(f"PipelineProcessLock: Could not parse existing lock file: {read_err}. Overwriting.")

        try:
            payload = {
                "pid": os.getpid(),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "metadata": self.metadata,
            }
            with open(self.lock_file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            self._acquired = True
            logger.info(f"PipelineProcessLock: Acquired lock (PID: {os.getpid()}) at '{self.lock_file_path}'.")
            return True
        except Exception as e:
            logger.error(f"PipelineProcessLock: Failed to write lock file: {e}")
            self._acquired = False
            return False

    def release(self) -> bool:
        """
        Releases the lock if owned by the current process.
        """
        if not self._acquired:
            return False

        try:
            if os.path.exists(self.lock_file_path):
                try:
                    with open(self.lock_file_path, "r", encoding="utf-8") as f:
                        lock_data = json.load(f)
                    if lock_data.get("pid") == os.getpid():
                        os.remove(self.lock_file_path)
                except Exception:
                    os.remove(self.lock_file_path)
            self._acquired = False
            logger.info(f"PipelineProcessLock: Released lock (PID: {os.getpid()}).")
            return True
        except Exception as e:
            logger.error(f"PipelineProcessLock: Failed to release lock: {e}")
            return False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
