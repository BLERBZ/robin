#!/usr/bin/env bash
# Install LiteLLM proxy into the Kait Python environment.
#
# Usage:
#   bash scripts/install_litellm.sh
#
# Installs the litellm[proxy] package which includes the proxy server
# and all provider SDKs.

set -euo pipefail

echo "==> LiteLLM installer for Kait"

# Detect Python
PYTHON="${PYTHON:-python3}"
if ! command -v "${PYTHON}" &>/dev/null; then
    echo "Error: Python not found. Set PYTHON env var to your Python 3.9+ binary."
    exit 1
fi

PY_VERSION=$("${PYTHON}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "    Python: ${PYTHON} (${PY_VERSION})"

# Check if already installed
if "${PYTHON}" -c "import litellm; print(f'LiteLLM {litellm.version}')" 2>/dev/null; then
    echo "    LiteLLM already installed."
    read -p "    Upgrade? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "    Skipping."
        exit 0
    fi
fi

echo "==> Installing litellm[proxy]..."
"${PYTHON}" -m pip install --upgrade 'litellm[proxy]'

# Verify
echo "==> Verifying installation..."
"${PYTHON}" -c "import litellm; print(f'LiteLLM {litellm.version} installed successfully')"

echo ""
echo "==> Done. To start the LiteLLM proxy:"
echo "    ${PYTHON} -m litellm --config config/litellm_config.yaml --port 4000"
echo ""
echo "    Or enable in Kait: set KAIT_LITELLM_ENABLED=true in .env"
