"""
Kait Robin Sync — Synchronization pipeline from Kait to Robin

Robin is the open-source mirror of Kait, optimized for community use.
This module handles:
- Initial cloning of Kait codebase as Robin base
- Ongoing sync from Kait→Robin
- OS suitability review (strip proprietary elements)
- Documentation enhancement for contributors
- BLERBZ branding enforcement
- Automated diff review before sync

Usage:
    from lib.robin_sync import RobinSync
    sync = RobinSync()
    sync.prepare_sync()
    sync.execute_sync()
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from lib.diagnostics import log_debug
from lib.github_ops import GitHubOps, GitHubError, get_github_ops

# ============= Configuration =============

KAIT_DIR = Path.home() / ".kait"
ROBIN_DIR = KAIT_DIR / "robin_sync"
ROBIN_STATE_FILE = ROBIN_DIR / "state.json"
ROBIN_SYNC_LOG = ROBIN_DIR / "sync.jsonl"

# Environment
ROBIN_REPO = os.environ.get("KAIT_ROBIN_REPO", "robin")
ROBIN_BRANCH = os.environ.get("KAIT_ROBIN_SYNC_BRANCH", "main")
KAIT_REPO = os.environ.get("KAIT_SOURCE_REPO", "kait-intel")
BLERBZ_ORG = os.environ.get("KAIT_GITHUB_OWNER", "") or os.environ.get("KAIT_GITHUB_ORG", "BLERBZ")
BLERBZ_NAME = os.environ.get("KAIT_BLERBZ_NAME", "BLERBZ LLC")

# Files/patterns to exclude from sync (proprietary or internal)
SYNC_EXCLUDE_PATTERNS = {
    ".env",
    ".env.local",
    ".kait/",
    "__pycache__/",
    "*.pyc",
    ".git/",
    ".venv/",
    "venv/",
    "node_modules/",
    # Proprietary Kait internals that Robin doesn't need
    "lib/mind_bridge.py",  # Vibeship Mind integration
    "mind_server.py",      # Mind bridge server
}

# Files that need branding replacement
BRANDING_FILES = {
    "README.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "docs/",
}

# Branding replacements
BRANDING_REPLACEMENTS = {
    "kait-intel": "robin",
    "Kait Intelligence": "Robin",
    "Kait Intel": "Robin",
    "kait_intel": "robin",
    "Kait's": "Robin's",
}


class SyncStatus(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    REVIEWING = "reviewing"
    SYNCING = "syncing"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncAction(str, Enum):
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    SKIP = "skip"
    REBRAND = "rebrand"


@dataclass
class SyncState:
    """Track Robin sync state."""

    last_sync_at: float = 0.0
    last_kait_sha: str = ""
    last_robin_sha: str = ""
    status: SyncStatus = SyncStatus.IDLE
    files_synced: int = 0
    files_skipped: int = 0
    total_syncs: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "last_sync_at": self.last_sync_at,
            "last_kait_sha": self.last_kait_sha,
            "last_robin_sha": self.last_robin_sha,
            "status": self.status.value,
            "files_synced": self.files_synced,
            "files_skipped": self.files_skipped,
            "total_syncs": self.total_syncs,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SyncState":
        return SyncState(
            last_sync_at=d.get("last_sync_at", 0.0),
            last_kait_sha=d.get("last_kait_sha", ""),
            last_robin_sha=d.get("last_robin_sha", ""),
            status=SyncStatus(d.get("status", "idle")),
            files_synced=d.get("files_synced", 0),
            files_skipped=d.get("files_skipped", 0),
            total_syncs=d.get("total_syncs", 0),
        )


@dataclass
class SyncItem:
    """A single file to sync."""

    path: str
    action: SyncAction
    reason: str = ""
    kait_sha: str = ""
    robin_sha: str = ""
    needs_rebrand: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "action": self.action.value,
            "reason": self.reason,
            "needs_rebrand": self.needs_rebrand,
        }


@dataclass
class SyncPlan:
    """Plan for a sync operation."""

    items: List[SyncItem] = field(default_factory=list)
    kait_sha: str = ""
    robin_sha: str = ""
    created_at: float = 0.0

    @property
    def add_count(self) -> int:
        return sum(1 for i in self.items if i.action == SyncAction.ADD)

    @property
    def update_count(self) -> int:
        return sum(1 for i in self.items if i.action == SyncAction.UPDATE)

    @property
    def skip_count(self) -> int:
        return sum(1 for i in self.items if i.action == SyncAction.SKIP)

    @property
    def rebrand_count(self) -> int:
        return sum(1 for i in self.items if i.needs_rebrand)

    def summary(self) -> Dict[str, Any]:
        return {
            "total_files": len(self.items),
            "add": self.add_count,
            "update": self.update_count,
            "skip": self.skip_count,
            "rebrand": self.rebrand_count,
            "kait_sha": self.kait_sha[:8],
            "robin_sha": self.robin_sha[:8] if self.robin_sha else "n/a",
        }


class RobinSync:
    """Synchronization pipeline from Kait to Robin."""

    def __init__(self, github: Optional[GitHubOps] = None):
        self._gh = github or get_github_ops()
        ROBIN_DIR.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()

    # ─── State Management ─────────────────────────────────────────

    def _load_state(self) -> SyncState:
        if not ROBIN_STATE_FILE.exists():
            return SyncState()
        try:
            data = json.loads(ROBIN_STATE_FILE.read_text())
            return SyncState.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return SyncState()

    def _save_state(self):
        ROBIN_STATE_FILE.write_text(json.dumps(self._state.to_dict(), indent=2))

    def get_status(self) -> Dict[str, Any]:
        return self._state.to_dict()

    # ─── Exclusion Logic ──────────────────────────────────────────

    def _should_exclude(self, path: str) -> bool:
        """Check if a file path should be excluded from sync."""
        for pattern in SYNC_EXCLUDE_PATTERNS:
            if pattern.endswith("/"):
                if path.startswith(pattern) or f"/{pattern}" in path:
                    return True
            elif "*" in pattern:
                # Simple glob matching
                ext = pattern.replace("*", "")
                if path.endswith(ext):
                    return True
            elif path == pattern or path.endswith(f"/{pattern}"):
                return True
        return False

    def _needs_rebrand(self, path: str) -> bool:
        """Check if a file needs branding replacement."""
        for branding_path in BRANDING_FILES:
            if branding_path.endswith("/"):
                if path.startswith(branding_path):
                    return True
            elif path == branding_path:
                return True
        return False

    # ─── Branding ─────────────────────────────────────────────────

    def apply_branding(self, content: str) -> str:
        """Apply Robin branding to content (replace Kait references)."""
        result = content
        for old, new in BRANDING_REPLACEMENTS.items():
            result = result.replace(old, new)
        return result

    def generate_robin_readme(self) -> str:
        """Generate Robin-specific README."""
        return f"""# Robin

**BLERBZ's Own Open Source Sidekick**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![BLERBZ OS](https://img.shields.io/badge/BLERBZ-Open%20Source-blue.svg)](https://blerbz.com)

## Overview

Robin is an open-source AI sidekick built by [{BLERBZ_NAME}](https://blerbz.com).
It provides a self-evolving intelligence layer for AI agents — text and audio/voice only,
designed to expand with skills and additional knowledge.

Robin is the community edition of the Kait intelligence platform, optimized for
open-source contributors and developers.

## Features

- **Self-evolving intelligence** — Learns from every interaction
- **Text & audio/voice interface** — No visual UI, pure efficiency
- **Skill-based expansion** — Add new capabilities as skills
- **GitHub integration** — Full OS project lifecycle management
- **Multi-backend TTS** — ElevenLabs, OpenAI, Piper, macOS Say
- **Autonomous operation** — Can manage projects independently

## Quick Start

```bash
# Clone Robin
git clone https://github.com/{BLERBZ_ORG}/robin.git
cd robin

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with all features
pip install -e ".[dev,tts,services]"

# Run Robin
robin status
```

## Architecture

```
Input Layer → Event Queue → Bridge Cycle → Learning → Advisory → Output
                                              ↓
                                    Sidekick (TTS, Agents, Reasoning)
```

## Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md) first.

### Good First Issues

Look for issues labeled `good first issue` to get started.

### Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .
```

## Documentation

- [Architecture Guide](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Configuration](docs/TUNEABLES.md)
- [Adapters Guide](docs/adapters.md)

## Community

- [GitHub Discussions](https://github.com/{BLERBZ_ORG}/robin/discussions)
- [Issue Tracker](https://github.com/{BLERBZ_ORG}/robin/issues)

## License

MIT License — see [LICENSE](LICENSE) for details.

## About

Robin is built and maintained by [{BLERBZ_NAME}](https://blerbz.com).
Based on the [Kait Intelligence Platform](https://github.com/{BLERBZ_ORG}/kait-intel).

Managed by [Kait OS Sidekick](https://github.com/{BLERBZ_ORG}/kait-intel) — BLERBZ's AI agent for open-source.
"""

    # ─── Sync Planning ────────────────────────────────────────────

    def prepare_sync(self) -> SyncPlan:
        """Prepare a sync plan by comparing Kait and Robin repos."""
        self._state.status = SyncStatus.PREPARING
        self._save_state()

        plan = SyncPlan(created_at=time.time())

        # Get latest SHAs
        try:
            plan.kait_sha = self._gh.get_branch_sha(KAIT_REPO, "main")
        except GitHubError as e:
            log_debug("robin_sync", f"Failed to get Kait SHA: {e}")
            plan.kait_sha = ""

        try:
            plan.robin_sha = self._gh.get_branch_sha(ROBIN_REPO, "main")
        except GitHubError:
            plan.robin_sha = ""

        # If this is the first sync and Robin doesn't exist yet, plan full copy
        if not plan.robin_sha:
            log_debug("robin_sync: Robin repo not found, planning initial sync")
            self._state.status = SyncStatus.REVIEWING
            self._save_state()
            return plan

        # Compare what changed in Kait since last sync
        if self._state.last_kait_sha and plan.kait_sha:
            try:
                comparison = self._gh.compare_commits(
                    KAIT_REPO, self._state.last_kait_sha, plan.kait_sha
                )
                files = comparison.get("files", [])

                for f in files:
                    path = f.get("filename", "")
                    status = f.get("status", "")

                    if self._should_exclude(path):
                        plan.items.append(SyncItem(
                            path=path,
                            action=SyncAction.SKIP,
                            reason="Excluded by sync rules",
                        ))
                        continue

                    action = SyncAction.UPDATE
                    if status == "added":
                        action = SyncAction.ADD
                    elif status == "removed":
                        action = SyncAction.DELETE

                    plan.items.append(SyncItem(
                        path=path,
                        action=action,
                        kait_sha=f.get("sha", ""),
                        needs_rebrand=self._needs_rebrand(path),
                    ))

            except GitHubError as e:
                log_debug("robin_sync", f"Compare failed: {e}")

        self._state.status = SyncStatus.REVIEWING
        self._save_state()

        log_debug("robin_sync", f"Plan ready — {plan.summary()}")
        return plan

    # ─── Sync Execution ───────────────────────────────────────────

    def execute_sync(self, plan: SyncPlan) -> Dict[str, Any]:
        """Execute a sync plan."""
        self._state.status = SyncStatus.SYNCING
        self._save_state()

        results: Dict[str, Any] = {
            "synced": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
        }

        for item in plan.items:
            if item.action == SyncAction.SKIP:
                results["skipped"] += 1
                continue

            try:
                if item.action in (SyncAction.ADD, SyncAction.UPDATE):
                    self._sync_file(item)
                    results["synced"] += 1
                elif item.action == SyncAction.DELETE:
                    # For safety, we don't auto-delete from Robin
                    results["skipped"] += 1
            except GitHubError as e:
                results["failed"] += 1
                results["errors"].append(f"{item.path}: {e}")

        # Update state
        self._state.last_sync_at = time.time()
        self._state.last_kait_sha = plan.kait_sha
        self._state.last_robin_sha = plan.robin_sha
        self._state.files_synced += results["synced"]
        self._state.files_skipped += results["skipped"]
        self._state.total_syncs += 1
        self._state.status = SyncStatus.COMPLETED
        self._save_state()

        # Log the sync
        self._log_sync(plan, results)

        return results

    def _sync_file(self, item: SyncItem):
        """Sync a single file from Kait to Robin."""
        import base64

        # Get file content from Kait
        kait_file = self._gh.get_file_content(KAIT_REPO, item.path)
        content = base64.b64decode(kait_file.get("content", "")).decode("utf-8", errors="replace")

        # Apply branding if needed
        if item.needs_rebrand:
            content = self.apply_branding(content)

        # Check if file exists in Robin
        robin_sha = None
        try:
            existing = self._gh.get_file_content(ROBIN_REPO, item.path)
            robin_sha = existing.get("sha")
        except GitHubError:
            pass

        # Create/update in Robin
        action_word = "Sync" if robin_sha else "Add"
        self._gh.create_or_update_file(
            ROBIN_REPO,
            item.path,
            content,
            f"{action_word} {item.path} from Kait — automated sync",
            sha=robin_sha,
        )

    def _log_sync(self, plan: SyncPlan, results: Dict[str, Any]):
        entry = {
            "ts": time.time(),
            "kait_sha": plan.kait_sha[:8],
            "robin_sha": plan.robin_sha[:8] if plan.robin_sha else "",
            "plan_summary": plan.summary(),
            "results": results,
        }
        try:
            with open(ROBIN_SYNC_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    # ─── Initial Setup ────────────────────────────────────────────

    def initialize_robin(self) -> Dict[str, Any]:
        """Initialize Robin as a new repo with Kait base + OS optimizations."""
        from lib.os_project_manager import OSProjectManager, get_os_project_manager

        manager = get_os_project_manager()

        # Create Robin project
        project = manager.create_project(
            slug="robin",
            name="Robin",
            description="BLERBZ's Own Open Source Sidekick — "
            "A self-evolving intelligence layer for AI agents",
            tech_stack=["python"],
            topics=["ai", "open-source", "sidekick", "blerbz", "intelligence", "agents"],
        )

        # Upload Robin-specific README
        try:
            readme = self.generate_robin_readme()
            existing = None
            try:
                existing = self._gh.get_file_content(ROBIN_REPO, "README.md")
            except GitHubError:
                pass

            sha = existing.get("sha") if existing else None
            self._gh.create_or_update_file(
                ROBIN_REPO,
                "README.md",
                readme,
                "Initialize Robin — BLERBZ's Own Open Source Sidekick",
                sha=sha,
            )
        except GitHubError as e:
            log_debug("robin_sync", f"Failed to create README: {e}")

        # Set up labels
        try:
            self._gh.setup_standard_labels(ROBIN_REPO)
        except GitHubError:
            pass

        return {
            "status": "initialized",
            "project": project.to_dict(),
            "repo_url": f"https://github.com/{BLERBZ_ORG}/{ROBIN_REPO}",
        }

    # ─── Sync Validation ──────────────────────────────────────────

    def validate_sync(self) -> Dict[str, Any]:
        """Validate that Robin is in sync with Kait."""
        results: Dict[str, Any] = {
            "in_sync": True,
            "checks": {},
        }

        # Check if Robin repo exists
        try:
            self._gh.get_repo(ROBIN_REPO)
            results["checks"]["repo_exists"] = True
        except GitHubError:
            results["checks"]["repo_exists"] = False
            results["in_sync"] = False
            return results

        # Check key files exist in Robin
        key_files = ["README.md", "CONTRIBUTING.md", "LICENSE", "CODE_OF_CONDUCT.md"]
        for f in key_files:
            try:
                self._gh.get_file_content(ROBIN_REPO, f)
                results["checks"][f] = True
            except GitHubError:
                results["checks"][f] = False
                results["in_sync"] = False

        # Check last sync age
        if self._state.last_sync_at > 0:
            age_hours = (time.time() - self._state.last_sync_at) / 3600
            results["last_sync_hours_ago"] = round(age_hours, 1)
            if age_hours > 168:  # More than a week
                results["in_sync"] = False
                results["checks"]["sync_freshness"] = False
            else:
                results["checks"]["sync_freshness"] = True
        else:
            results["checks"]["sync_freshness"] = False
            results["in_sync"] = False

        return results


# ─── Singleton ────────────────────────────────────────────────────

_robin_sync: Optional[RobinSync] = None


def get_robin_sync(**kwargs) -> RobinSync:
    global _robin_sync
    if _robin_sync is None:
        _robin_sync = RobinSync(**kwargs)
    return _robin_sync
