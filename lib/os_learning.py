"""
Kait OS Learning Engine — Self-improvement through OS project analysis

Learns from open-source project patterns:
- Analyze project metrics (stars, forks, contributors, issues)
- Extract best practices from successful projects
- Track mastery progression over time
- Benchmark against industry standards
- Integrate feedback loops with cognitive_learner

Usage:
    from lib.os_learning import OSLearningEngine
    engine = OSLearningEngine()
    engine.learn_from_project("robin")
    engine.get_mastery_report()
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.diagnostics import log_debug
from lib.github_ops import GitHubOps, GitHubError, get_github_ops

# ============= Configuration =============

KAIT_DIR = Path.home() / ".kait"
LEARNING_DIR = KAIT_DIR / "os_learning"
METRICS_FILE = LEARNING_DIR / "metrics.jsonl"
INSIGHTS_FILE = LEARNING_DIR / "insights.json"
MASTERY_FILE = LEARNING_DIR / "mastery.json"
BENCHMARKS_FILE = LEARNING_DIR / "benchmarks.json"


class MasteryLevel(str, Enum):
    NOVICE = "novice"
    APPRENTICE = "apprentice"
    COMPETENT = "competent"
    PROFICIENT = "proficient"
    EXPERT = "expert"


class LearningDomain(str, Enum):
    PROJECT_SETUP = "project_setup"
    CODE_QUALITY = "code_quality"
    COMMUNITY = "community"
    RELEASES = "releases"
    DOCUMENTATION = "documentation"
    MAINTENANCE = "maintenance"
    MARKETING = "marketing"


@dataclass
class ProjectMetrics:
    """Snapshot of project metrics at a point in time."""

    project_slug: str
    timestamp: float
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    closed_issues: int = 0
    contributors: int = 0
    watchers: int = 0
    commits_30d: int = 0
    prs_merged_30d: int = 0
    avg_issue_close_time_h: float = 0.0
    has_ci: bool = False
    has_docs: bool = False
    has_contributing: bool = False
    license_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_slug": self.project_slug,
            "timestamp": self.timestamp,
            "stars": self.stars,
            "forks": self.forks,
            "open_issues": self.open_issues,
            "closed_issues": self.closed_issues,
            "contributors": self.contributors,
            "watchers": self.watchers,
            "commits_30d": self.commits_30d,
            "prs_merged_30d": self.prs_merged_30d,
            "avg_issue_close_time_h": self.avg_issue_close_time_h,
            "has_ci": self.has_ci,
            "has_docs": self.has_docs,
            "has_contributing": self.has_contributing,
            "license_type": self.license_type,
        }


@dataclass
class OSInsight:
    """A learning insight from OS project analysis."""

    domain: LearningDomain
    title: str
    description: str
    source_project: str = ""
    confidence: float = 0.0
    created_at: float = 0.0
    validated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain.value,
            "title": self.title,
            "description": self.description,
            "source_project": self.source_project,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "validated": self.validated,
        }


@dataclass
class DomainMastery:
    """Mastery state for a learning domain."""

    domain: LearningDomain
    level: MasteryLevel = MasteryLevel.NOVICE
    score: int = 0
    max_score: int = 100
    actions_completed: int = 0
    insights_applied: int = 0
    last_activity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain.value,
            "level": self.level.value,
            "score": self.score,
            "max_score": self.max_score,
            "actions_completed": self.actions_completed,
            "insights_applied": self.insights_applied,
            "last_activity": self.last_activity,
        }


# ─── Benchmarks ───────────────────────────────────────────────────

# Based on analysis of successful OS projects
OS_BENCHMARKS = {
    "small_project": {  # <100 stars
        "min_docs_files": 3,  # README, CONTRIBUTING, LICENSE
        "response_time_h": 72,
        "release_frequency_days": 30,
        "ci_required": False,
    },
    "growing_project": {  # 100-1000 stars
        "min_docs_files": 5,
        "response_time_h": 48,
        "release_frequency_days": 14,
        "ci_required": True,
    },
    "mature_project": {  # 1000+ stars
        "min_docs_files": 8,
        "response_time_h": 24,
        "release_frequency_days": 7,
        "ci_required": True,
    },
}


class OSLearningEngine:
    """Self-improvement engine for OS project management."""

    def __init__(self, github: Optional[GitHubOps] = None):
        self._gh = github or get_github_ops()
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)
        self._insights: List[OSInsight] = self._load_insights()
        self._mastery: Dict[str, DomainMastery] = self._load_mastery()

    # ─── State Management ─────────────────────────────────────────

    def _load_insights(self) -> List[OSInsight]:
        if not INSIGHTS_FILE.exists():
            return []
        try:
            data = json.loads(INSIGHTS_FILE.read_text())
            return [
                OSInsight(
                    domain=LearningDomain(i["domain"]),
                    title=i["title"],
                    description=i["description"],
                    source_project=i.get("source_project", ""),
                    confidence=i.get("confidence", 0.0),
                    created_at=i.get("created_at", 0.0),
                    validated=i.get("validated", False),
                )
                for i in data
            ]
        except (json.JSONDecodeError, OSError):
            return []

    def _save_insights(self):
        data = [i.to_dict() for i in self._insights]
        INSIGHTS_FILE.write_text(json.dumps(data, indent=2))

    def _load_mastery(self) -> Dict[str, DomainMastery]:
        if not MASTERY_FILE.exists():
            return {
                d.value: DomainMastery(domain=d) for d in LearningDomain
            }
        try:
            data = json.loads(MASTERY_FILE.read_text())
            result = {}
            for d in LearningDomain:
                if d.value in data:
                    m = data[d.value]
                    result[d.value] = DomainMastery(
                        domain=d,
                        level=MasteryLevel(m.get("level", "novice")),
                        score=m.get("score", 0),
                        actions_completed=m.get("actions_completed", 0),
                        insights_applied=m.get("insights_applied", 0),
                        last_activity=m.get("last_activity", 0.0),
                    )
                else:
                    result[d.value] = DomainMastery(domain=d)
            return result
        except (json.JSONDecodeError, OSError):
            return {d.value: DomainMastery(domain=d) for d in LearningDomain}

    def _save_mastery(self):
        data = {k: v.to_dict() for k, v in self._mastery.items()}
        MASTERY_FILE.write_text(json.dumps(data, indent=2))

    def _update_mastery(self, domain: LearningDomain, score_delta: int = 1):
        mastery = self._mastery.get(domain.value)
        if not mastery:
            mastery = DomainMastery(domain=domain)
            self._mastery[domain.value] = mastery

        mastery.score = min(mastery.score + score_delta, mastery.max_score)
        mastery.actions_completed += 1
        mastery.last_activity = time.time()

        # Update level based on score
        if mastery.score >= 80:
            mastery.level = MasteryLevel.EXPERT
        elif mastery.score >= 60:
            mastery.level = MasteryLevel.PROFICIENT
        elif mastery.score >= 40:
            mastery.level = MasteryLevel.COMPETENT
        elif mastery.score >= 20:
            mastery.level = MasteryLevel.APPRENTICE
        else:
            mastery.level = MasteryLevel.NOVICE

        self._save_mastery()

    # ─── Metrics Collection ───────────────────────────────────────

    def collect_metrics(self, repo_name: str) -> ProjectMetrics:
        """Collect current metrics for a project."""
        metrics = ProjectMetrics(
            project_slug=repo_name,
            timestamp=time.time(),
        )

        try:
            stats = self._gh.get_repo_stats(repo_name)
            metrics.stars = stats.get("stars", 0)
            metrics.forks = stats.get("forks", 0)
            metrics.open_issues = stats.get("open_issues", 0)
            metrics.watchers = stats.get("watchers", 0)
            metrics.license_type = stats.get("license", "")
        except GitHubError:
            pass

        try:
            contributors = self._gh.get_contributor_stats(repo_name)
            metrics.contributors = len(contributors)
        except GitHubError:
            pass

        # Check for CI
        try:
            workflows = self._gh.list_workflows(repo_name)
            metrics.has_ci = len(workflows) > 0
        except GitHubError:
            pass

        # Check for docs
        for path in ["README.md", "CONTRIBUTING.md"]:
            try:
                self._gh.get_file_content(repo_name, path)
                if path == "README.md":
                    metrics.has_docs = True
                elif path == "CONTRIBUTING.md":
                    metrics.has_contributing = True
            except GitHubError:
                pass

        # Store metrics
        self._store_metrics(metrics)

        return metrics

    def _store_metrics(self, metrics: ProjectMetrics):
        try:
            with open(METRICS_FILE, "a") as f:
                f.write(json.dumps(metrics.to_dict()) + "\n")
        except OSError:
            pass

    # ─── Learning Analysis ────────────────────────────────────────

    def learn_from_project(self, repo_name: str) -> List[OSInsight]:
        """Analyze a project and extract insights."""
        metrics = self.collect_metrics(repo_name)
        new_insights = []

        # Analyze documentation
        if not metrics.has_docs:
            insight = OSInsight(
                domain=LearningDomain.DOCUMENTATION,
                title="Missing documentation",
                description=f"Project {repo_name} lacks a README. "
                "Projects with good READMEs get 2x more contributors on average.",
                source_project=repo_name,
                confidence=0.95,
                created_at=time.time(),
            )
            new_insights.append(insight)

        if not metrics.has_contributing:
            insight = OSInsight(
                domain=LearningDomain.COMMUNITY,
                title="Missing contribution guide",
                description=f"Project {repo_name} needs a CONTRIBUTING.md. "
                "This lowers the barrier for first-time contributors.",
                source_project=repo_name,
                confidence=0.90,
                created_at=time.time(),
            )
            new_insights.append(insight)

        # Analyze CI/CD
        if not metrics.has_ci:
            insight = OSInsight(
                domain=LearningDomain.CODE_QUALITY,
                title="No CI/CD pipeline",
                description=f"Project {repo_name} has no GitHub Actions workflows. "
                "Automated testing increases code quality and contributor confidence.",
                source_project=repo_name,
                confidence=0.85,
                created_at=time.time(),
            )
            new_insights.append(insight)

        # Analyze issue health
        if metrics.open_issues > 20:
            insight = OSInsight(
                domain=LearningDomain.MAINTENANCE,
                title="High open issue count",
                description=f"Project {repo_name} has {metrics.open_issues} open issues. "
                "Consider triaging, labeling, and closing stale issues.",
                source_project=repo_name,
                confidence=0.80,
                created_at=time.time(),
            )
            new_insights.append(insight)

        # Analyze growth
        if metrics.stars > 0 and metrics.forks == 0:
            insight = OSInsight(
                domain=LearningDomain.COMMUNITY,
                title="Stars but no forks",
                description=f"Project {repo_name} has {metrics.stars} stars but no forks. "
                "Add 'good first issue' labels and clear contribution docs to encourage forks.",
                source_project=repo_name,
                confidence=0.70,
                created_at=time.time(),
            )
            new_insights.append(insight)

        # Store insights
        self._insights.extend(new_insights)
        self._save_insights()

        # Update mastery
        self._update_mastery(LearningDomain.PROJECT_SETUP, 2)

        log_debug("os_learning", f"Learned {len(new_insights)} insights from {repo_name}")
        return new_insights

    def analyze_trends(self, repo_name: str) -> Dict[str, Any]:
        """Analyze metric trends over time for a project."""
        if not METRICS_FILE.exists():
            return {"error": "No metrics data available"}

        snapshots = []
        try:
            with open(METRICS_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if entry.get("project_slug") == repo_name:
                        snapshots.append(entry)
        except (json.JSONDecodeError, OSError):
            return {"error": "Failed to read metrics"}

        if len(snapshots) < 2:
            return {
                "project": repo_name,
                "snapshots": len(snapshots),
                "trend": "insufficient_data",
                "latest": snapshots[-1] if snapshots else None,
            }

        latest = snapshots[-1]
        previous = snapshots[-2]

        trends = {
            "stars": latest.get("stars", 0) - previous.get("stars", 0),
            "forks": latest.get("forks", 0) - previous.get("forks", 0),
            "issues": latest.get("open_issues", 0) - previous.get("open_issues", 0),
            "contributors": latest.get("contributors", 0) - previous.get("contributors", 0),
        }

        overall = sum(1 for v in trends.values() if v > 0)
        trend_direction = "growing" if overall >= 2 else "stable" if overall >= 1 else "declining"

        return {
            "project": repo_name,
            "snapshots": len(snapshots),
            "trend": trend_direction,
            "deltas": trends,
            "latest": latest,
        }

    # ─── Benchmarking ─────────────────────────────────────────────

    def benchmark_project(self, repo_name: str) -> Dict[str, Any]:
        """Benchmark a project against OS standards."""
        metrics = self.collect_metrics(repo_name)

        # Determine project tier
        if metrics.stars >= 1000:
            tier = "mature_project"
        elif metrics.stars >= 100:
            tier = "growing_project"
        else:
            tier = "small_project"

        benchmark = OS_BENCHMARKS[tier]
        results: Dict[str, Any] = {
            "project": repo_name,
            "tier": tier,
            "checks": {},
            "passed": 0,
            "total": 0,
        }

        # Check documentation
        doc_files = sum([metrics.has_docs, metrics.has_contributing, bool(metrics.license_type)])
        meets_docs = doc_files >= benchmark["min_docs_files"]
        results["checks"]["documentation"] = {
            "required": benchmark["min_docs_files"],
            "actual": doc_files,
            "passed": meets_docs,
        }
        results["total"] += 1
        if meets_docs:
            results["passed"] += 1

        # Check CI
        if benchmark["ci_required"]:
            results["checks"]["ci_cd"] = {
                "required": True,
                "actual": metrics.has_ci,
                "passed": metrics.has_ci,
            }
            results["total"] += 1
            if metrics.has_ci:
                results["passed"] += 1

        results["score"] = (
            round(results["passed"] / results["total"] * 100)
            if results["total"] > 0
            else 0
        )
        results["grade"] = (
            "A" if results["score"] >= 90
            else "B" if results["score"] >= 75
            else "C" if results["score"] >= 60
            else "D" if results["score"] >= 40
            else "F"
        )

        # Update mastery
        self._update_mastery(LearningDomain.CODE_QUALITY, 1)

        return results

    # ─── Mastery Report ───────────────────────────────────────────

    def get_mastery_report(self) -> Dict[str, Any]:
        """Generate a mastery progression report."""
        domains = {}
        total_score = 0
        total_max = 0

        for key, mastery in self._mastery.items():
            domains[key] = mastery.to_dict()
            total_score += mastery.score
            total_max += mastery.max_score

        overall_pct = round(total_score / total_max * 100) if total_max > 0 else 0

        if overall_pct >= 80:
            overall_level = MasteryLevel.EXPERT
        elif overall_pct >= 60:
            overall_level = MasteryLevel.PROFICIENT
        elif overall_pct >= 40:
            overall_level = MasteryLevel.COMPETENT
        elif overall_pct >= 20:
            overall_level = MasteryLevel.APPRENTICE
        else:
            overall_level = MasteryLevel.NOVICE

        return {
            "overall_level": overall_level.value,
            "overall_score": overall_pct,
            "domains": domains,
            "total_insights": len(self._insights),
            "validated_insights": sum(1 for i in self._insights if i.validated),
        }

    def get_insights(
        self, domain: Optional[LearningDomain] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get learning insights, optionally filtered by domain."""
        insights = self._insights
        if domain:
            insights = [i for i in insights if i.domain == domain]
        return [i.to_dict() for i in insights[-limit:]]

    def get_recommendations(self, repo_name: str) -> List[str]:
        """Get actionable recommendations for a project."""
        insights = [i for i in self._insights if i.source_project == repo_name]
        return [
            f"[{i.domain.value}] {i.title}: {i.description}"
            for i in insights
            if not i.validated
        ]


# ─── Singleton ────────────────────────────────────────────────────

_os_learning: Optional[OSLearningEngine] = None


def get_os_learning(**kwargs) -> OSLearningEngine:
    global _os_learning
    if _os_learning is None:
        _os_learning = OSLearningEngine(**kwargs)
    return _os_learning
