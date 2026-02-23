"""
Kait Release Pipeline — Automated release management for OS projects

Handles the complete release workflow:
- Semantic versioning (SemVer) management
- Automated changelog generation from commits/PRs
- GitHub Release creation with notes
- Tag management and validation
- Release notes generation (human-readable)
- Social media / marketing draft generation

Usage:
    from lib.release_pipeline import ReleasePipeline
    pipeline = ReleasePipeline()
    pipeline.prepare_release("robin", "minor")
    pipeline.execute_release("robin", "0.2.0")
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
from typing import Any, Dict, List, Optional, Tuple

from lib.diagnostics import log_debug
from lib.github_ops import (
    GitHubOps,
    GitHubError,
    ReleaseConfig,
    get_github_ops,
)

# ============= Configuration =============

KAIT_DIR = Path.home() / ".kait"
RELEASES_DIR = KAIT_DIR / "releases"
RELEASES_LOG = RELEASES_DIR / "release_log.jsonl"

# SemVer regex
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([\w.]+))?(?:\+([\w.]+))?$")

BLERBZ_ORG = os.environ.get("KAIT_GITHUB_OWNER", "") or os.environ.get("KAIT_GITHUB_ORG", "BLERBZ")
BLERBZ_NAME = os.environ.get("KAIT_BLERBZ_NAME", "BLERBZ LLC")


class BumpType(str, Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    PRERELEASE = "prerelease"


class ReleaseStatus(str, Enum):
    PREPARING = "preparing"
    READY = "ready"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class SemVer:
    """Semantic version representation."""

    major: int = 0
    minor: int = 0
    patch: int = 0
    prerelease: str = ""
    build: str = ""

    def __str__(self) -> str:
        v = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            v += f"-{self.prerelease}"
        if self.build:
            v += f"+{self.build}"
        return v

    @staticmethod
    def parse(version: str) -> "SemVer":
        version = version.lstrip("v")
        match = SEMVER_RE.match(version)
        if not match:
            raise ValueError(f"Invalid SemVer: {version}")
        return SemVer(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4) or "",
            build=match.group(5) or "",
        )

    def bump(self, bump_type: BumpType) -> "SemVer":
        if bump_type == BumpType.MAJOR:
            return SemVer(self.major + 1, 0, 0)
        elif bump_type == BumpType.MINOR:
            return SemVer(self.major, self.minor + 1, 0)
        elif bump_type == BumpType.PATCH:
            return SemVer(self.major, self.minor, self.patch + 1)
        elif bump_type == BumpType.PRERELEASE:
            pre = self.prerelease
            if pre:
                # Increment prerelease number
                parts = pre.rsplit(".", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    pre = f"{parts[0]}.{int(parts[1]) + 1}"
                else:
                    pre = f"{pre}.1"
            else:
                pre = "rc.1"
            return SemVer(self.major, self.minor, self.patch + 1, prerelease=pre)
        return self

    def tag_name(self) -> str:
        return f"v{self}"


@dataclass
class CommitInfo:
    """Parsed commit information."""

    sha: str
    message: str
    author: str
    date: str
    category: str = "other"  # fix, feat, docs, refactor, test, chore, other

    @staticmethod
    def categorize(message: str) -> str:
        msg_lower = message.lower()
        if msg_lower.startswith(("fix:", "fix(", "bugfix:")):
            return "fix"
        elif msg_lower.startswith(("feat:", "feat(", "add:", "feature:")):
            return "feat"
        elif msg_lower.startswith(("docs:", "doc:")):
            return "docs"
        elif msg_lower.startswith(("refactor:", "refactor(")):
            return "refactor"
        elif msg_lower.startswith(("test:", "tests:")):
            return "test"
        elif msg_lower.startswith(("chore:", "ci:", "build:")):
            return "chore"
        # Heuristic fallback
        if "fix" in msg_lower or "bug" in msg_lower:
            return "fix"
        elif "add" in msg_lower or "new" in msg_lower or "feature" in msg_lower:
            return "feat"
        return "other"


@dataclass
class ReleasePrep:
    """Prepared release data before execution."""

    project_slug: str
    current_version: SemVer
    next_version: SemVer
    commits: List[CommitInfo] = field(default_factory=list)
    changelog_entry: str = ""
    release_notes: str = ""
    status: ReleaseStatus = ReleaseStatus.PREPARING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_slug": self.project_slug,
            "current_version": str(self.current_version),
            "next_version": str(self.next_version),
            "commit_count": len(self.commits),
            "changelog_entry": self.changelog_entry,
            "release_notes": self.release_notes,
            "status": self.status.value,
        }


class ReleasePipeline:
    """Manages the complete release workflow for BLERBZ OS projects."""

    def __init__(self, github: Optional[GitHubOps] = None):
        self._gh = github or get_github_ops()
        RELEASES_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Version Management ───────────────────────────────────────

    def get_current_version(self, repo_name: str) -> SemVer:
        """Get current version from latest release tag."""
        try:
            releases = self._gh.list_releases(repo_name, per_page=1)
            if releases:
                tag = releases[0].get("tag_name", "v0.0.0")
                return SemVer.parse(tag)
        except GitHubError:
            pass
        return SemVer(0, 0, 0)

    def calculate_next_version(
        self, current: SemVer, bump_type: BumpType
    ) -> SemVer:
        return current.bump(bump_type)

    def auto_detect_bump(self, commits: List[CommitInfo]) -> BumpType:
        """Auto-detect bump type from commit messages."""
        has_breaking = any("breaking" in c.message.lower() for c in commits)
        has_feat = any(c.category == "feat" for c in commits)
        has_fix = any(c.category == "fix" for c in commits)

        if has_breaking:
            return BumpType.MAJOR
        elif has_feat:
            return BumpType.MINOR
        elif has_fix:
            return BumpType.PATCH
        return BumpType.PATCH

    # ─── Changelog Generation ─────────────────────────────────────

    def _fetch_commits_since_release(
        self, repo_name: str, since_tag: Optional[str] = None
    ) -> List[CommitInfo]:
        """Fetch commits since the last release."""
        try:
            if since_tag:
                # Compare from tag to HEAD
                result = self._gh.compare_commits(repo_name, since_tag, "main")
                raw_commits = result.get("commits", [])
            else:
                raw_commits = self._gh.list_commits(repo_name, per_page=50)

            commits = []
            for c in raw_commits:
                msg = c.get("commit", {}).get("message", "").split("\n")[0]
                commits.append(CommitInfo(
                    sha=c.get("sha", "")[:8],
                    message=msg,
                    author=c.get("commit", {}).get("author", {}).get("name", "Unknown"),
                    date=c.get("commit", {}).get("author", {}).get("date", ""),
                    category=CommitInfo.categorize(msg),
                ))
            return commits
        except GitHubError:
            return []

    def generate_changelog_entry(
        self, version: SemVer, commits: List[CommitInfo]
    ) -> str:
        """Generate a changelog entry from commits."""
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        sections: Dict[str, List[str]] = {
            "Added": [],
            "Fixed": [],
            "Changed": [],
            "Documentation": [],
            "Other": [],
        }

        for c in commits:
            entry = f"- {c.message} ({c.sha})"
            if c.category == "feat":
                sections["Added"].append(entry)
            elif c.category == "fix":
                sections["Fixed"].append(entry)
            elif c.category == "refactor":
                sections["Changed"].append(entry)
            elif c.category == "docs":
                sections["Documentation"].append(entry)
            else:
                sections["Other"].append(entry)

        lines = [f"## [{version}] - {date}\n"]
        for section, entries in sections.items():
            if entries:
                lines.append(f"### {section}\n")
                lines.extend(entries)
                lines.append("")

        return "\n".join(lines)

    def generate_release_notes(
        self, project_name: str, version: SemVer, commits: List[CommitInfo]
    ) -> str:
        """Generate human-readable release notes."""
        date = datetime.now(timezone.utc).strftime("%B %d, %Y")

        features = [c for c in commits if c.category == "feat"]
        fixes = [c for c in commits if c.category == "fix"]
        others = [c for c in commits if c.category not in ("feat", "fix")]

        lines = [
            f"# {project_name} v{version}",
            f"",
            f"Released on {date} by {BLERBZ_NAME}",
            f"",
        ]

        if features:
            lines.append("## New Features\n")
            for f in features:
                lines.append(f"- {f.message}")
            lines.append("")

        if fixes:
            lines.append("## Bug Fixes\n")
            for f in fixes:
                lines.append(f"- {f.message}")
            lines.append("")

        if others:
            lines.append("## Other Changes\n")
            for o in others:
                lines.append(f"- {o.message}")
            lines.append("")

        lines.extend([
            "---",
            f"Full changelog: https://github.com/{BLERBZ_ORG}/{project_name}/compare/"
            f"v{version.major}.{version.minor}.{version.patch - 1 if version.patch > 0 else 0}...v{version}",
            "",
            f"Managed by [Kait OS Sidekick](https://github.com/{BLERBZ_ORG}/kait-intel)",
        ])

        return "\n".join(lines)

    # ─── Release Workflow ─────────────────────────────────────────

    def prepare_release(
        self,
        repo_name: str,
        bump_type: Optional[BumpType] = None,
    ) -> ReleasePrep:
        """Prepare a release (gather commits, generate changelog, etc.)."""

        current = self.get_current_version(repo_name)
        current_tag = current.tag_name() if str(current) != "0.0.0" else None

        # Fetch commits since last release
        commits = self._fetch_commits_since_release(repo_name, current_tag)

        # Auto-detect bump type if not specified
        if bump_type is None:
            bump_type = self.auto_detect_bump(commits)

        next_version = self.calculate_next_version(current, bump_type)

        # Generate changelog and release notes
        changelog = self.generate_changelog_entry(next_version, commits)
        notes = self.generate_release_notes(repo_name, next_version, commits)

        prep = ReleasePrep(
            project_slug=repo_name,
            current_version=current,
            next_version=next_version,
            commits=commits,
            changelog_entry=changelog,
            release_notes=notes,
            status=ReleaseStatus.READY,
        )

        log_debug(
            "release_pipeline",
            f"Prepared {repo_name} v{current} → v{next_version} ({len(commits)} commits)",
        )

        return prep

    def execute_release(self, prep: ReleasePrep) -> Dict[str, Any]:
        """Execute a prepared release."""
        repo = prep.project_slug
        version = prep.next_version

        log_debug("release_pipeline", f"Executing release {repo} v{version}")

        results: Dict[str, Any] = {
            "version": str(version),
            "tag": version.tag_name(),
            "steps": {},
        }

        # Step 1: Update CHANGELOG.md
        try:
            existing = self._gh.get_file_content(repo, "CHANGELOG.md")
            current_content = ""
            if existing.get("content"):
                import base64
                current_content = base64.b64decode(existing["content"]).decode()

            # Insert new entry after the header
            header_end = current_content.find("\n## ")
            if header_end == -1:
                header_end = len(current_content)

            new_content = (
                current_content[:header_end]
                + "\n"
                + prep.changelog_entry
                + "\n"
                + current_content[header_end:]
            )

            self._gh.create_or_update_file(
                repo,
                "CHANGELOG.md",
                new_content,
                f"Release v{version} — update changelog",
                sha=existing.get("sha"),
            )
            results["steps"]["changelog"] = "updated"
        except GitHubError as e:
            results["steps"]["changelog"] = f"failed: {e}"

        # Step 2: Create GitHub Release
        try:
            release_config = ReleaseConfig(
                tag_name=version.tag_name(),
                name=f"v{version}",
                body=prep.release_notes,
                draft=False,
                prerelease=bool(version.prerelease),
                generate_release_notes=True,
            )
            release_result = self._gh.create_release(repo, release_config)
            results["steps"]["github_release"] = "created"
            results["release_url"] = release_result.get("html_url", "")
        except GitHubError as e:
            results["steps"]["github_release"] = f"failed: {e}"
            prep.status = ReleaseStatus.FAILED

        # Step 3: Log the release
        self._log_release(prep, results)

        if prep.status != ReleaseStatus.FAILED:
            prep.status = ReleaseStatus.PUBLISHED
            results["status"] = "published"
        else:
            results["status"] = "failed"

        return results

    def _log_release(self, prep: ReleasePrep, results: Dict[str, Any]):
        """Log release to audit trail."""
        entry = {
            "ts": time.time(),
            "project": prep.project_slug,
            "version": str(prep.next_version),
            "from_version": str(prep.current_version),
            "commits": len(prep.commits),
            "status": prep.status.value,
            "results": results,
        }
        try:
            with open(RELEASES_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    # ─── Marketing Drafts ─────────────────────────────────────────

    def generate_announcement(self, prep: ReleasePrep) -> Dict[str, str]:
        """Generate release announcement drafts for various channels."""
        name = prep.project_slug
        version = prep.next_version
        features = [c for c in prep.commits if c.category == "feat"]
        fixes = [c for c in prep.commits if c.category == "fix"]

        feature_list = "\n".join(f"  - {f.message}" for f in features[:5])
        fix_list = "\n".join(f"  - {f.message}" for f in fixes[:5])

        # GitHub Discussion / Blog post
        blog = f"""# {name} v{version} is here!

We're excited to announce the release of {name} v{version}!

"""
        if features:
            blog += f"## What's New\n\n{feature_list}\n\n"
        if fixes:
            blog += f"## Bug Fixes\n\n{fix_list}\n\n"
        blog += f"""## Get Started

```bash
pip install {name}=={version}
```

Check out the [full changelog](https://github.com/{BLERBZ_ORG}/{name}/releases/tag/v{version}).

Built by {BLERBZ_NAME} | Managed by Kait OS Sidekick
"""

        # Twitter/X post
        top_feature = features[0].message if features else f"improvements and fixes"
        twitter = (
            f"Announcing {name} v{version}! "
            f"{top_feature}. "
            f"Check it out: https://github.com/{BLERBZ_ORG}/{name}/releases/tag/v{version} "
            f"#OpenSource #BLERBZ"
        )

        # Short summary
        summary = (
            f"{name} v{version}: "
            f"{len(features)} new feature(s), {len(fixes)} fix(es), "
            f"{len(prep.commits)} total commits"
        )

        return {
            "blog": blog,
            "twitter": twitter,
            "summary": summary,
            "release_notes": prep.release_notes,
        }

    # ─── Release History ──────────────────────────────────────────

    def get_release_history(self, repo_name: str) -> List[Dict[str, Any]]:
        """Get release history from GitHub."""
        try:
            releases = self._gh.list_releases(repo_name, per_page=20)
            return [
                {
                    "tag": r.get("tag_name"),
                    "name": r.get("name"),
                    "published_at": r.get("published_at"),
                    "prerelease": r.get("prerelease"),
                    "url": r.get("html_url"),
                }
                for r in releases
            ]
        except GitHubError:
            return []


# ─── Singleton ────────────────────────────────────────────────────

_release_pipeline: Optional[ReleasePipeline] = None


def get_release_pipeline(**kwargs) -> ReleasePipeline:
    global _release_pipeline
    if _release_pipeline is None:
        _release_pipeline = ReleasePipeline(**kwargs)
    return _release_pipeline
