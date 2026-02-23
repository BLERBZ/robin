"""Environment variable compatibility helper for Kait -> Kait migration.

Checks KAIT_* first, falls back to KAIT_* for backward compatibility.
"""
from __future__ import annotations

import os


def kait_env(kait_name: str, default: str = "") -> str:
    """Get env var, checking KAIT_* first then falling back to KAIT_*.

    Args:
        kait_name: The KAIT_* env var name (e.g. "KAIT_WORKSPACE").
        default: Default value if neither is set.

    Returns:
        The env var value, or default.
    """
    val = os.environ.get(kait_name, "").strip()
    if val:
        return val
    # Fall back to KAIT_* equivalent
    kait_name = "KAIT_" + kait_name.removeprefix("KAIT_")
    val = os.environ.get(kait_name, "").strip()
    if val:
        return val
    return default


def kait_env_flag(kait_name: str, default: bool = False) -> bool:
    """Get boolean env var, checking KAIT_* first then falling back to KAIT_*.

    Args:
        kait_name: The KAIT_* env var name (e.g. "KAIT_NO_WATCHDOG").
        default: Default if neither is set.

    Returns:
        True if the env var is truthy.
    """
    val = kait_env(kait_name, "")
    if not val:
        return default
    return val.lower() in {"1", "true", "yes", "on", "y"}
