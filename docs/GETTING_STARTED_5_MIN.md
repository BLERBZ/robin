# Getting Started (5 Minutes)

If you are new: follow this page first. For the full map, see `docs/DOCS_INDEX.md`.

## 0) Prereqs

- Python 3.10+
- `pip`
- Git
- Windows one-command path: PowerShell
- Mac/Linux one-command path: `curl` + `bash`

## 1) Install

### Option A: Windows One Command (Repo + venv + install + up)

```powershell
irm https://raw.githubusercontent.com/vibeforge1111/kait-intel/main/install.ps1 | iex
```

Then run a ready check (from repo root):

```powershell
.\.venv\Scripts\python -m kait.cli up
.\.venv\Scripts\python -m kait.cli health
```

### Option B: Mac/Linux One Command (Repo + venv + install + up)

```bash
curl -fsSL https://raw.githubusercontent.com/vibeforge1111/kait-intel/main/install.sh | bash
```

Then run a ready check (from repo root):

```bash
./.venv/bin/python -m kait.cli up
./.venv/bin/python -m kait.cli health
```

### Option C: Installer (Recommended for full OpenClaw stack)

- Windows: clone `kait-openclaw-installer` and run `install.ps1`
- Mac/Linux: clone `kait-openclaw-installer` and run `install.sh`

See `README.md` for the exact commands.

### Option D: Manual (Repo)

```bash
cd /path/to/kait-intel
python3 -m venv .venv
# Mac/Linux:
source .venv/bin/activate
python -m pip install -e .[services]
```

```powershell
# Windows (no activate needed):
cd C:\path\to\kait-intel
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[services]"
```

If you see `externally-managed-environment`, use the virtualenv block above and
re-run installation inside it.

## 2) Start Services

### Windows (repo)

```bat
start_kait.bat
```

```powershell
# Equivalent without PATH assumptions:
.\.venv\Scripts\python -m kait.cli up
```

### Mac/Linux (repo)

```bash
python3 -m kait.cli up
# or: kait up
```

## 3) Verify Health

CLI:
```bash
python3 -m kait.cli health
```

HTTP:
- kaitd liveness: `http://127.0.0.1:8787/health` (plain `ok`)
- kaitd status: `http://127.0.0.1:8787/status` (JSON)
- Mind (if enabled): `http://127.0.0.1:8080/health`

## 4) Observability

- Kait Pulse (web dashboard): `http://localhost:8765`
- Obsidian Observatory: `python scripts/generate_observatory.py --force`

See `docs/OBSIDIAN_OBSERVATORY_GUIDE.md` for full observatory setup.

## 5) Connect Your Coding Agent

If you use Claude Code or Cursor:
- Claude Code: `docs/claude_code.md`
- Cursor/VS Code: `docs/cursor.md`

The goal is simple:
- Kait writes learnings to context files.
- Your agent reads them and adapts.

## Troubleshooting (Fast)

- Port already in use: change ports via env (see `lib/ports.py` and `docs/QUICKSTART.md`).
- Health is red: start via `start_kait.bat` / `kait up` (not manual scripts) so watchdog + workers come up correctly.
- Queue shows 0 events: you may simply not have run any tool interactions yet in this session.
