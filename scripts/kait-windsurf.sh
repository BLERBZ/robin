#!/usr/bin/env sh
set -e

CMD="${KAIT_WINDSURF_CMD:-${WINDSURF_CMD:-windsurf}}}"
python -m kait.cli sync-context
exec "$CMD" "$@"
