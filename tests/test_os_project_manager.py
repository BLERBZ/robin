"""Tests for lib/os_project_manager.py — OS Project lifecycle management."""

import json
import time
from pathlib import Path

import pytest

import lib.os_project_manager as opm
from lib.os_project_manager import (
    OSProjectManager,
    ProjectPhase,
    ProjectHealth,
    ProjectState,
)
from lib.github_ops import GitHubOps, GitHubError, RepoVisibility


class MockGitHubOps:
    """Mock GitHub operations for testing."""

    def __init__(self):
        self.repos_created = []
        self.files_created = []
        self.labels_created = []

    def create_repo(self, config):
        self.repos_created.append(config.name)
        return {"html_url": f"https://github.com/blerbz/{config.name}"}

    def set_repo_topics(self, repo_name, topics):
        return {"names": topics}

    def get_file_content(self, repo_name, path, ref="main"):
        raise GitHubError("Not found", status_code=404)

    def create_or_update_file(self, repo_name, path, content, message, branch="main", sha=None):
        self.files_created.append(path)
        return {"content": {"path": path}}

    def setup_standard_labels(self, repo_name):
        self.labels_created.append(repo_name)
        return []

    def get_repo(self, repo_name):
        return {"name": repo_name, "stargazers_count": 5, "forks_count": 1}

    def get_repo_stats(self, repo_name):
        return {"stars": 5, "forks": 1, "open_issues": 2, "name": repo_name}

    def list_issues(self, repo_name, state="open", labels=None, per_page=30):
        return [{"number": 1}, {"number": 2}]

    def list_prs(self, repo_name, state="open", per_page=30):
        return [{"number": 1}]

    def get_branch_sha(self, repo_name, branch="main"):
        return "abc123"

    def create_branch(self, repo_name, branch_name, from_sha):
        return {"ref": f"refs/heads/{branch_name}"}

    def create_issue(self, repo_name, config):
        return {"number": 42, "title": config.title}

    def get_contributor_stats(self, repo_name):
        return [{"login": "user1"}, {"login": "user2"}]

    def list_workflows(self, repo_name):
        return [{"id": 1, "name": "CI"}]

    def _check_repo_allowed(self, repo_name):
        pass


def _patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(opm, "OS_PROJECTS_DIR", tmp_path / "os_projects")
    monkeypatch.setattr(opm, "OS_PROJECTS_STATE", tmp_path / "os_projects" / "projects.json")
    monkeypatch.setattr(opm, "_os_project_manager", None)


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    mock_gh = MockGitHubOps()
    return OSProjectManager(github=mock_gh)


# ─── Project Creation ─────────────────────────────────────────────


def test_create_project(mgr):
    project = mgr.create_project("test-project", description="A test project")
    assert project.slug == "test-project"
    assert project.name == "Test Project"
    assert project.phase == ProjectPhase.PLANNING
    assert project.health == ProjectHealth.HEALTHY
    assert project.current_version == "0.1.0"
    assert "blerbz" in project.repo_url


def test_create_project_custom_name(mgr):
    project = mgr.create_project("my-project", name="My Custom Name")
    assert project.name == "My Custom Name"
    assert project.slug == "my-project"


def test_create_project_scaffolds_files(mgr):
    mgr.create_project("scaffolded")
    gh = mgr._gh
    expected_files = {"README.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
                      "CHANGELOG.md", "SECURITY.md", ".gitignore"}
    assert set(gh.files_created) == expected_files


def test_create_project_sets_labels(mgr):
    mgr.create_project("labeled")
    assert "labeled" in mgr._gh.labels_created


# ─── Project State Persistence ────────────────────────────────────


def test_project_persists(mgr, tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    mgr.create_project("persist-test")

    # Create a new manager instance (simulates restart)
    mgr2 = OSProjectManager(github=MockGitHubOps())
    project = mgr2.get_project("persist-test")
    assert project is not None
    assert project.slug == "persist-test"


def test_list_projects(mgr):
    mgr.create_project("project-a")
    mgr.create_project("project-b")
    projects = mgr.list_projects()
    assert len(projects) == 2
    slugs = {p.slug for p in projects}
    assert slugs == {"project-a", "project-b"}


# ─── ProjectState Serialization ───────────────────────────────────


def test_project_state_round_trip():
    state = ProjectState(
        name="Test",
        slug="test",
        description="A test",
        phase=ProjectPhase.DEVELOPMENT,
        health=ProjectHealth.HEALTHY,
        created_at=1000.0,
        updated_at=2000.0,
        current_version="1.2.3",
    )
    d = state.to_dict()
    restored = ProjectState.from_dict(d)
    assert restored.name == state.name
    assert restored.slug == state.slug
    assert restored.phase == ProjectPhase.DEVELOPMENT
    assert restored.current_version == "1.2.3"


# ─── Phase Management ────────────────────────────────────────────


def test_advance_phase(mgr):
    mgr.create_project("phase-test")
    assert mgr.get_project("phase-test").phase == ProjectPhase.PLANNING

    new_phase = mgr.advance_phase("phase-test")
    assert new_phase == ProjectPhase.DEVELOPMENT

    new_phase = mgr.advance_phase("phase-test")
    assert new_phase == ProjectPhase.TESTING


def test_advance_phase_stops_at_maintenance(mgr):
    mgr.create_project("phase-max")
    for _ in range(10):  # Advance many times
        mgr.advance_phase("phase-max")
    assert mgr.get_project("phase-max").phase == ProjectPhase.MAINTENANCE


def test_set_phase(mgr):
    mgr.create_project("set-phase")
    mgr.set_phase("set-phase", ProjectPhase.RELEASE)
    assert mgr.get_project("set-phase").phase == ProjectPhase.RELEASE


# ─── Development Operations ──────────────────────────────────────


def test_create_feature_branch(mgr):
    mgr.create_project("branch-test")
    result = mgr.create_feature_branch("branch-test", "new-thing")
    assert result["branch"] == "feature/new-thing"


def test_create_feature_issue(mgr):
    mgr.create_project("issue-test")
    result = mgr.create_feature_issue("issue-test", "Add new feature", "Details")
    assert result["number"] == 42


def test_create_bug_report(mgr):
    mgr.create_project("bug-test")
    result = mgr.create_bug_report("bug-test", "Something broken", "Steps to reproduce")
    assert result["number"] == 42


# ─── Health Check ─────────────────────────────────────────────────


def test_health_check(mgr):
    mgr.create_project("health-test")
    checks = mgr.health_check("health-test")
    assert "health" in checks
    assert "score" in checks


def test_health_check_unknown_project(mgr):
    checks = mgr.health_check("nonexistent")
    assert checks["health"] == "unknown"


# ─── Metrics ──────────────────────────────────────────────────────


def test_update_metrics(mgr):
    mgr.create_project("metrics-test")
    metrics = mgr.update_metrics("metrics-test")
    assert "stars" in metrics
    assert "forks" in metrics
    assert "contributors" in metrics


# ─── Viability Assessment ─────────────────────────────────────────


def test_assess_viability_high():
    mgr = OSProjectManager(github=MockGitHubOps())
    result = mgr.assess_viability(
        "An open source tool to automate Python project management and simplify deployment",
        tech_stack=["python", "javascript"],
    )
    assert result["viability"] in ("high", "medium")
    assert result["score"] > 0
    assert len(result["factors"]) > 0


def test_assess_viability_low():
    mgr = OSProjectManager(github=MockGitHubOps())
    result = mgr.assess_viability("x")
    assert result["viability"] == "low"


# ─── Templates ────────────────────────────────────────────────────


def test_readme_template():
    readme = opm._readme_template("Robin", "A sidekick", "robin")
    assert "Robin" in readme
    assert "robin" in readme
    assert "MIT" in readme or "License" in readme
    assert "BLERBZ" in readme


def test_contributing_template():
    content = opm._contributing_template("Robin", "robin")
    assert "Contributing" in content
    assert "Pull Requests" in content
    assert "robin" in content


def test_code_of_conduct_template():
    content = opm._code_of_conduct_template()
    assert "Contributor Covenant" in content
    assert "Our Pledge" in content


def test_changelog_template():
    content = opm._changelog_template("Robin")
    assert "Changelog" in content
    assert "[Unreleased]" in content


def test_security_template():
    content = opm._security_template("robin")
    assert "Security Policy" in content
    assert "Reporting a Vulnerability" in content


def test_gitignore_python():
    content = opm._gitignore_python()
    assert "__pycache__/" in content
    assert ".env" in content
    assert ".venv/" in content


# ─── Project Status ───────────────────────────────────────────────


def test_get_project_status(mgr):
    mgr.create_project("status-test", description="Status test project")
    status = mgr.get_project_status("status-test")
    assert status["name"] == "Status Test"
    assert status["phase"] == "planning"
    assert status.get("github_stats") is not None


def test_get_project_status_missing(mgr):
    status = mgr.get_project_status("nonexistent")
    assert "error" in status
