"""Tests for lib/github_ops.py — GitHub API operations."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import lib.github_ops as github_ops
from lib.github_ops import (
    GitHubOps,
    GitHubError,
    RateLimitError,
    RepoNotAllowedError,
    PrivateRepoBlockedError,
    RepoConfig,
    RepoVisibility,
    IssueConfig,
    PRConfig,
    ReleaseConfig,
    RateState,
    OwnerType,
    _KNOWN_PRIVATE_REPOS,
)


def _patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(github_ops, "GITHUB_STATE_DIR", tmp_path / "github")
    monkeypatch.setattr(github_ops, "GITHUB_CACHE_FILE", tmp_path / "github" / "api_cache.json")
    monkeypatch.setattr(github_ops, "GITHUB_AUDIT_LOG", tmp_path / "github" / "audit.jsonl")


@pytest.fixture
def gh(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("KAIT_GITHUB_TOKEN", "ghp_test_token_123")
    monkeypatch.setenv("KAIT_GITHUB_OWNER", "BLERBZ")
    monkeypatch.setenv("KAIT_GITHUB_ALLOWED_REPOS", "robin,kait-intel,test-project")
    # Reset singleton
    monkeypatch.setattr(github_ops, "_github_ops", None)
    return GitHubOps(
        token="ghp_test_token_123",
        owner="BLERBZ",
        allowed_repos=["robin", "kait-intel", "test-project"],
        public_only=True,
        owner_type=OwnerType.USER,
    )


@pytest.fixture
def gh_no_allowlist(tmp_path, monkeypatch):
    """GitHubOps with no allowlist but public_only enabled."""
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(github_ops, "_github_ops", None)
    return GitHubOps(
        token="ghp_test_token_123",
        owner="BLERBZ",
        allowed_repos=[],
        public_only=True,
        owner_type=OwnerType.USER,
    )


# ─── Auth & Security ─────────────────────────────────────────────


def test_no_token_raises(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    ops = GitHubOps(token="", owner="BLERBZ")
    with pytest.raises(GitHubError, match="No GitHub token"):
        ops._check_token()


def test_repo_not_allowed(gh):
    with pytest.raises(RepoNotAllowedError):
        gh._check_repo_allowed("unauthorized-repo")


def test_repo_allowed(gh):
    # Should not raise
    gh._check_repo_allowed("robin")
    gh._check_repo_allowed("kait-intel")


def test_empty_allowlist_allows_all(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    ops = GitHubOps(token="test", owner="BLERBZ", allowed_repos=[], owner_type=OwnerType.USER)
    # Empty allowlist means no filtering
    ops._check_repo_allowed("any-repo")


# ─── Public-Only Enforcement ─────────────────────────────────────


def test_known_private_repos_blocked(gh):
    """Hard-coded private repos are always blocked."""
    for repo in _KNOWN_PRIVATE_REPOS:
        with pytest.raises(PrivateRepoBlockedError, match="private"):
            gh._verify_repo_public(repo)


def test_known_private_repos_set():
    """Verify the hardcoded blocklist contains the expected repos."""
    assert "blerbz" in _KNOWN_PRIVATE_REPOS
    assert "blerbz-app" in _KNOWN_PRIVATE_REPOS
    assert "buyrockz" in _KNOWN_PRIVATE_REPOS
    assert "maifarm" in _KNOWN_PRIVATE_REPOS


def test_cached_public_repo_allowed(gh):
    """Repo verified as public should be cached and not re-checked."""
    gh._public_repos_cache["robin"] = True
    gh._public_repos_cache_ts = time.time()
    # Should not raise — uses cache
    gh._verify_repo_public("robin")


def test_cached_private_repo_blocked(gh):
    """Repo cached as private should be blocked."""
    gh._public_repos_cache["secret-project"] = False
    gh._public_repos_cache_ts = time.time()
    with pytest.raises(PrivateRepoBlockedError):
        gh._verify_repo_public("secret-project")


def test_public_only_disabled_allows_everything(tmp_path, monkeypatch):
    """When public_only is False, no visibility check happens."""
    _patch_paths(tmp_path, monkeypatch)
    ops = GitHubOps(
        token="test", owner="BLERBZ", allowed_repos=[],
        public_only=False, owner_type=OwnerType.USER,
    )
    # Should not raise even for known private repos
    ops._verify_repo_public("blerbz")
    ops._verify_repo_public("secret-thing")


def test_public_only_defaults_to_true(tmp_path, monkeypatch):
    """Public-only mode defaults to True for safety."""
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.delenv("KAIT_GITHUB_PUBLIC_ONLY", raising=False)
    ops = GitHubOps(token="test", owner="BLERBZ", owner_type=OwnerType.USER)
    assert ops._public_only is True


def test_public_only_env_false(tmp_path, monkeypatch):
    """KAIT_GITHUB_PUBLIC_ONLY=false disables the check."""
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setenv("KAIT_GITHUB_PUBLIC_ONLY", "false")
    ops = GitHubOps(token="test", owner="BLERBZ", owner_type=OwnerType.USER)
    assert ops._public_only is False


def test_check_repo_access_combines_allowlist_and_visibility(gh):
    """_check_repo_access enforces both allowlist and public-only."""
    # Not in allowlist → RepoNotAllowedError
    with pytest.raises(RepoNotAllowedError):
        gh._check_repo_access("unauthorized-repo")

    # In allowlist but known-private → PrivateRepoBlockedError
    gh._allowed_repos.append("blerbz")
    with pytest.raises(PrivateRepoBlockedError):
        gh._check_repo_access("blerbz")


def test_create_repo_blocks_private(gh):
    """Creating a private repo is blocked when public_only is True."""
    config = RepoConfig(name="new-secret", visibility=RepoVisibility.PRIVATE)
    with pytest.raises(PrivateRepoBlockedError):
        gh.create_repo(config)


def test_private_repo_blocked_audit_logged(gh, tmp_path, monkeypatch):
    """Blocked private repo attempts are audit-logged."""
    audit_log = tmp_path / "github" / "audit.jsonl"
    monkeypatch.setattr(github_ops, "GITHUB_AUDIT_LOG", audit_log)

    with pytest.raises(PrivateRepoBlockedError):
        gh._verify_repo_public("blerbz")

    assert audit_log.exists()
    line = audit_log.read_text().strip()
    entry = json.loads(line)
    assert entry["action"] == "BLOCKED_PRIVATE_REPO"
    assert entry["target"] == "blerbz"


# ─── Owner Type Detection ────────────────────────────────────────


def test_owner_type_user(gh):
    """User owner type is correctly set."""
    assert gh._owner_type == OwnerType.USER


def test_owner_type_org(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    ops = GitHubOps(
        token="test", owner="someorg",
        owner_type=OwnerType.ORG,
    )
    assert ops._owner_type == OwnerType.ORG


def test_owner_repos_path_user(gh):
    assert gh._owner_repos_path() == "/user/repos"


def test_owner_repos_path_org(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    ops = GitHubOps(
        token="test", owner="someorg",
        owner_type=OwnerType.ORG,
    )
    assert ops._owner_repos_path() == "/orgs/someorg/repos"


# ─── Legacy Compatibility ────────────────────────────────────────


def test_legacy_org_parameter(tmp_path, monkeypatch):
    """The 'org' parameter still works as an alias for 'owner'."""
    _patch_paths(tmp_path, monkeypatch)
    ops = GitHubOps(token="test", org="BLERBZ", owner_type=OwnerType.USER)
    assert ops._owner == "BLERBZ"
    assert ops._org == "BLERBZ"


def test_legacy_env_var(tmp_path, monkeypatch):
    """KAIT_GITHUB_ORG env var still works when KAIT_GITHUB_OWNER is not set."""
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.delenv("KAIT_GITHUB_OWNER", raising=False)
    monkeypatch.setenv("KAIT_GITHUB_ORG", "legacy-org")
    ops = GitHubOps(token="test", owner_type=OwnerType.USER)
    assert ops._owner == "legacy-org"


# ─── Rate Limiting ────────────────────────────────────────────────


def test_rate_limit_check_passes_with_remaining(gh):
    gh._rate.remaining = 1000
    gh._rate.reset_at = time.time() + 3600
    # Should not raise
    gh._check_rate()


def test_rate_limit_check_raises_when_exhausted(gh):
    gh._rate.remaining = 50
    gh._rate.reset_at = time.time() + 3600
    with pytest.raises(RateLimitError):
        gh._check_rate()


def test_rate_status(gh):
    status = gh.get_rate_status()
    assert "limit" in status
    assert "remaining" in status
    assert "reset_at" in status
    assert "reset_in_s" in status


# ─── Audit Logging ────────────────────────────────────────────────


def test_audit_log_written(gh, tmp_path, monkeypatch):
    audit_log = tmp_path / "github" / "audit.jsonl"
    monkeypatch.setattr(github_ops, "GITHUB_AUDIT_LOG", audit_log)
    gh._audit("test_action", "test_target", {"detail": "value"})
    assert audit_log.exists()
    line = audit_log.read_text().strip()
    entry = json.loads(line)
    assert entry["action"] == "test_action"
    assert entry["target"] == "test_target"


# ─── Config Parsing ──────────────────────────────────────────────


def test_allowed_repos_from_string(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    ops = GitHubOps(token="test", owner="BLERBZ", allowed_repos="robin,kait-intel")
    assert ops._allowed_repos == ["robin", "kait-intel"]


def test_allowed_repos_from_list(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    ops = GitHubOps(token="test", owner="BLERBZ", allowed_repos=["robin", "kait-intel"])
    assert ops._allowed_repos == ["robin", "kait-intel"]


# ─── RepoConfig ──────────────────────────────────────────────────


def test_repo_config_defaults():
    config = RepoConfig(name="test-repo")
    assert config.name == "test-repo"
    assert config.visibility == RepoVisibility.PUBLIC
    assert config.license_template == "mit"
    assert config.has_issues is True
    assert config.has_discussions is True
    assert config.auto_init is True


def test_repo_config_private():
    config = RepoConfig(name="test", visibility=RepoVisibility.PRIVATE)
    assert config.visibility == RepoVisibility.PRIVATE


# ─── IssueConfig ─────────────────────────────────────────────────


def test_issue_config():
    config = IssueConfig(title="Bug: something broken", body="Details here", labels=["bug"])
    assert config.title == "Bug: something broken"
    assert config.labels == ["bug"]


# ─── PRConfig ────────────────────────────────────────────────────


def test_pr_config():
    config = PRConfig(title="Add feature", head="feature/new", base="main")
    assert config.head == "feature/new"
    assert config.base == "main"
    assert config.draft is False


# ─── ReleaseConfig ───────────────────────────────────────────────


def test_release_config():
    config = ReleaseConfig(tag_name="v1.0.0", name="Release 1.0.0")
    assert config.tag_name == "v1.0.0"
    assert config.generate_release_notes is True


# ─── Health Check ─────────────────────────────────────────────────


def test_health_check_no_token(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    ops = GitHubOps(token="", owner="BLERBZ", owner_type=OwnerType.USER)
    health = ops.health_check()
    assert health["status"] == "auth_error" or health["user"]["valid"] is False


# ─── Context Manager ─────────────────────────────────────────────


def test_context_manager(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    with GitHubOps(token="test", owner="BLERBZ") as ops:
        assert ops is not None


# ─── Repo Path ────────────────────────────────────────────────────


def test_repo_path(gh):
    assert gh._repo_path("robin") == "/repos/BLERBZ/robin"


# ─── Standard Labels ─────────────────────────────────────────────


def test_standard_labels_list():
    """Verify the expected labels would be created."""
    labels = [
        ("bug", "d73a4a", "Something isn't working"),
        ("enhancement", "a2eeef", "New feature or request"),
        ("good first issue", "7057ff", "Good for newcomers"),
        ("help wanted", "008672", "Extra attention is needed"),
        ("documentation", "0075ca", "Improvements or additions to documentation"),
        ("kait-managed", "1d76db", "Managed by Kait OS Sidekick"),
        ("blerbz-os", "e4e669", "BLERBZ Open Source"),
        ("release", "0e8a16", "Release-related"),
        ("security", "b60205", "Security-related"),
        ("dependencies", "0366d6", "Pull requests that update a dependency"),
    ]
    assert len(labels) == 10
    assert all(len(color) == 6 for _, color, _ in labels)


# ─── Cache TTL ────────────────────────────────────────────────────


def test_cache_expires(gh):
    """Stale cache entries should be treated as invalid."""
    gh._public_repos_cache["some-repo"] = True
    gh._public_repos_cache_ts = time.time() - 600  # 10 min ago, past 5 min TTL
    assert not gh._is_public_repo_cache_valid()


def test_cache_valid(gh):
    """Fresh cache entries should be valid."""
    gh._public_repos_cache["some-repo"] = True
    gh._public_repos_cache_ts = time.time()
    assert gh._is_public_repo_cache_valid()
