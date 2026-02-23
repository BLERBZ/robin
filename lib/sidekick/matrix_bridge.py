"""Matrix protocol bridge for the Kait AI sidekick.

Provides bidirectional messaging between Kait and Matrix/Element rooms
using the ``matrix-nio`` library with end-to-end encryption (E2EE).

Design principles:
- The ``matrix-nio`` library is *entirely* optional.  When it is absent
  the module can still be imported -- construction of :class:`MatrixBridge`
  will raise an informative error.
- Credentials are persisted to ``~/.kait/matrix/credentials.json`` so
  that subsequent starts reuse the access token instead of logging in
  again.
- E2EE keys are stored in ``~/.kait/matrix/crypto_store/`` and survive
  restarts.
- Room devices are auto-trusted so that encrypted messages can be sent
  without manual verification.
- Reconnection uses exponential backoff with jitter.
- All public methods are async; the bridge is designed to run inside an
  ``asyncio`` event loop alongside the rest of the sidekick.

Usage::

    cfg = MatrixConfig.from_env()
    bridge = MatrixBridge(cfg, on_message=my_handler)
    await bridge.start()
    await bridge.send_message("!room:matrix.org", "Hello from Kait!")
    await bridge.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("kait.matrix")

# ---------------------------------------------------------------------------
# Optional matrix-nio import
# ---------------------------------------------------------------------------
try:
    from nio import (
        AsyncClient,
        AsyncClientConfig,
        InviteEvent,
        LoginResponse,
        MatrixRoom,
        RoomMessageText,
    )

    _NIO_AVAILABLE = True
except ImportError:
    # Stubs so the module can be imported (and tested) without matrix-nio.
    AsyncClient = None  # type: ignore[assignment,misc]
    AsyncClientConfig = None  # type: ignore[assignment,misc]
    InviteEvent = None  # type: ignore[assignment,misc]
    LoginResponse = None  # type: ignore[assignment,misc]
    MatrixRoom = None  # type: ignore[assignment,misc]
    RoomMessageText = None  # type: ignore[assignment,misc]
    _NIO_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_HOMESERVER = "https://matrix.org"
_DEFAULT_DEVICE_NAME = "kait-intel"
_DEFAULT_SYNC_TIMEOUT = 30_000  # milliseconds
_DEFAULT_STORE_PATH = Path.home() / ".kait" / "matrix"
_CREDENTIALS_FILE = "credentials.json"
_CRYPTO_STORE_DIR = "crypto_store"

# Reconnection parameters
_RECONNECT_BASE_DELAY = 2.0   # seconds
_RECONNECT_MAX_DELAY = 300.0  # 5 minutes
_RECONNECT_JITTER = 0.5       # fraction of delay added as jitter


# ===================================================================
# MatrixConfig
# ===================================================================

@dataclass
class MatrixConfig:
    """Configuration for the Matrix bridge.

    Attributes
    ----------
    homeserver:
        Matrix homeserver URL (e.g. ``https://matrix.org``).
    user_id:
        Full Matrix user ID (e.g. ``@kait-intel:matrix.org``).
    password:
        Password for initial login.  Not stored after the first
        successful login -- an access token is persisted instead.
    room_ids:
        List of room IDs to auto-join on startup.
    device_name:
        Human-readable device name shown in room member lists.
    sync_timeout:
        Long-poll timeout for ``/sync`` in milliseconds.
    store_path:
        Base directory for credential and crypto storage.
    """

    homeserver: str = _DEFAULT_HOMESERVER
    user_id: str = ""
    password: str = ""
    room_ids: List[str] = field(default_factory=list)
    device_name: str = _DEFAULT_DEVICE_NAME
    sync_timeout: int = _DEFAULT_SYNC_TIMEOUT
    store_path: Path = _DEFAULT_STORE_PATH

    @classmethod
    def from_env(cls) -> MatrixConfig:
        """Build a :class:`MatrixConfig` from environment variables.

        Environment Variables
        ---------------------
        KAIT_MATRIX_HOMESERVER
            Homeserver URL (default ``https://matrix.org``).
        KAIT_MATRIX_USER
            Full Matrix user ID.
        KAIT_MATRIX_PASSWORD
            Login password.
        KAIT_MATRIX_ROOM_IDS
            Comma-separated room IDs.
        KAIT_MATRIX_DEVICE_NAME
            Device name (default ``kait-intel``).
        KAIT_MATRIX_SYNC_TIMEOUT
            Sync timeout in ms (default ``30000``).
        KAIT_MATRIX_STORE_PATH
            Base storage directory (default ``~/.kait/matrix/``).

        Returns
        -------
        A populated :class:`MatrixConfig`.
        """
        raw_rooms = os.environ.get("KAIT_MATRIX_ROOM_IDS", "")
        room_ids = [r.strip() for r in raw_rooms.split(",") if r.strip()]

        store_env = os.environ.get("KAIT_MATRIX_STORE_PATH", "")
        store_path = Path(store_env) if store_env else _DEFAULT_STORE_PATH

        sync_timeout = _DEFAULT_SYNC_TIMEOUT
        raw_timeout = os.environ.get("KAIT_MATRIX_SYNC_TIMEOUT", "")
        if raw_timeout.isdigit():
            sync_timeout = int(raw_timeout)

        return cls(
            homeserver=os.environ.get("KAIT_MATRIX_HOMESERVER", _DEFAULT_HOMESERVER),
            user_id=os.environ.get("KAIT_MATRIX_USER", ""),
            password=os.environ.get("KAIT_MATRIX_PASSWORD", ""),
            room_ids=room_ids,
            device_name=os.environ.get("KAIT_MATRIX_DEVICE_NAME", _DEFAULT_DEVICE_NAME),
            sync_timeout=sync_timeout,
            store_path=store_path,
        )


# ===================================================================
# Credential persistence helpers
# ===================================================================

def _credentials_path(store_path: Path) -> Path:
    """Return the path to the credentials JSON file."""
    return store_path / _CREDENTIALS_FILE


def _save_credentials(
    store_path: Path,
    user_id: str,
    device_id: str,
    access_token: str,
) -> None:
    """Persist login credentials to disk."""
    cred_path = _credentials_path(store_path)
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "user_id": user_id,
        "device_id": device_id,
        "access_token": access_token,
    }
    cred_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Credentials saved to %s", cred_path)


def _load_credentials(store_path: Path) -> Optional[Dict[str, str]]:
    """Load previously saved credentials, or return ``None``."""
    cred_path = _credentials_path(store_path)
    if not cred_path.exists():
        return None
    try:
        data = json.loads(cred_path.read_text(encoding="utf-8"))
        if all(k in data for k in ("user_id", "device_id", "access_token")):
            logger.info("Loaded saved credentials from %s", cred_path)
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load credentials: %s", exc)
    return None


# ===================================================================
# MatrixBridge
# ===================================================================

# Callback type: called with (room_id, sender, body)
MessageCallback = Callable[[str, str, str], Awaitable[None]]


class MatrixBridge:
    """Async Matrix client bridge for the Kait sidekick.

    Manages the full lifecycle of a Matrix connection: login or token
    restore, E2EE key management, room joins, message sending and
    receiving, device trust, and graceful shutdown.

    Parameters
    ----------
    config:
        A :class:`MatrixConfig` with connection parameters.
    on_message:
        Async callback invoked when a ``m.room.message`` of type
        ``m.text`` arrives.  Signature: ``(room_id, sender, body)``.
    """

    def __init__(
        self,
        config: MatrixConfig,
        on_message: Optional[MessageCallback] = None,
    ) -> None:
        if not _NIO_AVAILABLE:
            raise RuntimeError(
                "matrix-nio is not installed. "
                "Install it with: pip install matrix-nio[e2e]"
            )
        self._config = config
        self._on_message_cb = on_message
        self._client: Optional[AsyncClient] = None
        self._sync_task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._reconnect_delay = _RECONNECT_BASE_DELAY

    # ---- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Log in (or restore session) and begin syncing.

        Creates the ``AsyncClient`` with E2EE support, attempts to
        restore a previous access token, falls back to password login
        if needed, uploads encryption keys, auto-joins configured rooms,
        and starts the background sync loop.
        """
        if self._running:
            logger.warning("MatrixBridge.start() called but already running")
            return

        store_dir = self._config.store_path / _CRYPTO_STORE_DIR
        store_dir.mkdir(parents=True, exist_ok=True)

        client_config = AsyncClientConfig(
            encryption_enabled=True,
            store_sync_tokens=True,
        )
        self._client = AsyncClient(
            homeserver=self._config.homeserver,
            user=self._config.user_id,
            config=client_config,
            store_path=str(store_dir),
        )

        # Try to restore credentials
        creds = _load_credentials(self._config.store_path)
        if creds is not None:
            self._client.access_token = creds["access_token"]
            self._client.user_id = creds["user_id"]
            self._client.device_id = creds["device_id"]
            logger.info("Restored session for %s (device %s)",
                        creds["user_id"], creds["device_id"])
        else:
            try:
                await self._login()
            except Exception:
                # Close client on login failure to prevent unclosed session
                await self._client.close()
                self._client = None
                raise

        # Register event callbacks
        self._client.add_event_callback(self._on_message, RoomMessageText)
        self._client.add_event_callback(self._on_invite, InviteEvent)

        # Upload E2EE keys if needed
        if self._client.should_upload_keys:
            await self._client.keys_upload()
            logger.info("E2EE keys uploaded")

        # Auto-join configured rooms
        for room_id in self._config.room_ids:
            await self.join_room(room_id)

        # Start background sync
        self._running = True
        self._reconnect_delay = _RECONNECT_BASE_DELAY
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info("MatrixBridge started for %s", self._config.user_id)

    async def stop(self) -> None:
        """Gracefully shut down the bridge.

        Cancels the sync loop, closes the client session, and cleans
        up resources.
        """
        self._running = False
        if self._sync_task is not None:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

        if self._client is not None:
            try:
                await self._client.close()
            except Exception as exc:
                logger.warning("Error closing Matrix client: %s", exc)
            self._client = None

        logger.info("MatrixBridge stopped")

    # ---- login -------------------------------------------------------------

    async def _login(self) -> None:
        """Perform password login and persist credentials."""
        if self._client is None:
            raise RuntimeError("Client not initialised")

        if not self._config.password:
            raise RuntimeError(
                "No saved credentials and KAIT_MATRIX_PASSWORD not set"
            )

        logger.info("Logging in as %s ...", self._config.user_id)
        response = await self._client.login(
            password=self._config.password,
            device_name=self._config.device_name,
        )

        if isinstance(response, LoginResponse):
            logger.info("Login successful (device %s)", response.device_id)
            _save_credentials(
                self._config.store_path,
                user_id=response.user_id,
                device_id=response.device_id,
                access_token=response.access_token,
            )
        else:
            error_msg = getattr(response, "message", "")
            status = getattr(response, "status_code", "")
            detail = error_msg or str(response)
            logger.error(
                "Login failed for %s at %s: %s (status=%s)",
                self._config.user_id, self._config.homeserver, detail, status,
            )
            raise RuntimeError(
                f"Matrix login failed: {detail} -- "
                f"Check that user '{self._config.user_id}' exists on "
                f"'{self._config.homeserver}' and password is correct."
            )

    # ---- sync loop ---------------------------------------------------------

    async def _sync_loop(self) -> None:
        """Background loop that calls ``/sync`` with long-polling.

        On transient errors the loop backs off exponentially (with
        jitter) up to ``_RECONNECT_MAX_DELAY`` seconds.
        """
        while self._running and self._client is not None:
            try:
                await self._client.sync(timeout=self._config.sync_timeout)
                # Reset backoff on success
                self._reconnect_delay = _RECONNECT_BASE_DELAY
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._running:
                    break
                jitter = random.uniform(0, _RECONNECT_JITTER * self._reconnect_delay)
                delay = self._reconnect_delay + jitter
                logger.warning(
                    "Sync error: %s -- retrying in %.1f s", exc, delay
                )
                await asyncio.sleep(delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, _RECONNECT_MAX_DELAY
                )

    # ---- event callbacks ---------------------------------------------------

    async def _on_message(self, room: Any, event: Any) -> None:
        """Handle incoming ``m.room.message`` events of type ``m.text``.

        Ignores messages sent by the bridge's own user.
        """
        if self._client is None:
            return

        # Ignore our own messages
        if event.sender == self._client.user_id:
            return

        body = event.body
        room_id = room.room_id
        sender = event.sender

        logger.info("Message from %s in %s: %s", sender, room_id, body[:120])

        if self._on_message_cb is not None:
            try:
                await self._on_message_cb(room_id, sender, body)
            except Exception as exc:
                logger.error("Message callback error: %s", exc)

    async def _on_invite(self, room: Any, event: Any) -> None:
        """Auto-join rooms when invited."""
        if self._client is None:
            return
        room_id = room.room_id
        logger.info("Invited to %s by %s -- auto-joining", room_id, event.sender)
        try:
            await self._client.join(room_id)
            logger.info("Joined room %s", room_id)
            await self._auto_trust_room_devices(room_id)
        except Exception as exc:
            logger.error("Failed to join room %s: %s", room_id, exc)

    # ---- device trust ------------------------------------------------------

    async def _auto_trust_room_devices(self, room_id: str) -> None:
        """Trust all devices of all members in *room_id* for E2EE.

        This is a convenience measure so that encrypted messages can be
        sent without requiring manual device verification.
        """
        if self._client is None:
            return

        room = self._client.rooms.get(room_id)
        if room is None:
            logger.debug("Room %s not in local state, skipping device trust", room_id)
            return

        for user_id in room.users:
            try:
                devices = self._client.device_store.active_user_devices(user_id)
                for device in devices:
                    if not self._client.is_device_verified(device):
                        self._client.verify_device(device)
                        logger.debug("Auto-trusted device %s of %s",
                                     device.device_id, user_id)
            except Exception as exc:
                logger.debug("Could not trust devices for %s: %s", user_id, exc)

    # ---- sending -----------------------------------------------------------

    async def send_message(
        self,
        room_id: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> None:
        """Send a ``m.text`` message to *room_id*.

        Parameters
        ----------
        room_id:
            Target room ID (e.g. ``!abc123:matrix.org``).
        body:
            Plain-text message body.
        html_body:
            Optional HTML-formatted body.  When provided the message
            includes both ``body`` and ``formatted_body``.
        """
        await self._send(room_id, body, html_body, msgtype="m.text")

    async def send_notice(
        self,
        room_id: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> None:
        """Send a ``m.notice`` message to *room_id*.

        Notices are typically rendered differently by clients (e.g.
        greyed out) and do not trigger notification sounds.

        Parameters
        ----------
        room_id:
            Target room ID.
        body:
            Plain-text message body.
        html_body:
            Optional HTML-formatted body.
        """
        await self._send(room_id, body, html_body, msgtype="m.notice")

    async def _send(
        self,
        room_id: str,
        body: str,
        html_body: Optional[str],
        msgtype: str,
    ) -> None:
        """Internal helper to send a message with the given type."""
        if self._client is None:
            raise RuntimeError("MatrixBridge is not started")

        content: Dict[str, Any] = {
            "msgtype": msgtype,
            "body": body,
        }
        if html_body is not None:
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = html_body

        # Trust devices before sending to encrypted rooms
        await self._auto_trust_room_devices(room_id)

        try:
            await self._client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content,
            )
            logger.debug("Sent %s to %s (%d chars)", msgtype, room_id, len(body))
        except Exception as exc:
            logger.error("Failed to send message to %s: %s", room_id, exc)
            raise

    # ---- room management ---------------------------------------------------

    async def join_room(self, room_id_or_alias: str) -> None:
        """Join a room by ID or alias.

        Parameters
        ----------
        room_id_or_alias:
            A room ID (``!abc:matrix.org``) or alias (``#room:matrix.org``).
        """
        if self._client is None:
            raise RuntimeError("MatrixBridge is not started")

        try:
            await self._client.join(room_id_or_alias)
            logger.info("Joined room %s", room_id_or_alias)
            await self._auto_trust_room_devices(room_id_or_alias)
        except Exception as exc:
            logger.error("Failed to join room %s: %s", room_id_or_alias, exc)

    # ---- introspection -----------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether the bridge is currently connected and syncing."""
        return self._running

    @property
    def user_id(self) -> str:
        """The Matrix user ID this bridge is logged in as."""
        if self._client is not None and self._client.user_id:
            return self._client.user_id
        return self._config.user_id

    @property
    def joined_rooms(self) -> List[str]:
        """List of room IDs the client has joined."""
        if self._client is not None:
            return list(self._client.rooms.keys())
        return []


# ===================================================================
# Module exports
# ===================================================================

__all__ = [
    "MatrixConfig",
    "MatrixBridge",
    "MessageCallback",
]
