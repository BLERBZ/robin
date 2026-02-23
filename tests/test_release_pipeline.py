"""Tests for lib/release_pipeline.py — Automated release management."""

import json
import time
from pathlib import Path

import pytest

import lib.release_pipeline as rp
from lib.release_pipeline import (
    ReleasePipeline,
    SemVer,
    BumpType,
    CommitInfo,
    ReleasePrep,
    ReleaseStatus,
)
from lib.github_ops import GitHubError


class MockGitHubOps:
    """Mock GitHub operations for release testing."""

    def __init__(self):
        self.releases = []
        self.files_updated = []

    def list_releases(self, repo_name, per_page=10):
        return self.releases

    def get_file_content(self, repo_name, path, ref="main"):
        import base64
        if path == "CHANGELOG.md":
            content = base64.b64encode(b"# Changelog\n\n## [Unreleased]\n").decode()
            return {"content": content, "sha": "abc123"}
        raise GitHubError("Not found", status_code=404)

    def create_or_update_file(self, repo_name, path, content, message, branch="main", sha=None):
        self.files_updated.append({"path": path, "content": content})
        return {"content": {"path": path}}

    def create_release(self, repo_name, config):
        return {"html_url": f"https://github.com/blerbz/{repo_name}/releases/tag/{config.tag_name}"}

    def compare_commits(self, repo_name, base, head):
        return {"commits": [
            {"sha": "abc12345", "commit": {"message": "feat: Add new feature", "author": {"name": "Dev", "date": "2024-01-01"}}},
            {"sha": "def67890", "commit": {"message": "fix: Fix broken thing", "author": {"name": "Dev", "date": "2024-01-02"}}},
            {"sha": "ghi11111", "commit": {"message": "docs: Update README", "author": {"name": "Dev", "date": "2024-01-03"}}},
        ]}

    def list_commits(self, repo_name, sha="main", per_page=30, since=None):
        return [
            {"sha": "abc12345", "commit": {"message": "feat: New thing", "author": {"name": "Dev", "date": "2024-01-01"}}},
            {"sha": "def67890", "commit": {"message": "fix: Bug fix", "author": {"name": "Dev", "date": "2024-01-02"}}},
        ]

    def _check_repo_allowed(self, repo_name):
        pass

    def get_branch_sha(self, repo_name, branch="main"):
        return "abc123"


def _patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "RELEASES_DIR", tmp_path / "releases")
    monkeypatch.setattr(rp, "RELEASES_LOG", tmp_path / "releases" / "release_log.jsonl")
    monkeypatch.setattr(rp, "_release_pipeline", None)


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    return ReleasePipeline(github=MockGitHubOps())


# ─── SemVer ───────────────────────────────────────────────────────


def test_semver_parse():
    v = SemVer.parse("1.2.3")
    assert v.major == 1
    assert v.minor == 2
    assert v.patch == 3


def test_semver_parse_with_v():
    v = SemVer.parse("v1.2.3")
    assert v.major == 1


def test_semver_parse_prerelease():
    v = SemVer.parse("1.2.3-rc.1")
    assert v.prerelease == "rc.1"


def test_semver_parse_invalid():
    with pytest.raises(ValueError):
        SemVer.parse("not-a-version")


def test_semver_str():
    v = SemVer(1, 2, 3)
    assert str(v) == "1.2.3"


def test_semver_str_prerelease():
    v = SemVer(1, 2, 3, prerelease="rc.1")
    assert str(v) == "1.2.3-rc.1"


def test_semver_str_build():
    v = SemVer(1, 2, 3, build="20240101")
    assert str(v) == "1.2.3+20240101"


def test_semver_tag_name():
    v = SemVer(1, 2, 3)
    assert v.tag_name() == "v1.2.3"


def test_semver_bump_major():
    v = SemVer(1, 2, 3)
    bumped = v.bump(BumpType.MAJOR)
    assert str(bumped) == "2.0.0"


def test_semver_bump_minor():
    v = SemVer(1, 2, 3)
    bumped = v.bump(BumpType.MINOR)
    assert str(bumped) == "1.3.0"


def test_semver_bump_patch():
    v = SemVer(1, 2, 3)
    bumped = v.bump(BumpType.PATCH)
    assert str(bumped) == "1.2.4"


def test_semver_bump_prerelease():
    v = SemVer(1, 2, 3)
    bumped = v.bump(BumpType.PRERELEASE)
    assert "rc" in bumped.prerelease


def test_semver_bump_prerelease_increment():
    v = SemVer(1, 2, 3, prerelease="rc.1")
    bumped = v.bump(BumpType.PRERELEASE)
    assert "rc.2" in bumped.prerelease


# ─── CommitInfo ───────────────────────────────────────────────────


def test_commit_categorize_feat():
    assert CommitInfo.categorize("feat: Add new feature") == "feat"
    assert CommitInfo.categorize("Add: New thing") == "feat"


def test_commit_categorize_fix():
    assert CommitInfo.categorize("fix: Broken thing") == "fix"
    assert CommitInfo.categorize("bugfix: Issue #42") == "fix"


def test_commit_categorize_docs():
    assert CommitInfo.categorize("docs: Update README") == "docs"


def test_commit_categorize_refactor():
    assert CommitInfo.categorize("refactor: Clean up code") == "refactor"


def test_commit_categorize_chore():
    assert CommitInfo.categorize("chore: Update deps") == "chore"
    assert CommitInfo.categorize("ci: Fix pipeline") == "chore"


def test_commit_categorize_heuristic():
    assert CommitInfo.categorize("Fix the login page") == "fix"
    assert CommitInfo.categorize("Add user authentication") == "feat"


def test_commit_categorize_other():
    assert CommitInfo.categorize("Merge branch main") == "other"


# ─── Auto Bump Detection ─────────────────────────────────────────


def test_auto_detect_major():
    commits = [
        CommitInfo(sha="a", message="BREAKING: Remove old API", author="Dev", date="2024-01-01"),
    ]
    pipeline_local = ReleasePipeline(github=MockGitHubOps())
    assert pipeline_local.auto_detect_bump(commits) == BumpType.MAJOR


def test_auto_detect_minor():
    commits = [
        CommitInfo(sha="a", message="New feature", author="Dev", date="", category="feat"),
    ]
    pipeline_local = ReleasePipeline(github=MockGitHubOps())
    assert pipeline_local.auto_detect_bump(commits) == BumpType.MINOR


def test_auto_detect_patch():
    commits = [
        CommitInfo(sha="a", message="Fix bug", author="Dev", date="", category="fix"),
    ]
    pipeline_local = ReleasePipeline(github=MockGitHubOps())
    assert pipeline_local.auto_detect_bump(commits) == BumpType.PATCH


# ─── Release Preparation ─────────────────────────────────────────


def test_prepare_release(pipeline):
    prep = pipeline.prepare_release("robin", BumpType.MINOR)
    assert prep.project_slug == "robin"
    assert prep.status == ReleaseStatus.READY
    assert len(prep.commits) > 0
    assert prep.changelog_entry
    assert prep.release_notes


def test_prepare_release_auto_bump(pipeline):
    prep = pipeline.prepare_release("robin")
    assert prep.next_version.minor > 0 or prep.next_version.patch > 0


# ─── Changelog Generation ────────────────────────────────────────


def test_generate_changelog_entry(pipeline):
    commits = [
        CommitInfo(sha="abc", message="Add login", author="Dev", date="", category="feat"),
        CommitInfo(sha="def", message="Fix crash", author="Dev", date="", category="fix"),
    ]
    version = SemVer(1, 0, 0)
    entry = pipeline.generate_changelog_entry(version, commits)
    assert "1.0.0" in entry
    assert "Added" in entry
    assert "Fixed" in entry


# ─── Release Notes ────────────────────────────────────────────────


def test_generate_release_notes(pipeline):
    commits = [
        CommitInfo(sha="abc", message="Add login", author="Dev", date="", category="feat"),
    ]
    version = SemVer(1, 0, 0)
    notes = pipeline.generate_release_notes("robin", version, commits)
    assert "robin" in notes.lower() or "Robin" in notes
    assert "1.0.0" in notes


# ─── Release Execution ───────────────────────────────────────────


def test_execute_release(pipeline):
    prep = pipeline.prepare_release("robin", BumpType.PATCH)
    results = pipeline.execute_release(prep)
    assert results["status"] == "published"
    assert "release_url" in results


# ─── Announcement Generation ─────────────────────────────────────


def test_generate_announcement(pipeline):
    prep = pipeline.prepare_release("robin", BumpType.MINOR)
    announcements = pipeline.generate_announcement(prep)
    assert "blog" in announcements
    assert "twitter" in announcements
    assert "summary" in announcements
    assert "robin" in announcements["twitter"].lower()


# ─── Release History ─────────────────────────────────────────────


def test_release_history_empty(pipeline):
    history = pipeline.get_release_history("robin")
    assert isinstance(history, list)


def test_release_history_with_releases(pipeline, tmp_path, monkeypatch):
    mock_gh = MockGitHubOps()
    mock_gh.releases = [
        {"tag_name": "v0.1.0", "name": "v0.1.0", "published_at": "2024-01-01", "prerelease": False, "html_url": "url"},
    ]
    _patch_paths(tmp_path, monkeypatch)
    p = ReleasePipeline(github=mock_gh)
    history = p.get_release_history("robin")
    assert len(history) == 1
    assert history[0]["tag"] == "v0.1.0"
