#!/usr/bin/env python3
"""matrix_worker -- Matrix/Element bridge daemon for Kait AI sidekick.

Connects Kait to Matrix rooms via the :class:`MatrixBridge` so that
users can interact with the sidekick through Element or any Matrix
client.  Incoming messages are processed by
:meth:`KaitSidekick.process_message` and the response is sent back
to the originating room.

Design:
- Single-instance via PID lock file (~/.kait/pids/matrix_worker.lock)
- Structured logging via ``lib.diagnostics``
- Async event loop wrapping the :class:`MatrixBridge` sync loop
- Graceful SIGINT/SIGTERM handling
- Periodic heartbeat written to ``~/.kait/matrix_worker_heartbeat.json``

Usage:
  python3 matrix_worker.py
  python3 matrix_worker.py --once          # Process one sync cycle then exit
  python3 matrix_worker.py --config path   # Load env vars from a .env file
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.diagnostics import setup_component_logging, log_exception
from lib.sidekick.matrix_bridge import MatrixBridge, MatrixConfig

logger = logging.getLogger("kait.matrix.worker")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HEARTBEAT_FILE = Path.home() / ".kait" / "matrix_worker_heartbeat.json"
_HEARTBEAT_INTERVAL = 30.0  # seconds


# ---------------------------------------------------------------------------
# Single-instance lock (same pattern as bridge_worker.py)
# ---------------------------------------------------------------------------

def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except Exception:
        return False


def _acquire_single_instance_lock(name: str) -> Optional[Path]:
    lock_dir = Path.home() / ".kait" / "pids"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / f"{name}.lock"
    pid = os.getpid()

    if lock_file.exists():
        try:
            existing_pid = int(lock_file.read_text(encoding="utf-8").strip())
            if existing_pid != pid and _pid_is_alive(existing_pid):
                logger.error(
                    "%s already running with pid %d; exiting duplicate",
                    name, existing_pid,
                )
                return None
        except Exception:
            pass

    lock_file.write_text(str(pid), encoding="utf-8")

    def _cleanup_lock() -> None:
        try:
            if lock_file.exists() and lock_file.read_text(encoding="utf-8").strip() == str(pid):
                lock_file.unlink(missing_ok=True)
        except Exception:
            pass

    atexit.register(_cleanup_lock)
    return lock_file


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def _write_heartbeat(
    room_count: int = 0,
    status: str = "running",
    messages_processed: int = 0,
    uptime_s: float = 0.0,
) -> None:
    """Write a heartbeat JSON file for liveness monitoring.

    Format matches the spec consumed by ``service_control.py``::

        {"timestamp": <unix>, "rooms": <int>, "status": "running"}
    """
    try:
        _HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": time.time(),
            "rooms": room_count,
            "status": status,
            "pid": os.getpid(),
            "messages_processed": messages_processed,
            "uptime_s": round(uptime_s, 1),
        }
        _HEARTBEAT_FILE.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.debug("Heartbeat write failed: %s", exc)


# ---------------------------------------------------------------------------
# .env file loader
# ---------------------------------------------------------------------------

def _load_env_file(path: str) -> None:
    """Load key=value pairs from a file into ``os.environ``."""
    env_path = Path(path)
    if not env_path.exists():
        logger.warning("Config file not found: %s", path)
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            os.environ[key] = value
    logger.info("Loaded environment from %s", path)


# ---------------------------------------------------------------------------
# Main async entry-point
# ---------------------------------------------------------------------------

async def run(once: bool = False) -> None:
    """Start the Matrix bridge and process messages.

    Parameters
    ----------
    once:
        If ``True``, run a single sync cycle and exit.
    """
    # Late import so logging + env are set up before sidekick initialises
    from kait_ai_sidekick import KaitSidekick

    config = MatrixConfig.from_env()
    if not config.user_id:
        logger.error("KAIT_MATRIX_USER not set -- cannot start")
        return

    # Sidekick instance (headless, no avatar GUI, no auto-services)
    sidekick = KaitSidekick(auto_services=False)
    logger.info("KaitSidekick initialised (headless)")

    # Ensure LLM is available
    sidekick._connect_llm()

    messages_processed = 0
    start_time = time.monotonic()

    async def on_message(room_id: str, sender: str, body: str) -> None:
        nonlocal messages_processed
        logger.info("Processing message from %s in %s", sender, room_id)
        try:
            # process_message is synchronous (runs LLM etc.), so offload
            # to a thread to avoid blocking the async event loop.
            meta = json.dumps({"room_id": room_id, "sender": sender})
            result = await asyncio.to_thread(
                sidekick.process_message, body,
                source="matrix", source_meta=meta,
            )
            await bridge.send_notice(room_id, result["response"])
            messages_processed += 1
            logger.info(
                "Reply sent (%.0fms, ~%d tokens)",
                result.get("elapsed_ms", 0),
                result.get("est_tokens", 0),
            )
        except Exception as exc:
            logger.error("Failed to process/reply: %s", exc)
            try:
                await bridge.send_notice(
                    room_id,
                    f"[error] I couldn't process that message: {exc}",
                )
            except Exception:
                pass

    bridge = MatrixBridge(config, on_message=on_message)

    # Shutdown coordination
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    # Start the bridge
    try:
        await bridge.start()
    except Exception as exc:
        logger.error("Failed to start Matrix bridge: %s", exc)
        return

    logger.info("Matrix worker running (pid %d)", os.getpid())

    if once:
        # Single sync cycle: bridge.start() already did one sync via login.
        # Give it a moment to process any pending messages.
        await asyncio.sleep(2)
        _write_heartbeat(
            room_count=len(bridge.joined_rooms),
            messages_processed=messages_processed,
            uptime_s=time.monotonic() - start_time,
        )
        await bridge.stop()
        return

    # Periodic heartbeat task
    async def heartbeat_loop() -> None:
        while not shutdown_event.is_set():
            _write_heartbeat(
                room_count=len(bridge.joined_rooms),
                messages_processed=messages_processed,
                uptime_s=time.monotonic() - start_time,
            )
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=_HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                pass

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    # Wait for shutdown signal
    await shutdown_event.wait()

    logger.info("Shutting down matrix worker...")
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass

    await bridge.stop()
    _write_heartbeat(
        room_count=0,
        status="stopped",
        messages_processed=messages_processed,
        uptime_s=time.monotonic() - start_time,
    )
    logger.info("Matrix worker stopped (processed %d messages)", messages_processed)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Matrix bridge daemon for Kait AI sidekick")
    ap.add_argument("--once", action="store_true", help="Run one sync cycle then exit")
    ap.add_argument("--config", default=None, help="Path to .env config file")
    args = ap.parse_args()

    setup_component_logging("matrix_worker")

    # Load .env: explicit --config first, then project-root .env as fallback
    if args.config:
        _load_env_file(args.config)
    else:
        default_env = Path(__file__).resolve().parent / ".env"
        if default_env.exists():
            _load_env_file(str(default_env))

    lock_file = _acquire_single_instance_lock("matrix_worker")
    if lock_file is None:
        sys.exit(1)

    logger.info("matrix_worker starting (pid %d)", os.getpid())

    try:
        asyncio.run(run(once=args.once))
    except KeyboardInterrupt:
        logger.info("matrix_worker interrupted")
    except Exception as exc:
        log_exception("matrix_worker", "fatal error", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
