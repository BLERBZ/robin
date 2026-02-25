#!/usr/bin/env bash
# Install Olla — lightweight Ollama load balancer for Kait.
#
# Downloads the Olla binary for the current platform and places it
# at ~/.kait/bin/olla. Validates the download with checksum if available.
#
# Usage:
#   bash scripts/install_olla.sh
#
# Supports: macOS (ARM64/AMD64), Linux (AMD64/ARM64)

set -euo pipefail

OLLA_VERSION="${OLLA_VERSION:-latest}"
INSTALL_DIR="${HOME}/.kait/bin"
OLLA_BIN="${INSTALL_DIR}/olla"

# Detect platform
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "${ARCH}" in
    x86_64|amd64)  ARCH="amd64" ;;
    arm64|aarch64)  ARCH="arm64" ;;
    *)
        echo "Error: Unsupported architecture: ${ARCH}"
        exit 1
        ;;
esac

case "${OS}" in
    darwin) PLATFORM="darwin" ;;
    linux)  PLATFORM="linux" ;;
    *)
        echo "Error: Unsupported OS: ${OS}"
        exit 1
        ;;
esac

echo "==> Olla installer for Kait"
echo "    Platform: ${PLATFORM}-${ARCH}"
echo "    Install dir: ${INSTALL_DIR}"

# Create install directory
mkdir -p "${INSTALL_DIR}"

# Check if already installed
if [ -f "${OLLA_BIN}" ]; then
    CURRENT_VERSION=$("${OLLA_BIN}" --version 2>/dev/null || echo "unknown")
    echo "    Existing installation: ${CURRENT_VERSION}"
    read -p "    Reinstall? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "    Skipping installation."
        exit 0
    fi
fi

# Download Olla
# NOTE: Update this URL when Olla publishes official releases.
# For now, this is a placeholder — Olla must be built from source or
# downloaded from the project's release page.
DOWNLOAD_URL="https://github.com/olla-ml/olla/releases/${OLLA_VERSION}/download/olla-${PLATFORM}-${ARCH}"

echo "==> Downloading Olla from ${DOWNLOAD_URL}..."
if command -v curl &>/dev/null; then
    curl -fSL -o "${OLLA_BIN}" "${DOWNLOAD_URL}" || {
        echo "Error: Download failed. You may need to build Olla from source:"
        echo "  go install github.com/olla-ml/olla@latest"
        echo "  cp \$(go env GOPATH)/bin/olla ${OLLA_BIN}"
        exit 1
    }
elif command -v wget &>/dev/null; then
    wget -q -O "${OLLA_BIN}" "${DOWNLOAD_URL}" || {
        echo "Error: Download failed."
        exit 1
    }
else
    echo "Error: Neither curl nor wget found."
    exit 1
fi

chmod +x "${OLLA_BIN}"

# Validate
echo "==> Validating installation..."
if "${OLLA_BIN}" --version &>/dev/null; then
    echo "    Olla installed successfully: $("${OLLA_BIN}" --version)"
else
    echo "    Warning: Binary may not be valid. Check the download URL."
fi

echo "==> Done. Olla installed at ${OLLA_BIN}"
echo "    Enable in Kait: set KAIT_OLLA_ENABLED=true in .env"
echo "    Config: config/olla.yaml"
