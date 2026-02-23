#!/usr/bin/env sh
set -e

CMD="${KAIT_CLAUDE_CMD:-${CLAUDE_CMD:-claude}}}"
python -m kait.cli sync-context
exec "$CMD" "$@"
