"""Tests for the Matrix bridge integration.

Unit tests mock the matrix-nio client to test MatrixBridge behaviour
without a live homeserver.  Integration tests (marked
``@pytest.mark.integration``) require actual Matrix credentials.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===================================================================
# 1. MatrixConfig Tests
# ===================================================================

from lib.sidekick.matrix_bridge import (
    MatrixConfig,
    _save_credentials,
    _load_credentials,
)


class TestMatrixConfig:
    """Tests for MatrixConfig dataclass and from_env() factory."""

    def test_default_values(self):
        """MatrixConfig should have sensible defaults."""
        cfg = MatrixConfig()
        assert cfg.homeserver == "https://matrix.org"
        assert cfg.user_id == ""
        assert cfg.password == ""
        assert cfg.room_ids == []
        assert cfg.device_name == "kait-intel"
        assert cfg.sync_timeout == 30_000
        assert cfg.store_path == Path.home() / ".kait" / "matrix"

    def test_from_env_all_set(self, monkeypatch):
        """from_env() should read all environment variables."""
        monkeypatch.setenv("KAIT_MATRIX_HOMESERVER", "https://my.server.org")
        monkeypatch.setenv("KAIT_MATRIX_USER", "@bot:my.server.org")
        monkeypatch.setenv("KAIT_MATRIX_PASSWORD", "s3cret")
        monkeypatch.setenv("KAIT_MATRIX_ROOM_IDS", "!room1:s.org, !room2:s.org")
        monkeypatch.setenv("KAIT_MATRIX_DEVICE_NAME", "test-device")
        monkeypatch.setenv("KAIT_MATRIX_SYNC_TIMEOUT", "60000")
        monkeypatch.setenv("KAIT_MATRIX_STORE_PATH", "/tmp/kait-test")

        cfg = MatrixConfig.from_env()
        assert cfg.homeserver == "https://my.server.org"
        assert cfg.user_id == "@bot:my.server.org"
        assert cfg.password == "s3cret"
        assert cfg.room_ids == ["!room1:s.org", "!room2:s.org"]
        assert cfg.device_name == "test-device"
        assert cfg.sync_timeout == 60_000
        assert cfg.store_path == Path("/tmp/kait-test")

    def test_from_env_defaults(self, monkeypatch):
        """from_env() should use defaults when env vars are unset."""
        # Clear any existing vars
        for var in (
            "KAIT_MATRIX_HOMESERVER",
            "KAIT_MATRIX_USER",
            "KAIT_MATRIX_PASSWORD",
            "KAIT_MATRIX_ROOM_IDS",
            "KAIT_MATRIX_DEVICE_NAME",
            "KAIT_MATRIX_SYNC_TIMEOUT",
            "KAIT_MATRIX_STORE_PATH",
        ):
            monkeypatch.delenv(var, raising=False)

        cfg = MatrixConfig.from_env()
        assert cfg.homeserver == "https://matrix.org"
        assert cfg.user_id == ""
        assert cfg.room_ids == []
        assert cfg.sync_timeout == 30_000

    def test_config_room_ids_parsing(self, monkeypatch):
        """Comma-separated room IDs are split and whitespace-stripped."""
        monkeypatch.setenv(
            "KAIT_MATRIX_ROOM_IDS",
            " !abc:matrix.org , !def:matrix.org , !ghi:matrix.org ",
        )
        cfg = MatrixConfig.from_env()
        assert cfg.room_ids == [
            "!abc:matrix.org",
            "!def:matrix.org",
            "!ghi:matrix.org",
        ]

    def test_config_empty_room_ids(self, monkeypatch):
        """Empty KAIT_MATRIX_ROOM_IDS should produce empty list."""
        monkeypatch.setenv("KAIT_MATRIX_ROOM_IDS", "")
        cfg = MatrixConfig.from_env()
        assert cfg.room_ids == []

    def test_from_env_invalid_timeout(self, monkeypatch):
        """Non-numeric sync timeout should fall back to default."""
        monkeypatch.setenv("KAIT_MATRIX_SYNC_TIMEOUT", "not_a_number")
        cfg = MatrixConfig.from_env()
        assert cfg.sync_timeout == 30_000


# ===================================================================
# 2. Credential Persistence Tests
# ===================================================================

class TestCredentialPersistence:
    """Tests for credential save/load helpers."""

    def test_save_and_load(self, tmp_path):
        """Saved credentials should be loadable."""
        _save_credentials(tmp_path, "user1", "device1", "token123")
        creds = _load_credentials(tmp_path)
        assert creds is not None
        assert creds["user_id"] == "user1"
        assert creds["device_id"] == "device1"
        assert creds["access_token"] == "token123"

    def test_load_missing_file(self, tmp_path):
        """Loading from a directory with no credentials.json returns None."""
        assert _load_credentials(tmp_path) is None

    def test_load_corrupted_file(self, tmp_path):
        """Loading corrupted credentials returns None."""
        cred_file = tmp_path / "credentials.json"
        cred_file.write_text("not json at all", encoding="utf-8")
        assert _load_credentials(tmp_path) is None

    def test_load_incomplete_credentials(self, tmp_path):
        """Loading credentials missing required keys returns None."""
        cred_file = tmp_path / "credentials.json"
        cred_file.write_text(json.dumps({"user_id": "x"}), encoding="utf-8")
        assert _load_credentials(tmp_path) is None


# ===================================================================
# 3. MatrixBridge Tests (mocked nio)
# ===================================================================

# We need to mock nio so tests run without matrix-nio installed
@pytest.fixture
def mock_nio(monkeypatch):
    """Patch the nio availability flag and mock AsyncClient."""
    import lib.sidekick.matrix_bridge as mb

    monkeypatch.setattr(mb, "_NIO_AVAILABLE", True)

    mock_client_cls = MagicMock()
    mock_client_instance = AsyncMock()
    mock_client_instance.user_id = "@kait:test.org"
    mock_client_instance.device_id = "TESTDEV"
    mock_client_instance.access_token = "tok_123"
    mock_client_instance.should_upload_keys = False
    mock_client_instance.rooms = {}
    mock_client_instance.device_store = MagicMock()
    mock_client_instance.device_store.active_user_devices.return_value = []
    mock_client_instance.is_device_verified.return_value = True
    # add_event_callback is synchronous in nio -- use MagicMock to avoid
    # "coroutine was never awaited" warnings.
    mock_client_instance.add_event_callback = MagicMock()
    mock_client_cls.return_value = mock_client_instance

    monkeypatch.setattr(mb, "AsyncClient", mock_client_cls)
    monkeypatch.setattr(mb, "AsyncClientConfig", MagicMock())
    monkeypatch.setattr(mb, "LoginResponse", type("LoginResponse", (), {}))
    monkeypatch.setattr(mb, "RoomMessageText", MagicMock())
    monkeypatch.setattr(mb, "InviteEvent", MagicMock())

    return mock_client_instance


@pytest.fixture
def bridge_config(tmp_path):
    """A MatrixConfig for testing."""
    return MatrixConfig(
        homeserver="https://test.org",
        user_id="@kait:test.org",
        password="testpass",
        room_ids=["!room1:test.org"],
        store_path=tmp_path,
    )


class TestMatrixBridge:
    """Tests for MatrixBridge with a mocked nio client."""

    @pytest.mark.asyncio
    async def test_start_password_login(self, mock_nio, bridge_config, monkeypatch, tmp_path):
        """start() should perform password login when no saved credentials."""
        import lib.sidekick.matrix_bridge as mb

        # Mock LoginResponse isinstance check
        login_resp = MagicMock()
        login_resp.user_id = "@kait:test.org"
        login_resp.device_id = "TESTDEV"
        login_resp.access_token = "tok_fresh"
        mock_nio.login.return_value = login_resp
        monkeypatch.setattr(mb, "LoginResponse", type(login_resp))

        bridge = mb.MatrixBridge(bridge_config)
        await bridge.start()

        mock_nio.login.assert_awaited_once_with(
            password="testpass",
            device_name="kait-intel",
        )

        # Credentials should be saved
        creds = _load_credentials(tmp_path)
        assert creds is not None
        assert creds["access_token"] == "tok_fresh"

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_start_restores_credentials(self, mock_nio, bridge_config, tmp_path):
        """start() should restore saved credentials and skip login."""
        import lib.sidekick.matrix_bridge as mb

        _save_credentials(tmp_path, "@kait:test.org", "DEV99", "tok_saved")

        bridge = mb.MatrixBridge(bridge_config)
        await bridge.start()

        # login should NOT have been called
        mock_nio.login.assert_not_awaited()
        assert mock_nio.access_token == "tok_saved"

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_send_message_text(self, mock_nio, bridge_config, tmp_path):
        """send_message() should call room_send with m.text."""
        import lib.sidekick.matrix_bridge as mb

        _save_credentials(tmp_path, "@kait:test.org", "DEV1", "tok1")
        bridge = mb.MatrixBridge(bridge_config)
        await bridge.start()

        await bridge.send_message("!room1:test.org", "Hello!")

        mock_nio.room_send.assert_awaited_once()
        call_kwargs = mock_nio.room_send.call_args
        assert call_kwargs.kwargs["room_id"] == "!room1:test.org"
        assert call_kwargs.kwargs["content"]["msgtype"] == "m.text"
        assert call_kwargs.kwargs["content"]["body"] == "Hello!"

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_send_notice(self, mock_nio, bridge_config, tmp_path):
        """send_notice() should use m.notice msgtype."""
        import lib.sidekick.matrix_bridge as mb

        _save_credentials(tmp_path, "@kait:test.org", "DEV1", "tok1")
        bridge = mb.MatrixBridge(bridge_config)
        await bridge.start()

        await bridge.send_notice("!room1:test.org", "System notice")

        call_kwargs = mock_nio.room_send.call_args
        assert call_kwargs.kwargs["content"]["msgtype"] == "m.notice"

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_send_html_message(self, mock_nio, bridge_config, tmp_path):
        """send_message with html_body should include formatted_body."""
        import lib.sidekick.matrix_bridge as mb

        _save_credentials(tmp_path, "@kait:test.org", "DEV1", "tok1")
        bridge = mb.MatrixBridge(bridge_config)
        await bridge.start()

        await bridge.send_message(
            "!room1:test.org", "Hello", html_body="<b>Hello</b>"
        )

        content = mock_nio.room_send.call_args.kwargs["content"]
        assert content["format"] == "org.matrix.custom.html"
        assert content["formatted_body"] == "<b>Hello</b>"

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_on_message_callback(self, mock_nio, bridge_config, tmp_path):
        """Incoming messages should trigger the on_message callback."""
        import lib.sidekick.matrix_bridge as mb

        received = []

        async def handler(room_id, sender, body):
            received.append((room_id, sender, body))

        _save_credentials(tmp_path, "@kait:test.org", "DEV1", "tok1")
        bridge = mb.MatrixBridge(bridge_config, on_message=handler)
        await bridge.start()

        # Simulate an incoming message event
        mock_room = MagicMock()
        mock_room.room_id = "!room1:test.org"
        mock_event = MagicMock()
        mock_event.sender = "@alice:test.org"
        mock_event.body = "Hi Kait!"

        await bridge._on_message(mock_room, mock_event)

        assert len(received) == 1
        assert received[0] == ("!room1:test.org", "@alice:test.org", "Hi Kait!")

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_own_message_ignored(self, mock_nio, bridge_config, tmp_path):
        """Messages from the bridge's own user should be ignored."""
        import lib.sidekick.matrix_bridge as mb

        received = []

        async def handler(room_id, sender, body):
            received.append(body)

        _save_credentials(tmp_path, "@kait:test.org", "DEV1", "tok1")
        bridge = mb.MatrixBridge(bridge_config, on_message=handler)
        await bridge.start()

        mock_room = MagicMock()
        mock_room.room_id = "!room1:test.org"
        mock_event = MagicMock()
        mock_event.sender = "@kait:test.org"  # own user
        mock_event.body = "Echo"

        await bridge._on_message(mock_room, mock_event)
        assert len(received) == 0

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_auto_join_on_invite(self, mock_nio, bridge_config, tmp_path):
        """Invite events should trigger join."""
        import lib.sidekick.matrix_bridge as mb

        _save_credentials(tmp_path, "@kait:test.org", "DEV1", "tok1")
        bridge = mb.MatrixBridge(bridge_config)
        await bridge.start()

        mock_room = MagicMock()
        mock_room.room_id = "!newroom:test.org"
        mock_event = MagicMock()
        mock_event.sender = "@inviter:test.org"

        await bridge._on_invite(mock_room, mock_event)

        mock_nio.join.assert_awaited()

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_graceful_stop(self, mock_nio, bridge_config, tmp_path):
        """stop() should cancel sync and close the client."""
        import lib.sidekick.matrix_bridge as mb

        _save_credentials(tmp_path, "@kait:test.org", "DEV1", "tok1")
        bridge = mb.MatrixBridge(bridge_config)
        await bridge.start()
        assert bridge.is_running

        await bridge.stop()
        assert not bridge.is_running
        mock_nio.close.assert_awaited()

    @pytest.mark.asyncio
    async def test_send_without_start_raises(self, mock_nio, bridge_config):
        """Sending before start() should raise RuntimeError."""
        import lib.sidekick.matrix_bridge as mb

        bridge = mb.MatrixBridge(bridge_config)
        with pytest.raises(RuntimeError, match="not started"):
            await bridge.send_message("!room:test.org", "Hello")

    def test_nio_not_available_raises(self, monkeypatch):
        """Construction should fail when matrix-nio is not installed."""
        import lib.sidekick.matrix_bridge as mb

        monkeypatch.setattr(mb, "_NIO_AVAILABLE", False)
        with pytest.raises(RuntimeError, match="matrix-nio is not installed"):
            mb.MatrixBridge(MatrixConfig())

    @pytest.mark.asyncio
    async def test_joined_rooms_property(self, mock_nio, bridge_config, tmp_path):
        """joined_rooms property should reflect client state."""
        import lib.sidekick.matrix_bridge as mb

        _save_credentials(tmp_path, "@kait:test.org", "DEV1", "tok1")
        bridge = mb.MatrixBridge(bridge_config)
        await bridge.start()

        mock_nio.rooms = {"!a:test.org": MagicMock(), "!b:test.org": MagicMock()}
        rooms = bridge.joined_rooms
        assert set(rooms) == {"!a:test.org", "!b:test.org"}

        await bridge.stop()


# ===================================================================
# 4. Integration Test Stubs
# ===================================================================

@pytest.mark.integration
class TestMatrixIntegration:
    """Integration tests requiring real Matrix credentials.

    These are skipped by default. Run with:
        pytest tests/test_matrix_bridge.py -m integration
    """

    @pytest.mark.asyncio
    async def test_real_connection(self):
        """Connect to an actual Matrix homeserver."""
        pytest.skip("Requires KAIT_MATRIX_USER and KAIT_MATRIX_PASSWORD env vars")

    @pytest.mark.asyncio
    async def test_send_receive_roundtrip(self):
        """Send a message and verify it arrives."""
        pytest.skip("Requires KAIT_MATRIX_USER and KAIT_MATRIX_PASSWORD env vars")
