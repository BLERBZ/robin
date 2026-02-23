#!/usr/bin/env sh
set -e

CMD="${KAIT_CLAWDBOT_CMD:-${CLAWDBOT_CMD:-clawdbot}}}"
python -m kait.cli sync-context
exec "$CMD" "$@"
