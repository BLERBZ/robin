#!/usr/bin/env sh
set -e

CMD="${KAIT_CODEX_CMD:-${CODEX_CMD:-codex}}}"
if [ -z "${KAIT_SYNC_TARGETS:-}}" ]; then
  export KAIT_SYNC_TARGETS="codex"
fi
python -m kait.cli sync-context
exec "$CMD" "$@"
