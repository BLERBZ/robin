#!/usr/bin/env bash
# =============================================================================
# Kait AI Intel - Quickstart Bootstrap
# =============================================================================
# One-liner: curl -sSL <repo>/quickstart.sh | bash
# Or: bash quickstart.sh
#
# What it does:
#   1. Checks Python 3.10+
#   2. Checks/installs Ollama
#   3. Starts Ollama if not running
#   4. Pulls a default model if none exist
#   5. Runs pre-flight checks
#   6. Launches the sidekick
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { echo -e "${CYAN}[INFO]${RESET} $*"; }
ok()    { echo -e "${GREEN}[OK]${RESET}   $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET} $*"; }
fail()  { echo -e "${RED}[FAIL]${RESET} $*"; }

echo -e "${BOLD}"
echo "    _  __     _ _"
echo "   | |/ /    (_) |"
echo "   | ' / __ _ _| |_"
echo "   |  < / _\` | | __|"
echo "   | . \\ (_| | | |_"
echo "   |_|\\_\\__,_|_|\\__|"
echo "         AI Intel - Quickstart"
echo -e "${RESET}"
echo ""

# ---- Step 1: Python check ----
info "Checking Python..."
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.10+ not found."
    echo "  Install Python from https://python.org/downloads/"
    exit 1
fi
ok "Python: $($PYTHON --version)"

# ---- Step 2: Ollama check ----
info "Checking Ollama..."
if ! command -v ollama &>/dev/null; then
    warn "Ollama not found. Installing..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            brew install ollama
        else
            echo "  Install Ollama from: https://ollama.com/download"
            echo "  Then re-run this script."
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux"* ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "  Install Ollama from: https://ollama.com/download"
        exit 1
    fi
fi
ok "Ollama: $(ollama --version 2>/dev/null || echo 'installed')"

# ---- Step 3: Start Ollama if not running ----
info "Checking Ollama server..."
if ! curl -s --max-time 2 http://localhost:11434/api/tags &>/dev/null; then
    warn "Ollama not running. Starting as background daemon..."
    # Use nohup + setsid to fully detach from this terminal session
    # so Ollama survives even if this terminal is closed.
    OLLAMA_LOG="${HOME}/.kait/logs/ollama.log"
    mkdir -p "$(dirname "$OLLAMA_LOG")"
    nohup ollama serve </dev/null >"$OLLAMA_LOG" 2>&1 &
    disown
    OLLAMA_PID=$!
    sleep 3
    if curl -s --max-time 2 http://localhost:11434/api/tags &>/dev/null; then
        ok "Ollama server started (PID: $OLLAMA_PID, detached)"
    else
        fail "Could not start Ollama. Start manually: ollama serve"
        exit 1
    fi
else
    ok "Ollama server: running"
fi

# ---- Step 4: Pull default model if none exist ----
info "Checking models..."
MODEL_COUNT=$(curl -s http://localhost:11434/api/tags 2>/dev/null | $PYTHON -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(len(data.get('models', [])))
except:
    print(0)
" 2>/dev/null || echo "0")

if [ "$MODEL_COUNT" -eq 0 ]; then
    warn "No models found. Pulling llama3.1:8b (this may take a few minutes)..."
    ollama pull llama3.1:8b
    ok "Model downloaded: llama3.1:8b"
else
    ok "Models available: $MODEL_COUNT"
fi

# ---- Step 5: Install sidekick deps if missing ----
info "Checking sidekick dependencies..."
$PYTHON -c "import sounddevice" 2>/dev/null || {
    warn "TTS audio deps not found. Installing..."
    $PYTHON -m pip install sounddevice soundfile --quiet 2>/dev/null && ok "TTS audio deps installed" || warn "Could not install audio deps (TTS will use system fallback)"
}

# ---- Step 6: Find script directory ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIDEKICK="$SCRIPT_DIR/kait_ai_sidekick.py"

if [ ! -f "$SIDEKICK" ]; then
    fail "kait_ai_sidekick.py not found in $SCRIPT_DIR"
    echo "  Make sure you run this script from the project root."
    exit 1
fi

# ---- Step 7: Pre-flight checks ----
info "Running pre-flight checks..."
$PYTHON "$SIDEKICK" --check
if [ $? -ne 0 ]; then
    warn "Some pre-flight checks failed (see above). Continuing anyway..."
fi

# ---- Step 8: Launch ----
echo ""
info "Launching Kait AI Intel..."
echo ""
exec $PYTHON "$SIDEKICK" "$@"
