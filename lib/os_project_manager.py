"""
Kait OS Project Manager — Full lifecycle management for open-source projects

Manages the complete lifecycle of BLERBZ open-source projects:
- Project creation with standard scaffolding
- Development tracking and code review workflows
- Maintenance: dependency updates, security audits
- Community health files and standards enforcement
- Project viability assessment

Usage:
    from lib.os_project_manager import OSProjectManager
    mgr = OSProjectManager()
    mgr.create_project("robin", description="BLERBZ OS Sidekick")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.diagnostics import log_debug
from lib.github_ops import (
    GitHubOps,
    GitHubError,
    RepoConfig,
    RepoVisibility,
    IssueConfig,
    ReleaseConfig,
    get_github_ops,
)

# ============= Configuration =============

KAIT_DIR = Path.home() / ".kait"
OS_PROJECTS_DIR = KAIT_DIR / "os_projects"
OS_PROJECTS_STATE = OS_PROJECTS_DIR / "projects.json"

# BLERBZ Standards
BLERBZ_LICENSE = os.environ.get("KAIT_BLERBZ_LICENSE", "MIT")
BLERBZ_ORG = os.environ.get("KAIT_GITHUB_OWNER", "") or os.environ.get("KAIT_GITHUB_ORG", "BLERBZ")
BLERBZ_URL = os.environ.get("KAIT_BLERBZ_URL", "https://blerbz.com")
BLERBZ_NAME = os.environ.get("KAIT_BLERBZ_NAME", "BLERBZ LLC")


class ProjectPhase(str, Enum):
    PLANNING = "planning"
    DEVELOPMENT = "development"
    TESTING = "testing"
    RELEASE = "release"
    MAINTENANCE = "maintenance"
    ARCHIVED = "archived"


class ProjectHealth(str, Enum):
    HEALTHY = "healthy"
    NEEDS_ATTENTION = "needs_attention"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ProjectState:
    """Track the state of an OS project."""

    name: str
    slug: str
    description: str = ""
    phase: ProjectPhase = ProjectPhase.PLANNING
    health: ProjectHealth = ProjectHealth.UNKNOWN
    created_at: float = 0.0
    updated_at: float = 0.0
    current_version: str = "0.0.0"
    repo_url: str = ""
    tech_stack: List[str] = field(default_factory=list)
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "phase": self.phase.value,
            "health": self.health.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_version": self.current_version,
            "repo_url": self.repo_url,
            "tech_stack": self.tech_stack,
            "milestones": self.milestones,
            "metrics": self.metrics,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ProjectState":
        return ProjectState(
            name=d.get("name", ""),
            slug=d.get("slug", ""),
            description=d.get("description", ""),
            phase=ProjectPhase(d.get("phase", "planning")),
            health=ProjectHealth(d.get("health", "unknown")),
            created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0),
            current_version=d.get("current_version", "0.0.0"),
            repo_url=d.get("repo_url", ""),
            tech_stack=d.get("tech_stack", []),
            milestones=d.get("milestones", []),
            metrics=d.get("metrics", {}),
        )


# ─── Templates ────────────────────────────────────────────────────

def _readme_template(name: str, description: str, slug: str) -> str:
    return f"""# {name}

{description}

[![License: {BLERBZ_LICENSE}](https://img.shields.io/badge/License-{BLERBZ_LICENSE}-yellow.svg)](LICENSE)
[![BLERBZ OS](https://img.shields.io/badge/BLERBZ-Open%20Source-blue.svg)]({BLERBZ_URL})
[![Managed by Kait](https://img.shields.io/badge/Managed%20by-Kait%20OS%20Sidekick-green.svg)](https://github.com/{BLERBZ_ORG}/kait-intel)

## Overview

{name} is an open-source project by [{BLERBZ_NAME}]({BLERBZ_URL}), managed by Kait OS Sidekick.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/{BLERBZ_ORG}/{slug}.git
cd {slug}

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## Features

- Feature list coming soon

## Documentation

- [Contributing Guide](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

This project is licensed under the {BLERBZ_LICENSE} License — see the [LICENSE](LICENSE) file for details.

## About {BLERBZ_NAME}

Built with care by [{BLERBZ_NAME}]({BLERBZ_URL}). Managed by [Kait OS Sidekick](https://github.com/{BLERBZ_ORG}/kait-intel).
"""


def _contributing_template(name: str, slug: str) -> str:
    return f"""# Contributing to {name}

Thank you for your interest in contributing to {name}! This document provides
guidelines and instructions for contributing.

## Code of Conduct

This project adheres to our [Code of Conduct](CODE_OF_CONDUCT.md). By participating,
you are expected to uphold this code.

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Use the bug report template when creating a new issue
3. Include steps to reproduce, expected behavior, and actual behavior

### Suggesting Enhancements

1. Check existing issues and discussions first
2. Use the feature request template
3. Describe the problem you're trying to solve

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes following our coding standards
4. Write or update tests as needed
5. Run the test suite: `pytest`
6. Commit with clear messages: `git commit -m "Add: your feature description"`
7. Push and create a Pull Request

### Commit Message Format

We follow conventional commits:

- `Add:` New feature
- `Fix:` Bug fix
- `Docs:` Documentation changes
- `Refactor:` Code refactoring
- `Test:` Adding or updating tests
- `Chore:` Maintenance tasks

### Coding Standards

- Follow PEP 8 for Python code
- Use type hints where possible
- Write docstrings for public functions
- Keep functions focused and small
- Write tests for new functionality

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/{slug}.git
cd {slug}

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .
```

## Review Process

1. All PRs require at least one review
2. CI checks must pass
3. Code coverage should not decrease
4. Documentation must be updated if applicable

## Questions?

Open a discussion or reach out to the maintainers.

Thank you for helping make {name} better!
"""


def _code_of_conduct_template() -> str:
    return """# Contributor Covenant Code of Conduct

## Our Pledge

We as members, contributors, and leaders pledge to make participation in our
community a harassment-free experience for everyone, regardless of age, body size,
visible or invisible disability, ethnicity, sex characteristics, gender identity
and expression, level of experience, education, socio-economic status, nationality,
personal appearance, race, religion, or sexual identity and orientation.

## Our Standards

Examples of behavior that contributes to a positive environment:

* Using welcoming and inclusive language
* Being respectful of differing viewpoints and experiences
* Gracefully accepting constructive criticism
* Focusing on what is best for the community
* Showing empathy towards other community members

Examples of unacceptable behavior:

* The use of sexualized language or imagery and unwelcome sexual attention
* Trolling, insulting/derogatory comments, and personal or political attacks
* Public or private harassment
* Publishing others' private information without explicit permission
* Other conduct which could reasonably be considered inappropriate

## Enforcement

Instances of abusive, harassing, or otherwise unacceptable behavior may be
reported to the project team. All complaints will be reviewed and investigated.

## Attribution

This Code of Conduct is adapted from the [Contributor Covenant](https://www.contributor-covenant.org),
version 2.1.
"""


def _changelog_template(name: str) -> str:
    return f"""# Changelog

All notable changes to {name} will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project setup
- README, CONTRIBUTING, CODE_OF_CONDUCT

## [0.1.0] - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

### Added
- Initial release
- Project scaffolding by Kait OS Sidekick
"""


def _security_template(slug: str) -> str:
    return f"""# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email security concerns to the maintainers
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Security Updates

Security updates are released as patch versions and announced in GitHub releases.
"""


def _gitignore_python() -> str:
    return """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg-info/
dist/
build/
.eggs/

# Virtual environments
.venv/
venv/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Environment
.env
.env.local

# Testing
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/

# Kait state
.kait/
"""


# ─── Project Manager ─────────────────────────────────────────────


class OSProjectManager:
    """Manages the full lifecycle of BLERBZ open-source projects."""

    def __init__(self, github: Optional[GitHubOps] = None):
        self._gh = github or get_github_ops()
        OS_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        self._projects: Dict[str, ProjectState] = self._load_projects()

    def _load_projects(self) -> Dict[str, ProjectState]:
        if not OS_PROJECTS_STATE.exists():
            return {}
        try:
            data = json.loads(OS_PROJECTS_STATE.read_text())
            return {
                k: ProjectState.from_dict(v)
                for k, v in data.items()
            }
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_projects(self):
        data = {k: v.to_dict() for k, v in self._projects.items()}
        OS_PROJECTS_STATE.write_text(json.dumps(data, indent=2))

    def _update_project(self, slug: str, **kwargs):
        if slug in self._projects:
            for k, v in kwargs.items():
                if hasattr(self._projects[slug], k):
                    setattr(self._projects[slug], k, v)
            self._projects[slug].updated_at = time.time()
            self._save_projects()

    # ─── Project Creation ─────────────────────────────────────────

    def create_project(
        self,
        slug: str,
        name: Optional[str] = None,
        description: str = "",
        tech_stack: Optional[List[str]] = None,
        visibility: RepoVisibility = RepoVisibility.PUBLIC,
        topics: Optional[List[str]] = None,
    ) -> ProjectState:
        """Create a new OS project with full scaffolding."""

        name = name or slug.replace("-", " ").title()
        now = time.time()

        log_debug("os_project_manager", f"Creating project {slug}")

        # Create GitHub repo
        repo_config = RepoConfig(
            name=slug,
            description=description or f"{name} — A BLERBZ open-source project",
            visibility=visibility,
            license_template=BLERBZ_LICENSE.lower(),
            has_issues=True,
            has_discussions=True,
            auto_init=True,
            gitignore_template="Python",
            topics=topics or ["blerbz", "open-source", "kait-managed"],
        )

        try:
            repo_result = self._gh.create_repo(repo_config)
            repo_url = repo_result.get("html_url", "")
        except GitHubError as e:
            log_debug("os_project_manager", f"GitHub repo creation failed: {e}")
            repo_url = f"https://github.com/{BLERBZ_ORG}/{slug}"

        # Create project state
        project = ProjectState(
            name=name,
            slug=slug,
            description=description,
            phase=ProjectPhase.PLANNING,
            health=ProjectHealth.HEALTHY,
            created_at=now,
            updated_at=now,
            current_version="0.1.0",
            repo_url=repo_url,
            tech_stack=tech_stack or ["python"],
        )

        self._projects[slug] = project
        self._save_projects()

        # Scaffold community health files
        self._scaffold_project(slug, name, description)

        return project

    def _scaffold_project(self, slug: str, name: str, description: str):
        """Create standard community health files in the repo."""

        files = {
            "README.md": _readme_template(name, description, slug),
            "CONTRIBUTING.md": _contributing_template(name, slug),
            "CODE_OF_CONDUCT.md": _code_of_conduct_template(),
            "CHANGELOG.md": _changelog_template(name),
            "SECURITY.md": _security_template(slug),
            ".gitignore": _gitignore_python(),
        }

        for path, content in files.items():
            try:
                # Check if file exists first
                existing = None
                try:
                    existing = self._gh.get_file_content(slug, path)
                except GitHubError:
                    pass

                sha = existing.get("sha") if existing else None
                self._gh.create_or_update_file(
                    slug,
                    path,
                    content,
                    f"Add {path} — scaffolded by Kait OS Sidekick",
                    sha=sha,
                )
            except GitHubError as e:
                log_debug("os_project_manager", f"Failed to create {path}: {e}")

        # Set up labels
        try:
            self._gh.setup_standard_labels(slug)
        except GitHubError:
            pass

    # ─── Project Status ───────────────────────────────────────────

    def get_project(self, slug: str) -> Optional[ProjectState]:
        return self._projects.get(slug)

    def list_projects(self) -> List[ProjectState]:
        return list(self._projects.values())

    def get_project_status(self, slug: str) -> Dict[str, Any]:
        """Get comprehensive project status."""
        project = self._projects.get(slug)
        if not project:
            return {"error": f"Project '{slug}' not found"}

        status: Dict[str, Any] = project.to_dict()

        # Fetch live stats from GitHub
        try:
            stats = self._gh.get_repo_stats(slug)
            status["github_stats"] = stats
        except GitHubError:
            status["github_stats"] = None

        # Fetch open issues count
        try:
            issues = self._gh.list_issues(slug, state="open")
            status["open_issues"] = len(issues)
        except GitHubError:
            status["open_issues"] = None

        # Fetch open PRs
        try:
            prs = self._gh.list_prs(slug, state="open")
            status["open_prs"] = len(prs)
        except GitHubError:
            status["open_prs"] = None

        return status

    # ─── Phase Management ─────────────────────────────────────────

    def advance_phase(self, slug: str) -> Optional[ProjectPhase]:
        """Advance project to next phase."""
        project = self._projects.get(slug)
        if not project:
            return None

        phase_order = [
            ProjectPhase.PLANNING,
            ProjectPhase.DEVELOPMENT,
            ProjectPhase.TESTING,
            ProjectPhase.RELEASE,
            ProjectPhase.MAINTENANCE,
        ]

        try:
            idx = phase_order.index(project.phase)
            if idx < len(phase_order) - 1:
                new_phase = phase_order[idx + 1]
                self._update_project(slug, phase=new_phase)
                log_debug("os_project_manager", f"{slug} advanced to {new_phase.value}")
                return new_phase
        except ValueError:
            pass
        return project.phase

    def set_phase(self, slug: str, phase: ProjectPhase):
        self._update_project(slug, phase=phase)

    # ─── Development Operations ───────────────────────────────────

    def create_feature_branch(self, slug: str, feature_name: str) -> Dict[str, Any]:
        """Create a feature branch for development."""
        branch_name = f"feature/{feature_name}"
        try:
            sha = self._gh.get_branch_sha(slug, "main")
            result = self._gh.create_branch(slug, branch_name, sha)
            return {"branch": branch_name, "sha": sha, "result": result}
        except GitHubError as e:
            return {"error": str(e)}

    def create_feature_issue(
        self, slug: str, title: str, body: str, labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a tracked feature issue."""
        config = IssueConfig(
            title=title,
            body=body,
            labels=labels or ["enhancement", "kait-managed"],
        )
        try:
            return self._gh.create_issue(slug, config)
        except GitHubError as e:
            return {"error": str(e)}

    def create_bug_report(
        self, slug: str, title: str, body: str, severity: str = "normal"
    ) -> Dict[str, Any]:
        """Create a bug report issue."""
        labels = ["bug", "kait-managed"]
        if severity == "critical":
            labels.append("security")

        config = IssueConfig(title=title, body=body, labels=labels)
        try:
            return self._gh.create_issue(slug, config)
        except GitHubError as e:
            return {"error": str(e)}

    # ─── Maintenance ──────────────────────────────────────────────

    def health_check(self, slug: str) -> Dict[str, Any]:
        """Run a health check on a project."""
        project = self._projects.get(slug)
        if not project:
            return {"health": "unknown", "error": "Project not found"}

        checks: Dict[str, Any] = {
            "has_readme": False,
            "has_contributing": False,
            "has_license": False,
            "has_code_of_conduct": False,
            "has_changelog": False,
            "has_security_policy": False,
            "open_issues_count": 0,
            "stale_issues": 0,
            "open_prs_count": 0,
        }

        # Check community health files
        for filename, key in [
            ("README.md", "has_readme"),
            ("CONTRIBUTING.md", "has_contributing"),
            ("LICENSE", "has_license"),
            ("CODE_OF_CONDUCT.md", "has_code_of_conduct"),
            ("CHANGELOG.md", "has_changelog"),
            ("SECURITY.md", "has_security_policy"),
        ]:
            try:
                self._gh.get_file_content(slug, filename)
                checks[key] = True
            except GitHubError:
                pass

        # Check issues
        try:
            issues = self._gh.list_issues(slug, state="open")
            checks["open_issues_count"] = len(issues)
        except GitHubError:
            pass

        # Check PRs
        try:
            prs = self._gh.list_prs(slug, state="open")
            checks["open_prs_count"] = len(prs)
        except GitHubError:
            pass

        # Determine overall health
        health_score = sum([
            checks["has_readme"],
            checks["has_contributing"],
            checks["has_license"],
            checks["has_code_of_conduct"],
            checks["has_changelog"],
            checks["has_security_policy"],
        ])

        if health_score >= 5:
            health = ProjectHealth.HEALTHY
        elif health_score >= 3:
            health = ProjectHealth.NEEDS_ATTENTION
        else:
            health = ProjectHealth.CRITICAL

        self._update_project(slug, health=health)
        checks["health"] = health.value
        checks["score"] = f"{health_score}/6"

        return checks

    # ─── Metrics ──────────────────────────────────────────────────

    def update_metrics(self, slug: str) -> Dict[str, Any]:
        """Fetch and store latest project metrics."""
        try:
            stats = self._gh.get_repo_stats(slug)
            contributors = self._gh.get_contributor_stats(slug)

            metrics = {
                "stars": stats.get("stars", 0),
                "forks": stats.get("forks", 0),
                "open_issues": stats.get("open_issues", 0),
                "watchers": stats.get("watchers", 0),
                "contributors": len(contributors),
                "updated_at": time.time(),
            }

            self._update_project(slug, metrics=metrics)
            return metrics
        except GitHubError as e:
            return {"error": str(e)}

    # ─── Project Assessment ───────────────────────────────────────

    def assess_viability(self, idea: str, tech_stack: Optional[List[str]] = None) -> Dict[str, Any]:
        """Assess the viability of a project idea (heuristic-based)."""
        score = 0
        factors = []

        # Check if idea has clear purpose
        if len(idea) > 20:
            score += 20
            factors.append("Clear description")

        # Check tech stack popularity
        popular_stacks = {"python", "javascript", "typescript", "rust", "go"}
        if tech_stack:
            overlap = set(s.lower() for s in tech_stack) & popular_stacks
            if overlap:
                score += 20
                factors.append(f"Popular tech: {', '.join(overlap)}")

        # Check for problem-solving keywords
        problem_keywords = {"solve", "automate", "simplify", "improve", "optimize", "manage"}
        idea_lower = idea.lower()
        if any(kw in idea_lower for kw in problem_keywords):
            score += 20
            factors.append("Solves a problem")

        # Check for market keywords
        market_keywords = {"open source", "developer", "tool", "library", "framework", "api"}
        if any(kw in idea_lower for kw in market_keywords):
            score += 20
            factors.append("Developer market fit")

        # Check for uniqueness (basic heuristic)
        if len(idea.split()) > 10:
            score += 20
            factors.append("Detailed vision")

        return {
            "score": score,
            "max_score": 100,
            "viability": "high" if score >= 60 else "medium" if score >= 40 else "low",
            "factors": factors,
            "recommendation": (
                "Proceed with project" if score >= 60
                else "Refine the idea" if score >= 40
                else "Needs more development"
            ),
        }


# ─── Singleton ────────────────────────────────────────────────────

_os_project_manager: Optional[OSProjectManager] = None


def get_os_project_manager(**kwargs) -> OSProjectManager:
    global _os_project_manager
    if _os_project_manager is None:
        _os_project_manager = OSProjectManager(**kwargs)
    return _os_project_manager
