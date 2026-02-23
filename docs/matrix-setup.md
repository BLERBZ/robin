# Kait Matrix Integration Setup Guide

## Overview

The Matrix integration enables Kait AI sidekick to communicate via the
[Matrix](https://matrix.org) protocol -- an open, decentralized messaging
standard. Once configured, you can chat with Kait from any Matrix client
including:

- **Element Desktop** (Windows, macOS, Linux)
- **Element iOS** and **Element Android**
- **Element Web** (browser-based)
- Any other Matrix-compatible client (FluffyChat, Nheko, etc.)

The integration supports **end-to-end encryption (E2EE)**, so messages between
you and Kait stay private even on public homeservers.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Python | 3.10 or later |
| libolm | C library required for E2EE support |
| Kait Intel | Installed and working (`kait_ai_sidekick.py` runs successfully) |

### Installing libolm

The `libolm` C library is required for end-to-end encryption. Install it for
your platform before installing the Python dependencies.

**macOS (Homebrew):**
```bash
brew install libolm
```

**Ubuntu / Debian:**
```bash
sudo apt-get update && sudo apt-get install -y libolm-dev
```

**Fedora:**
```bash
sudo dnf install libolm-devel
```

**Arch Linux:**
```bash
sudo pacman -S libolm
```

**Windows:**

Download prebuilt binaries from
https://gitlab.matrix.org/matrix-org/olm and add them to your system PATH.

---

## Installation

Install the Matrix optional dependencies via pip:

```bash
pip install "kait-intel[matrix]"
```

Or install the dependencies manually:

```bash
pip install "matrix-nio[e2e]>=0.25.0" "aiofiles>=23.0"
```

Verify the installation:

```bash
python -c "import nio; print('matrix-nio', nio.__version__)"
```

---

## Account Setup

Kait needs its own Matrix account to send and receive messages.

### Option A: Register on matrix.org (recommended for getting started)

1. Go to https://app.element.io
2. Click **Create Account**
3. Register with a username like `kait-intel` (this gives you `@kait-intel:matrix.org`)
4. Note the password -- you will need it for configuration

### Option B: Use an existing Matrix homeserver

If you run your own Synapse, Dendrite, or Conduit homeserver:

1. Register a new user via your homeserver admin tools
2. Use the full Matrix ID (e.g., `@kait:yourhomeserver.com`)
3. This is recommended for production use (no rate limits, full control)

---

## Configuration

### Environment Variables

All Matrix configuration is controlled through environment variables prefixed
with `KAIT_MATRIX_`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KAIT_MATRIX_ENABLED` | Yes | `false` | Set to `true` to enable the Matrix bridge |
| `KAIT_MATRIX_HOMESERVER` | Yes | `https://matrix.org` | Matrix homeserver URL |
| `KAIT_MATRIX_USER` | Yes | -- | Full Matrix user ID (e.g., `@kait-intel:matrix.org`) |
| `KAIT_MATRIX_PASSWORD` | Yes | -- | Account password |
| `KAIT_MATRIX_ROOM_IDS` | No | (empty) | Comma-separated room IDs to auto-join. If empty, Kait joins any room it is invited to |
| `KAIT_MATRIX_DEVICE_NAME` | No | `kait-intel` | Device name shown in Matrix client session lists |

### .env File Setup

Create or edit the `.env` file in the kait-intel project root:

```bash
# Matrix Integration
KAIT_MATRIX_ENABLED=true
KAIT_MATRIX_HOMESERVER=https://matrix.org
KAIT_MATRIX_USER=@kait-intel:matrix.org
KAIT_MATRIX_PASSWORD=your-secure-password-here
KAIT_MATRIX_ROOM_IDS=
KAIT_MATRIX_DEVICE_NAME=kait-intel
```

The `.env` file is automatically loaded by the service control system when
starting daemons (see `lib/service_control.py`).

### Config File

An optional JSON config file can be placed at `~/.kait/matrix/config.json` for
additional settings. A template is provided at `config/matrix_config_template.json`:

```json
{
  "homeserver": "https://matrix.org",
  "user_id": "@kait-intel:matrix.org",
  "device_name": "kait-intel",
  "sync_timeout_ms": 30000,
  "auto_join_rooms": true,
  "auto_trust_devices": true,
  "message_type": "m.notice",
  "reconnect_max_attempts": 10,
  "reconnect_base_delay_s": 1,
  "reconnect_max_delay_s": 300
}
```

Environment variables take precedence over config file values.

---

## Quick Start

### Step 1: Install dependencies

```bash
pip install "kait-intel[matrix]"
```

If you are not installing via pip, ensure `libolm` is installed for your
platform (see Prerequisites above) and then:

```bash
pip install "matrix-nio[e2e]>=0.25.0" "aiofiles>=23.0"
```

### Step 2: Create a Matrix account for Kait

Register at https://app.element.io or create an account on your homeserver.

### Step 3: Set environment variables

Add to your `.env` file in the project root:

```bash
KAIT_MATRIX_ENABLED=true
KAIT_MATRIX_HOMESERVER=https://matrix.org
KAIT_MATRIX_USER=@kait-intel:matrix.org
KAIT_MATRIX_PASSWORD=your-password
```

### Step 4: Start services

Using the Kait service manager (starts all services including Matrix):

```bash
python kait_ai_sidekick.py
```

Or run the Matrix worker directly:

```bash
python matrix_worker.py
```

### Step 5: Invite Kait to a room

In Element (or your preferred Matrix client):

1. Start a new direct message with `@kait-intel:matrix.org` (or your chosen username)
2. Send a message -- Kait will respond

---

## Using with Element

### Element Desktop

1. Download from https://element.io/download
2. Sign in with your personal Matrix account
3. Click **+** to start a new conversation
4. Search for your Kait bot's Matrix ID (e.g., `@kait-intel:matrix.org`)
5. Send an invite -- Kait auto-joins when `auto_join_rooms` is enabled
6. Start chatting

### Element iOS / Android

1. Install Element from the App Store or Google Play
2. Sign in with your personal account
3. Tap the compose button to create a new direct message
4. Enter Kait's Matrix ID and send the invite
5. Chat as usual -- responses work the same as desktop

### Element Web

1. Go to https://app.element.io
2. Sign in and create a DM with Kait's Matrix ID
3. Works identically to the desktop version

### Device Verification for E2EE

When E2EE is enabled, Element may show a warning about unverified sessions. To
verify Kait's device:

1. Open the room with Kait
2. Click on Kait's name in the member list
3. Under **Sessions**, click on the `kait-intel` device
4. Choose **Manually verify by text** and confirm

Kait uses `auto_trust_devices: true` by default, meaning it trusts your devices
automatically. You only need to verify Kait's device from your side.

### Message Types

Kait responds using `m.notice` message type by default. This is the standard
convention for bot messages in Matrix -- they appear slightly differently from
regular messages and do not trigger notification sounds in most clients.

---

## Architecture

```
+------------------+      +--------------------+      +-------------------+
|                  |      |                    |      |                   |
|  Element Client  +----->+  Matrix Homeserver +----->+  matrix_worker.py |
|  (Desktop/iOS/   |      |  (matrix.org or    |      |                   |
|   Android/Web)   |<-----+   self-hosted)      |<-----+  KaitSidekick    |
|                  |      |                    |      |  (AI processing)  |
+------------------+      +--------------------+      +-------------------+
```

**Message flow:**

1. You send a message in Element
2. Element delivers it to the Matrix homeserver
3. `matrix_worker.py` syncs with the homeserver and receives the message
4. The message is passed to `KaitSidekick` for AI processing
5. Kait generates a response
6. `matrix_worker.py` sends the response back to the Matrix homeserver
7. Element receives and displays the response

The `matrix_worker.py` daemon maintains a persistent connection to the
homeserver using long-polling sync. It handles reconnection automatically with
exponential backoff.

---

## Service Management

The Matrix worker integrates with Kait's service management system in
`lib/service_control.py`.

### Starting

When `KAIT_MATRIX_ENABLED=true`, the matrix worker is included in the standard
service startup:

```python
# Included automatically in start_services() via _service_cmds()
# Command: python matrix_worker.py
```

You can also start it standalone:

```bash
python matrix_worker.py
```

### Status

Check service status with the `/services` command in the Kait sidekick, or
programmatically:

```python
from lib.service_control import service_status
status = service_status()
print(status.get("matrix_worker"))
# Example: {'running': True, 'heartbeat_age_s': 5.2, 'pid': 12345, ...}
```

The service control system checks both the process PID and a heartbeat file at
`~/.kait/matrix_worker_heartbeat.json` to determine if the worker is alive.

### Logs

Matrix worker logs are written to:

```
~/.kait/logs/matrix_worker.log
```

View recent logs:

```bash
tail -f ~/.kait/logs/matrix_worker.log
```

### Stopping

The matrix worker is stopped along with other services via `stop_services()`.
To stop it individually, send SIGTERM to its PID:

```bash
kill $(cat ~/.kait/pids/matrix_worker.pid)
```

---

## Troubleshooting

### "Login failed" or "Invalid credentials"

- Verify `KAIT_MATRIX_USER` is the full Matrix ID (e.g., `@kait-intel:matrix.org`,
  not just `kait-intel`)
- Confirm the password is correct -- try logging in via Element with the same
  credentials
- Check that the homeserver URL is correct and reachable

### "E2EE errors" or "olm not found"

- Ensure `libolm` is installed for your platform (see Prerequisites)
- Reinstall matrix-nio with E2EE support: `pip install "matrix-nio[e2e]"`
- On macOS, if Homebrew installed libolm but Python cannot find it, try:
  ```bash
  export LIBRARY_PATH="/opt/homebrew/lib:$LIBRARY_PATH"
  pip install --force-reinstall "matrix-nio[e2e]"
  ```

### "Can't decrypt messages" or "Unable to decrypt"

- This usually means device trust has not been established
- Verify Kait's device from your Element client (see Device Verification above)
- If the crypto store is corrupted, remove it and re-login:
  ```bash
  rm -rf ~/.kait/matrix/crypto_store/
  ```
  Note: this requires re-verifying all devices.

### "Connection refused" or "Could not connect to homeserver"

- Verify the homeserver URL: `curl https://matrix.org/_matrix/client/versions`
- Check your network connection and firewall rules
- If using a self-hosted server, ensure it is running and the port is open

### "Rate limited" (HTTP 429)

- matrix.org applies rate limits to free accounts
- The worker automatically retries with backoff
- If persistent, wait a few minutes before restarting
- Consider a self-hosted homeserver for production use

### Matrix worker not appearing in service status

- Confirm `KAIT_MATRIX_ENABLED=true` is set in your `.env` or environment
- Check logs at `~/.kait/logs/matrix_worker.log`
- Verify the heartbeat file exists: `ls ~/.kait/matrix_worker_heartbeat.json`

---

## Security

### Credential Storage

Matrix credentials and session data are stored at:

| Path | Contents |
|------|----------|
| `~/.kait/matrix/credentials.json` | Login token and device ID |
| `~/.kait/matrix/crypto_store/` | E2EE keys and device trust data |
| `.env` (project root) | Password in plain text -- restrict file permissions |

Protect these files:

```bash
chmod 600 .env
chmod 700 ~/.kait/matrix/
chmod 600 ~/.kait/matrix/credentials.json
```

### E2EE Device Trust Model

Kait uses **auto-trust** by default (`auto_trust_devices: true` in config).
This means Kait will encrypt messages to all devices of verified users without
requiring manual per-device verification. This simplifies setup but is less
secure than manual verification.

For higher security environments:

1. Set `auto_trust_devices: false` in `~/.kait/matrix/config.json`
2. Manually verify each device through Element
3. Unverified devices will not receive encrypted messages from Kait

### Room Access Control

- By default, Kait auto-joins any room it is invited to
- To restrict Kait to specific rooms, set `KAIT_MATRIX_ROOM_IDS` to a
  comma-separated list of room IDs (e.g., `!abc123:matrix.org,!def456:matrix.org`)
- Kait will ignore invites from rooms not in the allow-list

### Production Recommendations

- **Self-hosted homeserver**: Run your own Synapse or Dendrite instance. This
  avoids rate limits and keeps all data under your control.
- **Dedicated credentials**: Do not reuse passwords from other accounts.
- **Network isolation**: If Kait only needs to communicate with local users,
  restrict homeserver federation.
- **Regular key rotation**: Periodically clear the crypto store and re-verify
  devices to limit the impact of key compromise.
- **File permissions**: Ensure `.env`, `credentials.json`, and the crypto store
  are readable only by the service account running Kait.
