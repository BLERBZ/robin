#!/bin/bash
# Tail logs for a Kait service

set -e
LOG_DIR="$HOME/.kait/logs"
name="$1"
if [ -z "$name" ]; then
  echo "usage: ./scripts/logs.sh <kaitd|bridge_worker|dashboard>"
  exit 1
fi
log="$LOG_DIR/${name}.log"
if [ ! -f "$log" ]; then
  echo "no log at $log"
  exit 1
fi

tail -n 200 -f "$log"
