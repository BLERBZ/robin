#!/bin/bash
# Print portable paths/snippets for this Kait repo

set -e
KAIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "KAIT_DIR=$KAIT_DIR"
echo ""
echo "Claude Code hook command:"
echo "python3 $KAIT_DIR/hooks/observe.py"
echo ""
echo "Run local services:"
echo "cd $KAIT_DIR && ./scripts/run_local.sh"
