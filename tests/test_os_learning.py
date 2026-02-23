"""Tests for lib/os_learning.py — OS Learning Engine."""

import json
import time
from pathlib import Path

import pytest

import lib.os_learning as osl
from lib.os_learning import (
    OSLearningEngine,
    MasteryLevel,
    LearningDomain,
    ProjectMetrics,
    OSInsight,
    DomainMastery,
)
from lib.github_ops import GitHubError


class MockGitHubOps:
    """Mock GitHub for learning tests."""

    def __init__(self, stars=5, forks=1, has_ci=False, has_readme=True, has_contributing=False):
        self.stars = stars
        self.forks = forks
        self.has_ci = has_ci
        self._has_readme = has_readme
        self._has_contributing = has_contributing

    def get_repo_stats(self, repo_name):
        return {
            "stars": self.stars,
            "forks": self.forks,
            "open_issues": 3,
            "watchers": 2,
            "license": "MIT",
            "name": repo_name,
        }

    def get_contributor_stats(self, repo_name):
        return [{"login": "user1"}, {"login": "user2"}]

    def list_workflows(self, repo_name):
        if self.has_ci:
            return [{"id": 1, "name": "CI"}]
        return []

    def get_file_content(self, repo_name, path, ref="main"):
        if path == "README.md" and self._has_readme:
            return {"content": "readme", "sha": "abc"}
        if path == "CONTRIBUTING.md" and self._has_contributing:
            return {"content": "contributing", "sha": "def"}
        raise GitHubError("Not found", status_code=404)

    def _check_repo_allowed(self, repo_name):
        pass


def _patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(osl, "LEARNING_DIR", tmp_path / "os_learning")
    monkeypatch.setattr(osl, "METRICS_FILE", tmp_path / "os_learning" / "metrics.jsonl")
    monkeypatch.setattr(osl, "INSIGHTS_FILE", tmp_path / "os_learning" / "insights.json")
    monkeypatch.setattr(osl, "MASTERY_FILE", tmp_path / "os_learning" / "mastery.json")
    monkeypatch.setattr(osl, "_os_learning", None)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    return OSLearningEngine(github=MockGitHubOps())


# ─── ProjectMetrics ───────────────────────────────────────────────


def test_project_metrics_to_dict():
    m = ProjectMetrics(project_slug="robin", timestamp=1000.0, stars=10, forks=5)
    d = m.to_dict()
    assert d["project_slug"] == "robin"
    assert d["stars"] == 10
    assert d["forks"] == 5


# ─── OSInsight ────────────────────────────────────────────────────


def test_os_insight_to_dict():
    i = OSInsight(
        domain=LearningDomain.DOCUMENTATION,
        title="Missing docs",
        description="No README found",
        source_project="robin",
        confidence=0.9,
        created_at=1000.0,
    )
    d = i.to_dict()
    assert d["domain"] == "documentation"
    assert d["title"] == "Missing docs"
    assert d["confidence"] == 0.9


# ─── DomainMastery ────────────────────────────────────────────────


def test_domain_mastery_to_dict():
    m = DomainMastery(domain=LearningDomain.RELEASES, level=MasteryLevel.COMPETENT, score=45)
    d = m.to_dict()
    assert d["domain"] == "releases"
    assert d["level"] == "competent"
    assert d["score"] == 45


# ─── Metrics Collection ──────────────────────────────────────────


def test_collect_metrics(engine):
    metrics = engine.collect_metrics("robin")
    assert metrics.project_slug == "robin"
    assert metrics.stars == 5
    assert metrics.forks == 1
    assert metrics.contributors == 2
    assert metrics.has_docs is True


def test_collect_metrics_no_contributing(engine):
    metrics = engine.collect_metrics("robin")
    assert metrics.has_contributing is False


# ─── Learning from Projects ──────────────────────────────────────


def test_learn_from_project(engine):
    insights = engine.learn_from_project("robin")
    assert isinstance(insights, list)
    # Should detect missing contributing guide
    domains = [i.domain for i in insights]
    assert LearningDomain.COMMUNITY in domains


def test_learn_from_project_no_ci(engine):
    insights = engine.learn_from_project("robin")
    # Should detect missing CI
    domains = [i.domain for i in insights]
    assert LearningDomain.CODE_QUALITY in domains


def test_learn_with_ci(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    engine = OSLearningEngine(github=MockGitHubOps(has_ci=True, has_contributing=True))
    insights = engine.learn_from_project("robin")
    # Should not report missing CI
    ci_insights = [i for i in insights if "CI" in i.title]
    assert len(ci_insights) == 0


def test_insights_persist(engine, tmp_path, monkeypatch):
    engine.learn_from_project("robin")
    assert len(engine._insights) > 0

    # Reload
    _patch_paths(tmp_path, monkeypatch)
    engine2 = OSLearningEngine(github=MockGitHubOps())
    assert len(engine2._insights) > 0


# ─── Mastery ──────────────────────────────────────────────────────


def test_initial_mastery(engine):
    report = engine.get_mastery_report()
    assert report["overall_level"] == "novice"
    assert report["overall_score"] == 0


def test_mastery_increases(engine):
    engine.learn_from_project("robin")
    report = engine.get_mastery_report()
    # Should have increased project_setup score
    assert report["domains"]["project_setup"]["score"] > 0


def test_mastery_level_progression(engine):
    # Simulate many learning cycles to increase mastery
    for _ in range(15):
        engine._update_mastery(LearningDomain.PROJECT_SETUP, 5)
    mastery = engine._mastery["project_setup"]
    assert mastery.level in (MasteryLevel.PROFICIENT, MasteryLevel.EXPERT)


# ─── Trends ───────────────────────────────────────────────────────


def test_analyze_trends_no_data(engine):
    result = engine.analyze_trends("robin")
    assert result.get("error") or result.get("trend") == "insufficient_data"


def test_analyze_trends_with_data(engine):
    # Collect metrics twice
    engine.collect_metrics("robin")
    engine.collect_metrics("robin")
    result = engine.analyze_trends("robin")
    assert result["project"] == "robin"
    assert result["snapshots"] >= 2


# ─── Benchmarking ─────────────────────────────────────────────────


def test_benchmark_small_project(engine):
    result = engine.benchmark_project("robin")
    assert result["tier"] == "small_project"
    assert "score" in result
    assert "grade" in result


def test_benchmark_growing_project(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    engine = OSLearningEngine(github=MockGitHubOps(stars=500))
    result = engine.benchmark_project("robin")
    assert result["tier"] == "growing_project"


# ─── Insights Retrieval ──────────────────────────────────────────


def test_get_insights(engine):
    engine.learn_from_project("robin")
    insights = engine.get_insights()
    assert len(insights) > 0
    assert "domain" in insights[0]


def test_get_insights_filtered(engine):
    engine.learn_from_project("robin")
    insights = engine.get_insights(domain=LearningDomain.COMMUNITY)
    assert all(i["domain"] == "community" for i in insights)


# ─── Recommendations ─────────────────────────────────────────────


def test_get_recommendations(engine):
    engine.learn_from_project("robin")
    recs = engine.get_recommendations("robin")
    assert isinstance(recs, list)
    assert len(recs) > 0


# ─── Mastery Report ──────────────────────────────────────────────


def test_mastery_report_structure(engine):
    report = engine.get_mastery_report()
    assert "overall_level" in report
    assert "overall_score" in report
    assert "domains" in report
    assert "total_insights" in report
    # All domains should be present
    for d in LearningDomain:
        assert d.value in report["domains"]
