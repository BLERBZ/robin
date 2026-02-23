"""Centralized port configuration for Kait services."""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except Exception:
        return default


KAITD_PORT = _env_int("KAITD_PORT", 8787)
PULSE_PORT = _env_int("KAIT_PULSE_PORT", 8765)
MIND_PORT = _env_int("KAIT_MIND_PORT", 8080)
MATRIX_WORKER_PORT = _env_int("KAIT_MATRIX_WORKER_PORT", 8769)


def _host(host: str | None) -> str:
    return host or "127.0.0.1"


def build_url(port: int, host: str | None = None) -> str:
    return f"http://{_host(host)}:{port}"


KAITD_URL = build_url(KAITD_PORT)
PULSE_URL = build_url(PULSE_PORT)
MIND_URL = build_url(MIND_PORT)
MATRIX_WORKER_URL = build_url(MATRIX_WORKER_PORT)

KAITD_HEALTH_URL = f"{KAITD_URL}/health"
PULSE_STATUS_URL = f"{PULSE_URL}/api/status"
PULSE_UI_URL = f"{PULSE_URL}/"
PULSE_DOCS_URL = f"{PULSE_URL}/docs"
MIND_HEALTH_URL = f"{MIND_URL}/health"
