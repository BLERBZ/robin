#!/bin/bash
# Stop Kait local services

set -e

KAIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$KAIT_DIR"

python3 -m kait.cli down
