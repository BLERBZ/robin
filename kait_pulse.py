#!/usr/bin/env python3
# ruff: noqa: S603
"""
Kait Pulse - Redirector to inline kait/pulse/.

This file is DEPRECATED. The real Kait Pulse is the FastAPI app at
kait/pulse/app.py. If someone runs this file directly, it will either
launch the pulse app or exit with an error.

DO NOT add a fallback HTTP server here. Use kait/pulse/app.py directly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main():
    from lib.service_control import KAIT_PULSE_DIR
    external_app = KAIT_PULSE_DIR / "app.py"

    print("\n" + "=" * 64)
    print("  KAIT PULSE - REDIRECTOR")
    print("=" * 64)

    if external_app.exists():
        print(f"  Launching external pulse: {KAIT_PULSE_DIR}")
        print("=" * 64 + "\n")
        sys.exit(subprocess.call([sys.executable, str(external_app)], cwd=str(KAIT_PULSE_DIR)))
    else:
        print()
        print("  ERROR: Kait Pulse app not found.")
        print(f"  Expected at: {external_app}")
        print()
        print("  Fix: Ensure kait/pulse/app.py exists,")
        print("  or set KAIT_PULSE_DIR env var to its location.")
        print("=" * 64 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
