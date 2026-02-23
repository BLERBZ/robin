"""Tests for lib/robin_sync.py — Robin synchronization pipeline."""

import json
import time
from pathlib import Path

import pytest

import lib.robin_sync as rs
from lib.robin_sync import (
    RobinSync,
    SyncStatus,
    SyncAction,
    SyncState,
    SyncItem,
    SyncPlan,
)
from lib.github_ops import GitHubError


class MockGitHubOps:
    """Mock GitHub for Robin sync tests."""

    def __init__(self, robin_exists=True):
        self.robin_exists = robin_exists
        self.repos_created = []
        self.files_created = []

    def get_repo(self, repo_name):
        if repo_name == "robin" and not self.robin_exists:
            raise GitHubError("Not found", status_code=404)
        return {"name": repo_name, "html_url": f"https://github.com/blerbz/{repo_name}"}

    def get_branch_sha(self, repo_name, branch="main"):
        if repo_name == "robin" and not self.robin_exists:
            raise GitHubError("Not found", status_code=404)
        return "abc123456789"

    def compare_commits(self, repo_name, base, head):
        return {"files": [
            {"filename": "lib/new_module.py", "status": "added", "sha": "aaa"},
            {"filename": "lib/existing.py", "status": "modified", "sha": "bbb"},
            {"filename": "README.md", "status": "modified", "sha": "ccc"},
            {"filename": ".env", "status": "modified", "sha": "ddd"},
            {"filename": "lib/mind_bridge.py", "status": "modified", "sha": "eee"},
        ]}

    def get_file_content(self, repo_name, path, ref="main"):
        import base64
        content = base64.b64encode(f"# Content of {path}".encode()).decode()
        return {"content": content, "sha": "fileSHA"}

    def create_or_update_file(self, repo_name, path, content, message, branch="main", sha=None):
        self.files_created.append({"repo": repo_name, "path": path})
        return {"content": {"path": path}}

    def create_repo(self, config):
        self.repos_created.append(config.name)
        return {"html_url": f"https://github.com/blerbz/{config.name}"}

    def set_repo_topics(self, repo_name, topics):
        return {}

    def setup_standard_labels(self, repo_name):
        return []

    def create_issue(self, repo_name, config):
        return {"number": 1}

    def _check_repo_allowed(self, repo_name):
        pass


def _patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "ROBIN_DIR", tmp_path / "robin_sync")
    monkeypatch.setattr(rs, "ROBIN_STATE_FILE", tmp_path / "robin_sync" / "state.json")
    monkeypatch.setattr(rs, "ROBIN_SYNC_LOG", tmp_path / "robin_sync" / "sync.jsonl")
    monkeypatch.setattr(rs, "_robin_sync", None)


@pytest.fixture
def sync(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    return RobinSync(github=MockGitHubOps())


# ─── SyncState ────────────────────────────────────────────────────


def test_sync_state_round_trip():
    state = SyncState(
        last_sync_at=1000.0,
        last_kait_sha="abc",
        last_robin_sha="def",
        status=SyncStatus.COMPLETED,
        files_synced=10,
        total_syncs=3,
    )
    d = state.to_dict()
    restored = SyncState.from_dict(d)
    assert restored.last_sync_at == 1000.0
    assert restored.last_kait_sha == "abc"
    assert restored.status == SyncStatus.COMPLETED
    assert restored.total_syncs == 3


def test_sync_state_defaults():
    state = SyncState()
    assert state.status == SyncStatus.IDLE
    assert state.total_syncs == 0


# ─── SyncItem ─────────────────────────────────────────────────────


def test_sync_item_to_dict():
    item = SyncItem(path="lib/test.py", action=SyncAction.ADD, needs_rebrand=True)
    d = item.to_dict()
    assert d["path"] == "lib/test.py"
    assert d["action"] == "add"
    assert d["needs_rebrand"] is True


# ─── SyncPlan ─────────────────────────────────────────────────────


def test_sync_plan_counts():
    plan = SyncPlan(items=[
        SyncItem(path="a.py", action=SyncAction.ADD),
        SyncItem(path="b.py", action=SyncAction.UPDATE),
        SyncItem(path="c.py", action=SyncAction.SKIP),
        SyncItem(path="d.py", action=SyncAction.ADD, needs_rebrand=True),
    ])
    assert plan.add_count == 2
    assert plan.update_count == 1
    assert plan.skip_count == 1
    assert plan.rebrand_count == 1


def test_sync_plan_summary():
    plan = SyncPlan(items=[], kait_sha="abc123", robin_sha="def456")
    summary = plan.summary()
    assert summary["total_files"] == 0
    assert "abc12" in summary["kait_sha"]


# ─── Exclusion Logic ─────────────────────────────────────────────


def test_should_exclude_env(sync):
    assert sync._should_exclude(".env") is True
    assert sync._should_exclude(".env.local") is True


def test_should_exclude_pycache(sync):
    assert sync._should_exclude("__pycache__/module.py") is True


def test_should_exclude_mind_bridge(sync):
    assert sync._should_exclude("lib/mind_bridge.py") is True
    assert sync._should_exclude("mind_server.py") is True


def test_should_exclude_pyc(sync):
    assert sync._should_exclude("lib/module.pyc") is True


def test_should_not_exclude_normal(sync):
    assert sync._should_exclude("lib/github_ops.py") is False
    assert sync._should_exclude("README.md") is False
    assert sync._should_exclude("tests/test_something.py") is False


# ─── Branding ─────────────────────────────────────────────────────


def test_needs_rebrand(sync):
    assert sync._needs_rebrand("README.md") is True
    assert sync._needs_rebrand("CONTRIBUTING.md") is True
    assert sync._needs_rebrand("pyproject.toml") is True
    assert sync._needs_rebrand("docs/guide.md") is True


def test_needs_rebrand_false(sync):
    assert sync._needs_rebrand("lib/github_ops.py") is False
    assert sync._needs_rebrand("tests/test_something.py") is False


def test_apply_branding(sync):
    content = "Welcome to kait-intel, the Kait Intelligence platform"
    rebranded = sync.apply_branding(content)
    assert "robin" in rebranded
    assert "Robin" in rebranded
    assert "kait-intel" not in rebranded


# ─── Robin README ─────────────────────────────────────────────────


def test_generate_robin_readme(sync):
    readme = sync.generate_robin_readme()
    assert "Robin" in readme
    assert "BLERBZ" in readme
    assert "Open Source Sidekick" in readme
    assert "git clone" in readme
    assert "Contributing" in readme


# ─── Sync Planning ────────────────────────────────────────────────


def test_prepare_sync_first_time(sync):
    plan = sync.prepare_sync()
    # First sync with no previous SHA — should still work
    assert plan.kait_sha
    assert sync._state.status == SyncStatus.REVIEWING


def test_prepare_sync_with_previous(sync):
    sync._state.last_kait_sha = "old_sha"
    sync._save_state()
    plan = sync.prepare_sync()
    # Should have items from compare
    if plan.items:
        # Check that exclusions worked
        paths = [i.path for i in plan.items]
        excluded = [i for i in plan.items if i.action == SyncAction.SKIP]
        assert any(i.path == ".env" for i in excluded) or ".env" not in paths


# ─── Sync Execution ──────────────────────────────────────────────


def test_execute_sync(sync):
    plan = SyncPlan(
        items=[
            SyncItem(path="lib/test.py", action=SyncAction.ADD),
            SyncItem(path="lib/excluded.py", action=SyncAction.SKIP, reason="Excluded"),
        ],
        kait_sha="abc",
        robin_sha="def",
    )
    results = sync.execute_sync(plan)
    assert results["synced"] == 1
    assert results["skipped"] == 1
    assert sync._state.status == SyncStatus.COMPLETED
    assert sync._state.total_syncs == 1


def test_execute_sync_deletes_are_skipped(sync):
    plan = SyncPlan(
        items=[
            SyncItem(path="lib/removed.py", action=SyncAction.DELETE),
        ],
        kait_sha="abc",
        robin_sha="def",
    )
    results = sync.execute_sync(plan)
    # Deletes are skipped for safety
    assert results["skipped"] == 1
    assert results["synced"] == 0


# ─── State Persistence ───────────────────────────────────────────


def test_state_persists(sync, tmp_path, monkeypatch):
    plan = SyncPlan(items=[], kait_sha="abc", robin_sha="def")
    sync.execute_sync(plan)

    _patch_paths(tmp_path, monkeypatch)
    sync2 = RobinSync(github=MockGitHubOps())
    assert sync2._state.total_syncs == 1


# ─── Status ───────────────────────────────────────────────────────


def test_get_status(sync):
    status = sync.get_status()
    assert status["status"] == "idle"
    assert status["total_syncs"] == 0


# ─── Validation ───────────────────────────────────────────────────


def test_validate_sync_robin_exists(sync):
    result = sync.validate_sync()
    assert result["checks"]["repo_exists"] is True


def test_validate_sync_robin_missing(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    sync = RobinSync(github=MockGitHubOps(robin_exists=False))
    result = sync.validate_sync()
    assert result["checks"]["repo_exists"] is False
    assert result["in_sync"] is False


# ─── Initialization ──────────────────────────────────────────────


def test_initialize_robin(sync, tmp_path, monkeypatch):
    # Need to mock os_project_manager too
    import lib.os_project_manager as opm_mod
    monkeypatch.setattr(opm_mod, "OS_PROJECTS_DIR", tmp_path / "os_projects")
    monkeypatch.setattr(opm_mod, "OS_PROJECTS_STATE", tmp_path / "os_projects" / "projects.json")
    monkeypatch.setattr(opm_mod, "_os_project_manager", None)

    result = sync.initialize_robin()
    assert result["status"] == "initialized"
    assert "repo_url" in result
