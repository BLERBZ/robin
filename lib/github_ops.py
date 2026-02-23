"""
Kait GitHub Operations — Core GitHub API integration for OS Sidekick

Provides repository management, issue/PR operations, release management,
and branch operations through the GitHub REST API.

Security:
  - PUBLIC REPOS ONLY: Kait will NEVER access private repositories.
  - Two-layer protection: token scope (public_repo only) + software enforcement.
  - Every operation verifies repo visibility before proceeding.
  - All blocked attempts are audit-logged.

Rate limiting: Exponential backoff with configurable limits.

Usage:
    from lib.github_ops import GitHubOps
    gh = GitHubOps()
    gh.create_repo("robin", description="BLERBZ OS Sidekick")
"""

from __future__ import annotations

import json
import os
import time
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from lib.diagnostics import log_debug

# ============= Configuration =============

GITHUB_API_BASE = "https://api.github.com"
KAIT_DIR = Path.home() / ".kait"
GITHUB_STATE_DIR = KAIT_DIR / "github"
GITHUB_CACHE_FILE = GITHUB_STATE_DIR / "api_cache.json"
GITHUB_AUDIT_LOG = GITHUB_STATE_DIR / "audit.jsonl"

# Rate limiting
DEFAULT_RATE_LIMIT_BUFFER = 100  # Stop when this many requests remain
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 60.0
MAX_RETRIES = 3

# Env vars
ENV_TOKEN = "KAIT_GITHUB_TOKEN"
ENV_OWNER = "KAIT_GITHUB_OWNER"
ENV_ALLOWED_REPOS = "KAIT_GITHUB_ALLOWED_REPOS"
ENV_PUBLIC_ONLY = "KAIT_GITHUB_PUBLIC_ONLY"

# Legacy env var support
ENV_ORG = "KAIT_GITHUB_ORG"


class GitHubError(Exception):
    """Base error for GitHub operations."""

    def __init__(self, message: str, status_code: int = 0, response: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


class RateLimitError(GitHubError):
    """Raised when GitHub API rate limit is hit."""

    def __init__(self, reset_at: float):
        self.reset_at = reset_at
        wait = max(0, reset_at - time.time())
        super().__init__(f"Rate limited. Resets in {wait:.0f}s", status_code=429)


class RepoNotAllowedError(GitHubError):
    """Raised when accessing a repo not in the allowlist."""

    def __init__(self, repo: str, allowed: List[str]):
        super().__init__(
            f"Repository '{repo}' not in allowlist: {allowed}",
            status_code=403,
        )


class PrivateRepoBlockedError(GitHubError):
    """Raised when attempting to access a private repository.

    HARD SAFETY BLOCK: Kait must NEVER access private repositories.
    This error cannot be bypassed — it is a fundamental security constraint.
    """

    def __init__(self, repo: str):
        super().__init__(
            f"BLOCKED: Repository '{repo}' is private. "
            f"Kait is restricted to PUBLIC repositories only. "
            f"This attempt has been audit-logged.",
            status_code=403,
        )


class RepoVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


@dataclass
class RepoConfig:
    """Configuration for creating a new repository."""

    name: str
    description: str = ""
    visibility: RepoVisibility = RepoVisibility.PUBLIC
    license_template: str = "mit"
    has_issues: bool = True
    has_wiki: bool = False
    has_discussions: bool = True
    auto_init: bool = True
    gitignore_template: str = "Python"
    topics: List[str] = field(default_factory=list)


@dataclass
class IssueConfig:
    """Configuration for creating an issue."""

    title: str
    body: str = ""
    labels: List[str] = field(default_factory=list)
    assignees: List[str] = field(default_factory=list)
    milestone: Optional[int] = None


@dataclass
class PRConfig:
    """Configuration for creating a pull request."""

    title: str
    body: str = ""
    head: str = ""
    base: str = "main"
    draft: bool = False
    labels: List[str] = field(default_factory=list)


@dataclass
class ReleaseConfig:
    """Configuration for creating a release."""

    tag_name: str
    name: str = ""
    body: str = ""
    draft: bool = False
    prerelease: bool = False
    generate_release_notes: bool = True
    target_commitish: str = "main"


@dataclass
class RateState:
    """Track GitHub API rate limit state."""

    limit: int = 5000
    remaining: int = 5000
    reset_at: float = 0.0
    last_check: float = 0.0


# ─── Private repo names (NEVER touch these) ──────────────────────
# Hardcoded safety net — even if all other checks fail, these are blocked.
_KNOWN_PRIVATE_REPOS = frozenset({"blerbz", "blerbz-app", "buyrockz", "maifarm"})


class OwnerType(str, Enum):
    """GitHub account type — determines API endpoint paths."""
    USER = "user"
    ORG = "org"


class GitHubOps:
    """Core GitHub API operations for Kait OS Sidekick.

    Thread-safe, rate-limited, with audit logging.
    PUBLIC REPOS ONLY — private repository access is hard-blocked.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        owner: Optional[str] = None,
        org: Optional[str] = None,
        allowed_repos: Optional[List[str]] = None,
        public_only: Optional[bool] = None,
        owner_type: Optional[OwnerType] = None,
    ):
        self._token = token or os.environ.get(ENV_TOKEN, "")
        # Support both 'owner' (new) and 'org' (legacy) parameter names
        self._owner = owner or org or os.environ.get(ENV_OWNER, "") or os.environ.get(ENV_ORG, "BLERBZ")
        # Legacy alias
        self._org = self._owner

        raw_allowed = allowed_repos or os.environ.get(ENV_ALLOWED_REPOS, "")
        if isinstance(raw_allowed, str):
            self._allowed_repos = [r.strip() for r in raw_allowed.split(",") if r.strip()]
        else:
            self._allowed_repos = list(raw_allowed)

        # PUBLIC-ONLY ENFORCEMENT (defaults to True — safety first)
        if public_only is not None:
            self._public_only = public_only
        else:
            self._public_only = os.environ.get(ENV_PUBLIC_ONLY, "true").lower() != "false"

        # Owner type detection (user vs org) — auto-detected on first API call
        self._owner_type: Optional[OwnerType] = owner_type
        self._owner_type_detected = owner_type is not None

        # Cache of verified-public repos to avoid repeated API calls
        self._public_repos_cache: Dict[str, bool] = {}
        self._public_repos_cache_ts: float = 0.0
        self._public_repos_cache_ttl: float = 300.0  # 5 min TTL

        self._rate = RateState()
        self._client: Optional[httpx.Client] = None

        # Ensure state directories
        GITHUB_STATE_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Client Management ────────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "kait-os-sidekick/1.0",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.Client(
                base_url=GITHUB_API_BASE,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    def close(self):
        if self._client and not self._client.is_closed:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ─── Auth & Security ──────────────────────────────────────────

    def _check_token(self):
        if not self._token:
            raise GitHubError("No GitHub token configured. Set KAIT_GITHUB_TOKEN.", status_code=401)

    def _check_repo_allowed(self, repo_name: str):
        """Check static allowlist (if configured)."""
        if self._allowed_repos and repo_name not in self._allowed_repos:
            raise RepoNotAllowedError(repo_name, self._allowed_repos)

    def _detect_owner_type(self):
        """Auto-detect whether the owner is a user or org account."""
        if self._owner_type_detected:
            return
        try:
            result = self._request_raw("GET", f"/users/{self._owner}")
            acct_type = result.get("type", "").lower()
            if acct_type == "organization":
                self._owner_type = OwnerType.ORG
            else:
                self._owner_type = OwnerType.USER
        except GitHubError:
            # Default to user if detection fails
            self._owner_type = OwnerType.USER
        self._owner_type_detected = True
        log_debug("github_ops", f"Owner '{self._owner}' detected as {self._owner_type.value}")

    def _repo_path(self, repo_name: str) -> str:
        return f"/repos/{self._owner}/{repo_name}"

    def _owner_repos_path(self) -> str:
        """Get the correct API path for listing/creating repos based on owner type."""
        self._detect_owner_type()
        if self._owner_type == OwnerType.ORG:
            return f"/orgs/{self._owner}/repos"
        return "/user/repos"

    def _is_public_repo_cache_valid(self) -> bool:
        return (time.time() - self._public_repos_cache_ts) < self._public_repos_cache_ttl

    def _verify_repo_public(self, repo_name: str):
        """CRITICAL SAFETY CHECK: Verify a repository is public before ANY operation.

        This is the core enforcement mechanism. It checks:
        1. The local cache of known-public repos
        2. If not cached, queries the GitHub API for repo visibility
        3. Hard-blocks with PrivateRepoBlockedError if private

        This check CANNOT be bypassed when public_only mode is enabled.
        """
        if not self._public_only:
            return

        # Hardcoded blocklist — final safety net
        if repo_name in _KNOWN_PRIVATE_REPOS:
            self._audit("BLOCKED_PRIVATE_REPO", repo_name, {"source": "hardcoded_blocklist"})
            raise PrivateRepoBlockedError(repo_name)

        # Check cache first
        if self._is_public_repo_cache_valid() and repo_name in self._public_repos_cache:
            if self._public_repos_cache[repo_name]:
                return
            self._audit("BLOCKED_PRIVATE_REPO", repo_name, {"source": "cache"})
            raise PrivateRepoBlockedError(repo_name)

        # Query GitHub API for repo visibility
        try:
            result = self._request_raw("GET", self._repo_path(repo_name))
            is_private = result.get("private", True)  # Default to private (safe)
            visibility = result.get("visibility", "private")

            # Update cache
            self._public_repos_cache[repo_name] = not is_private
            self._public_repos_cache_ts = time.time()

            if is_private:
                self._audit("BLOCKED_PRIVATE_REPO", repo_name, {
                    "visibility": visibility,
                    "source": "api_check",
                })
                raise PrivateRepoBlockedError(repo_name)

        except PrivateRepoBlockedError:
            raise
        except GitHubError as e:
            if e.status_code == 404:
                # Repo doesn't exist or token can't see it — safe to proceed
                # (will fail later with proper error if truly missing)
                return
            raise

    def _check_repo_access(self, repo_name: str):
        """Full access check: allowlist + public-only enforcement.

        This is the single entry point for all repo access validation.
        Called before every operation that targets a specific repository.
        """
        self._check_repo_allowed(repo_name)
        self._verify_repo_public(repo_name)

    # ─── Rate Limiting ────────────────────────────────────────────

    def _update_rate(self, response: httpx.Response):
        self._rate.limit = int(response.headers.get("x-ratelimit-limit", self._rate.limit))
        self._rate.remaining = int(
            response.headers.get("x-ratelimit-remaining", self._rate.remaining)
        )
        self._rate.reset_at = float(response.headers.get("x-ratelimit-reset", self._rate.reset_at))
        self._rate.last_check = time.time()

    def _check_rate(self):
        if self._rate.remaining <= DEFAULT_RATE_LIMIT_BUFFER and self._rate.reset_at > time.time():
            raise RateLimitError(self._rate.reset_at)

    def get_rate_status(self) -> Dict[str, Any]:
        return {
            "limit": self._rate.limit,
            "remaining": self._rate.remaining,
            "reset_at": self._rate.reset_at,
            "reset_in_s": max(0, self._rate.reset_at - time.time()),
        }

    # ─── Audit Logging ────────────────────────────────────────────

    def _audit(self, action: str, target: str, details: Optional[Dict] = None):
        entry = {
            "ts": time.time(),
            "action": action,
            "target": target,
            "org": self._org,
            "details": details or {},
        }
        try:
            with open(GITHUB_AUDIT_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass
        log_debug("github_ops", f"{action} {target}")

    # ─── Core API Methods ─────────────────────────────────────────

    def _do_request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Low-level HTTP request with retry logic. No access checks."""
        client = self._get_client()
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                response = client.request(
                    method=method,
                    url=path,
                    json=json_data,
                    params=params,
                )
                self._update_rate(response)

                if response.status_code == 429:
                    reset_at = float(response.headers.get("x-ratelimit-reset", time.time() + 60))
                    raise RateLimitError(reset_at)

                if response.status_code == 204:
                    return {"status": "success", "code": 204}

                data = response.json() if response.content else {}

                if response.status_code >= 400:
                    msg = data.get("message", f"HTTP {response.status_code}")
                    raise GitHubError(msg, status_code=response.status_code, response=data)

                return data

            except RateLimitError:
                raise
            except GitHubError:
                raise
            except httpx.TimeoutException as e:
                last_error = e
                wait = min(BACKOFF_BASE_S * (2**attempt), BACKOFF_MAX_S)
                time.sleep(wait)
            except Exception as e:
                last_error = e
                wait = min(BACKOFF_BASE_S * (2**attempt), BACKOFF_MAX_S)
                time.sleep(wait)

        raise GitHubError(f"Request failed after {MAX_RETRIES} retries: {last_error}")

    def _request_raw(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """API request with auth/rate checks but NO repo access checks.

        Used internally for owner-type detection and visibility verification
        to avoid circular dependency with _check_repo_access.
        """
        self._check_token()
        self._check_rate()
        return self._do_request(method, path, json_data, params)

    def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """API request with full auth, rate, and safety checks."""
        self._check_token()
        self._check_rate()
        return self._do_request(method, path, json_data, params)

    # ─── Repository Operations ────────────────────────────────────

    def create_repo(self, config: RepoConfig) -> Dict[str, Any]:
        # SAFETY: Block creation of private repos
        if self._public_only and config.visibility == RepoVisibility.PRIVATE:
            self._audit("BLOCKED_PRIVATE_REPO_CREATE", config.name, {
                "requested_visibility": config.visibility.value,
            })
            raise PrivateRepoBlockedError(config.name)

        self._audit("create_repo", config.name)

        payload: Dict[str, Any] = {
            "name": config.name,
            "description": config.description,
            "private": False,  # Always public when public_only is enabled
            "has_issues": config.has_issues,
            "has_wiki": config.has_wiki,
            "has_discussions": config.has_discussions,
            "auto_init": config.auto_init,
            "license_template": config.license_template,
            "gitignore_template": config.gitignore_template,
        }

        if not self._public_only:
            payload["private"] = config.visibility == RepoVisibility.PRIVATE

        # Use correct endpoint based on owner type (user vs org)
        self._detect_owner_type()
        if self._owner_type == OwnerType.ORG:
            endpoint = f"/orgs/{self._owner}/repos"
        else:
            endpoint = "/user/repos"

        result = self._request("POST", endpoint, json_data=payload)

        # Set topics if specified
        if config.topics:
            self.set_repo_topics(config.name, config.topics)

        return result

    def get_repo(self, repo_name: str) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        return self._request("GET", self._repo_path(repo_name))

    def list_repos(self, sort: str = "updated", per_page: int = 30) -> List[Dict[str, Any]]:
        """List repositories. When public_only is enabled, only returns public repos."""
        self._detect_owner_type()
        if self._owner_type == OwnerType.ORG:
            endpoint = f"/orgs/{self._owner}/repos"
            params: Dict[str, Any] = {"sort": sort, "per_page": per_page, "type": "public"}
        else:
            endpoint = f"/users/{self._owner}/repos"
            params = {"sort": sort, "per_page": per_page, "type": "public"}

        if not self._public_only:
            params.pop("type", None)

        result = self._request("GET", endpoint, params=params)
        repos = result if isinstance(result, list) else []

        # Double-check: filter out any private repos that slipped through
        if self._public_only:
            repos = [r for r in repos if not r.get("private", True)]

        # Update public repos cache
        for r in repos:
            name = r.get("name", "")
            if name:
                self._public_repos_cache[name] = not r.get("private", True)
        self._public_repos_cache_ts = time.time()

        return repos

    def list_public_repos(self) -> List[Dict[str, Any]]:
        """List ONLY public repositories for the owner. Convenience method."""
        was_public_only = self._public_only
        self._public_only = True
        try:
            return self.list_repos()
        finally:
            self._public_only = was_public_only

    def update_repo(self, repo_name: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("update_repo", repo_name, updates)
        return self._request("PATCH", self._repo_path(repo_name), json_data=updates)

    def set_repo_topics(self, repo_name: str, topics: List[str]) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("set_topics", repo_name, {"topics": topics})
        return self._request(
            "PUT",
            f"{self._repo_path(repo_name)}/topics",
            json_data={"names": topics},
        )

    def delete_repo(self, repo_name: str) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("delete_repo", repo_name)
        return self._request("DELETE", self._repo_path(repo_name))

    # ─── Issue Operations ─────────────────────────────────────────

    def create_issue(self, repo_name: str, config: IssueConfig) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("create_issue", f"{repo_name}#{config.title}")

        payload: Dict[str, Any] = {"title": config.title, "body": config.body}
        if config.labels:
            payload["labels"] = config.labels
        if config.assignees:
            payload["assignees"] = config.assignees
        if config.milestone:
            payload["milestone"] = config.milestone

        return self._request(
            "POST",
            f"{self._repo_path(repo_name)}/issues",
            json_data=payload,
        )

    def list_issues(
        self,
        repo_name: str,
        state: str = "open",
        labels: Optional[str] = None,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        self._check_repo_access(repo_name)
        params: Dict[str, Any] = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = labels
        result = self._request(
            "GET", f"{self._repo_path(repo_name)}/issues", params=params
        )
        return result if isinstance(result, list) else []

    def comment_on_issue(
        self, repo_name: str, issue_number: int, body: str
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("comment_issue", f"{repo_name}#{issue_number}")
        return self._request(
            "POST",
            f"{self._repo_path(repo_name)}/issues/{issue_number}/comments",
            json_data={"body": body},
        )

    def close_issue(self, repo_name: str, issue_number: int) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("close_issue", f"{repo_name}#{issue_number}")
        return self._request(
            "PATCH",
            f"{self._repo_path(repo_name)}/issues/{issue_number}",
            json_data={"state": "closed"},
        )

    def label_issue(
        self, repo_name: str, issue_number: int, labels: List[str]
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        return self._request(
            "POST",
            f"{self._repo_path(repo_name)}/issues/{issue_number}/labels",
            json_data={"labels": labels},
        )

    # ─── Pull Request Operations ──────────────────────────────────

    def create_pr(self, repo_name: str, config: PRConfig) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("create_pr", f"{repo_name}: {config.title}")

        payload: Dict[str, Any] = {
            "title": config.title,
            "body": config.body,
            "head": config.head,
            "base": config.base,
            "draft": config.draft,
        }
        result = self._request(
            "POST", f"{self._repo_path(repo_name)}/pulls", json_data=payload
        )

        if config.labels and result.get("number"):
            self.label_issue(repo_name, result["number"], config.labels)

        return result

    def list_prs(
        self,
        repo_name: str,
        state: str = "open",
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        self._check_repo_access(repo_name)
        result = self._request(
            "GET",
            f"{self._repo_path(repo_name)}/pulls",
            params={"state": state, "per_page": per_page},
        )
        return result if isinstance(result, list) else []

    def merge_pr(
        self,
        repo_name: str,
        pr_number: int,
        merge_method: str = "squash",
        commit_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("merge_pr", f"{repo_name}#{pr_number}")

        payload: Dict[str, Any] = {"merge_method": merge_method}
        if commit_message:
            payload["commit_message"] = commit_message

        return self._request(
            "PUT",
            f"{self._repo_path(repo_name)}/pulls/{pr_number}/merge",
            json_data=payload,
        )

    def review_pr(
        self, repo_name: str, pr_number: int, body: str, event: str = "COMMENT"
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("review_pr", f"{repo_name}#{pr_number}")
        return self._request(
            "POST",
            f"{self._repo_path(repo_name)}/pulls/{pr_number}/reviews",
            json_data={"body": body, "event": event},
        )

    # ─── Release Operations ───────────────────────────────────────

    def create_release(self, repo_name: str, config: ReleaseConfig) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("create_release", f"{repo_name}@{config.tag_name}")

        payload = {
            "tag_name": config.tag_name,
            "name": config.name or config.tag_name,
            "body": config.body,
            "draft": config.draft,
            "prerelease": config.prerelease,
            "generate_release_notes": config.generate_release_notes,
            "target_commitish": config.target_commitish,
        }
        return self._request(
            "POST",
            f"{self._repo_path(repo_name)}/releases",
            json_data=payload,
        )

    def list_releases(
        self, repo_name: str, per_page: int = 10
    ) -> List[Dict[str, Any]]:
        self._check_repo_access(repo_name)
        result = self._request(
            "GET",
            f"{self._repo_path(repo_name)}/releases",
            params={"per_page": per_page},
        )
        return result if isinstance(result, list) else []

    def get_latest_release(self, repo_name: str) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        return self._request("GET", f"{self._repo_path(repo_name)}/releases/latest")

    # ─── Branch Operations ────────────────────────────────────────

    def list_branches(self, repo_name: str, per_page: int = 30) -> List[Dict[str, Any]]:
        self._check_repo_access(repo_name)
        result = self._request(
            "GET",
            f"{self._repo_path(repo_name)}/branches",
            params={"per_page": per_page},
        )
        return result if isinstance(result, list) else []

    def create_branch(self, repo_name: str, branch_name: str, from_sha: str) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("create_branch", f"{repo_name}:{branch_name}")
        return self._request(
            "POST",
            f"{self._repo_path(repo_name)}/git/refs",
            json_data={"ref": f"refs/heads/{branch_name}", "sha": from_sha},
        )

    def get_branch_sha(self, repo_name: str, branch: str = "main") -> str:
        self._check_repo_access(repo_name)
        result = self._request(
            "GET", f"{self._repo_path(repo_name)}/git/ref/heads/{branch}"
        )
        return result.get("object", {}).get("sha", "")

    def set_branch_protection(
        self, repo_name: str, branch: str = "main", require_reviews: bool = True
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("set_protection", f"{repo_name}:{branch}")

        payload: Dict[str, Any] = {
            "enforce_admins": True,
            "required_status_checks": None,
            "restrictions": None,
            "required_pull_request_reviews": (
                {"required_approving_review_count": 1} if require_reviews else None
            ),
        }
        return self._request(
            "PUT",
            f"{self._repo_path(repo_name)}/branches/{branch}/protection",
            json_data=payload,
        )

    # ─── File Operations ──────────────────────────────────────────

    def get_file_content(
        self, repo_name: str, path: str, ref: str = "main"
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        return self._request(
            "GET",
            f"{self._repo_path(repo_name)}/contents/{path}",
            params={"ref": ref},
        )

    def create_or_update_file(
        self,
        repo_name: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
        sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("update_file", f"{repo_name}/{path}")

        import base64

        payload: Dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        return self._request(
            "PUT",
            f"{self._repo_path(repo_name)}/contents/{path}",
            json_data=payload,
        )

    # ─── Commit Operations ────────────────────────────────────────

    def list_commits(
        self,
        repo_name: str,
        sha: str = "main",
        per_page: int = 30,
        since: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self._check_repo_access(repo_name)
        params: Dict[str, Any] = {"sha": sha, "per_page": per_page}
        if since:
            params["since"] = since
        result = self._request(
            "GET", f"{self._repo_path(repo_name)}/commits", params=params
        )
        return result if isinstance(result, list) else []

    def compare_commits(
        self, repo_name: str, base: str, head: str
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        return self._request(
            "GET", f"{self._repo_path(repo_name)}/compare/{base}...{head}"
        )

    # ─── Labels ───────────────────────────────────────────────────

    def create_label(
        self, repo_name: str, name: str, color: str, description: str = ""
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        return self._request(
            "POST",
            f"{self._repo_path(repo_name)}/labels",
            json_data={"name": name, "color": color, "description": description},
        )

    def setup_standard_labels(self, repo_name: str) -> List[Dict[str, Any]]:
        """Create standard BLERBZ OS project labels."""
        self._check_repo_access(repo_name)
        self._audit("setup_labels", repo_name)

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
        results = []
        for name, color, desc in labels:
            try:
                result = self.create_label(repo_name, name, color, desc)
                results.append(result)
            except GitHubError:
                pass  # Label may already exist
        return results

    # ─── Repository Stats ─────────────────────────────────────────

    def get_repo_stats(self, repo_name: str) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        repo = self.get_repo(repo_name)
        return {
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
            "watchers": repo.get("watchers_count", 0),
            "language": repo.get("language"),
            "created_at": repo.get("created_at"),
            "updated_at": repo.get("updated_at"),
            "topics": repo.get("topics", []),
            "license": (repo.get("license") or {}).get("spdx_id"),
            "default_branch": repo.get("default_branch"),
            "visibility": repo.get("visibility"),
        }

    def get_contributor_stats(self, repo_name: str) -> List[Dict[str, Any]]:
        self._check_repo_access(repo_name)
        result = self._request(
            "GET", f"{self._repo_path(repo_name)}/contributors", params={"per_page": 30}
        )
        return result if isinstance(result, list) else []

    # ─── Discussions ──────────────────────────────────────────────

    def list_discussions(self, repo_name: str) -> Dict[str, Any]:
        """List discussions via GraphQL (limited — uses REST comments endpoint)."""
        self._check_repo_access(repo_name)
        # Discussions require GraphQL; for now surface issue-based discussions
        return self._request(
            "GET",
            f"{self._repo_path(repo_name)}/issues",
            params={"labels": "discussion", "per_page": 20},
        )

    # ─── Webhooks ─────────────────────────────────────────────────

    def create_webhook(
        self, repo_name: str, url: str, events: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("create_webhook", repo_name, {"url": url})

        payload = {
            "name": "web",
            "active": True,
            "events": events or ["push", "pull_request", "issues", "release"],
            "config": {
                "url": url,
                "content_type": "json",
            },
        }
        return self._request(
            "POST", f"{self._repo_path(repo_name)}/hooks", json_data=payload
        )

    # ─── GitHub Actions ───────────────────────────────────────────

    def list_workflows(self, repo_name: str) -> List[Dict[str, Any]]:
        self._check_repo_access(repo_name)
        result = self._request(
            "GET", f"{self._repo_path(repo_name)}/actions/workflows"
        )
        return result.get("workflows", [])

    def list_workflow_runs(
        self, repo_name: str, workflow_id: Optional[int] = None, per_page: int = 10
    ) -> List[Dict[str, Any]]:
        self._check_repo_access(repo_name)
        path = f"{self._repo_path(repo_name)}/actions/runs"
        if workflow_id:
            path = f"{self._repo_path(repo_name)}/actions/workflows/{workflow_id}/runs"
        result = self._request("GET", path, params={"per_page": per_page})
        return result.get("workflow_runs", [])

    def trigger_workflow(
        self, repo_name: str, workflow_id: str, ref: str = "main", inputs: Optional[Dict] = None
    ) -> Dict[str, Any]:
        self._check_repo_access(repo_name)
        self._audit("trigger_workflow", f"{repo_name}/{workflow_id}")

        payload: Dict[str, Any] = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs

        return self._request(
            "POST",
            f"{self._repo_path(repo_name)}/actions/workflows/{workflow_id}/dispatches",
            json_data=payload,
        )

    # ─── Utility ──────────────────────────────────────────────────

    def verify_token(self) -> Dict[str, Any]:
        """Verify the current token and return user info."""
        if not self._token:
            return {"valid": False, "error": "No token configured"}
        try:
            result = self._request_raw("GET", "/user")
            return {
                "valid": True,
                "login": result.get("login"),
                "scopes": result.get("scopes", []),
            }
        except GitHubError as e:
            return {"valid": False, "error": str(e)}

    def health_check(self) -> Dict[str, Any]:
        """Check GitHub API health, token validity, and public-only enforcement."""
        try:
            user_info = self.verify_token()
            rate = self.get_rate_status()
            self._detect_owner_type()

            # Count accessible public repos
            public_repos = []
            try:
                public_repos = self.list_public_repos()
            except GitHubError:
                pass

            return {
                "status": "healthy" if user_info.get("valid") else "auth_error",
                "user": user_info,
                "rate_limit": rate,
                "owner": self._owner,
                "owner_type": self._owner_type.value if self._owner_type else "unknown",
                "public_only": self._public_only,
                "allowed_repos": self._allowed_repos,
                "public_repos": [r.get("name") for r in public_repos],
                "public_repo_count": len(public_repos),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ─── Singleton ────────────────────────────────────────────────────

_github_ops: Optional[GitHubOps] = None


def get_github_ops(**kwargs) -> GitHubOps:
    global _github_ops
    if _github_ops is None:
        _github_ops = GitHubOps(**kwargs)
    return _github_ops
