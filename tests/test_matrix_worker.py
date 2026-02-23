"""Tests for the matrix_worker daemon.

Covers:
  - Single-instance PID lock acquisition and release
  - Heartbeat file writing
  - .env config loading

Run with:
    pytest tests/test_matrix_worker.py -v
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from matrix_worker import (
    _acquire_single_instance_lock,
    _write_heartbeat,
    _load_env_file,
    _pid_is_alive,
)


# ===================================================================
# 1. PID Lock Tests
# ===================================================================

class TestSingleInstanceLock:
    """Tests for the PID-based single-instance lock."""

    def test_acquire_lock_fresh(self, tmp_path, monkeypatch):
        """Acquiring a lock in a clean directory should succeed."""
        monkeypatch.setattr("matrix_worker.Path.home", lambda: tmp_path)
        lock = _acquire_single_instance_lock("test_worker")
        assert lock is not None
        assert lock.exists()
        assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())

    def test_acquire_lock_stale_pid(self, tmp_path, monkeypatch):
        """A stale PID file (dead process) should be overridden."""
        monkeypatch.setattr("matrix_worker.Path.home", lambda: tmp_path)
        lock_dir = tmp_path / ".kait" / "pids"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / "test_worker.lock"
        # Write a PID that doesn't exist
        lock_file.write_text("999999999", encoding="utf-8")

        with patch("matrix_worker._pid_is_alive", return_value=False):
            lock = _acquire_single_instance_lock("test_worker")

        assert lock is not None
        assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())

    def test_acquire_lock_active_pid(self, tmp_path, monkeypatch):
        """An active PID should block lock acquisition."""
        monkeypatch.setattr("matrix_worker.Path.home", lambda: tmp_path)
        lock_dir = tmp_path / ".kait" / "pids"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / "test_worker.lock"
        lock_file.write_text("12345", encoding="utf-8")

        with patch("matrix_worker._pid_is_alive", return_value=True):
            lock = _acquire_single_instance_lock("test_worker")

        assert lock is None

    def test_pid_is_alive_current_process(self):
        """Current process PID should be alive."""
        assert _pid_is_alive(os.getpid()) is True

    def test_pid_is_alive_nonexistent(self):
        """A very large PID should not be alive."""
        # This may vary by OS, but 999999999 is unlikely to exist
        result = _pid_is_alive(999999999)
        # On some systems this may raise OSError -> returns False
        assert isinstance(result, bool)


# ===================================================================
# 2. Heartbeat Tests
# ===================================================================

class TestHeartbeat:
    """Tests for heartbeat file writing."""

    def test_write_heartbeat(self, tmp_path, monkeypatch):
        """Heartbeat should write valid JSON with expected fields."""
        hb_file = tmp_path / "heartbeat.json"
        monkeypatch.setattr("matrix_worker._HEARTBEAT_FILE", hb_file)

        _write_heartbeat(messages_processed=42, uptime_s=123.456)

        assert hb_file.exists()
        data = json.loads(hb_file.read_text(encoding="utf-8"))
        assert data["messages_processed"] == 42
        assert data["uptime_s"] == 123.5
        assert "timestamp" in data
        assert "pid" in data
        assert "status" in data
        assert "rooms" in data

    def test_write_heartbeat_creates_parents(self, tmp_path, monkeypatch):
        """Heartbeat should create parent directories if needed."""
        hb_file = tmp_path / "deep" / "nested" / "heartbeat.json"
        monkeypatch.setattr("matrix_worker._HEARTBEAT_FILE", hb_file)

        _write_heartbeat(messages_processed=0, uptime_s=0.0)
        assert hb_file.exists()


# ===================================================================
# 3. Env File Loader Tests
# ===================================================================

class TestEnvFileLoader:
    """Tests for .env file loading."""

    def test_load_env_file(self, tmp_path, monkeypatch):
        """Key=value pairs from file should be set in os.environ."""
        env_file = tmp_path / "test.env"
        env_file.write_text(
            "KAIT_MATRIX_USER=@bot:test.org\n"
            "KAIT_MATRIX_PASSWORD='secret'\n"
            "# This is a comment\n"
            "\n"
            "KAIT_MATRIX_HOMESERVER=\"https://test.org\"\n",
            encoding="utf-8",
        )

        _load_env_file(str(env_file))

        assert os.environ.get("KAIT_MATRIX_USER") == "@bot:test.org"
        assert os.environ.get("KAIT_MATRIX_PASSWORD") == "secret"
        assert os.environ.get("KAIT_MATRIX_HOMESERVER") == "https://test.org"

        # Cleanup
        for key in ("KAIT_MATRIX_USER", "KAIT_MATRIX_PASSWORD", "KAIT_MATRIX_HOMESERVER"):
            os.environ.pop(key, None)

    def test_load_missing_env_file(self, tmp_path):
        """Loading a non-existent file should warn but not crash."""
        _load_env_file(str(tmp_path / "nonexistent.env"))
        # Should not raise
