#!/bin/bash
# Run Kait local services (lightweight, compatible)
# Starts: kaitd (8787), bridge_worker, pulse (8765), watchdog

set -e

KAIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$KAIT_DIR"

KAIT_ARGS=()
if [[ "${KAIT_LITE}" == "1" || "${KAIT_LITE}" == "true" || "${KAIT_LITE}" == "yes" ]]; then
  KAIT_ARGS+=("--lite")
fi
if [[ "${KAIT_NO_PULSE}" == "1" ]]; then
  KAIT_ARGS+=("--no-pulse")
fi
if [[ "${KAIT_NO_WATCHDOG}" == "1" ]]; then
  KAIT_ARGS+=("--no-watchdog")
fi

python3 -m kait.cli up "${KAIT_ARGS[@]}"
python3 -m kait.cli services
