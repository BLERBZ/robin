#!/usr/bin/env sh
set -e

CMD="${KAIT_CURSOR_CMD:-${CURSOR_CMD:-cursor}}}"
python -m kait.cli sync-context
exec "$CMD" "$@"
