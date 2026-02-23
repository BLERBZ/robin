"""Tests for lib/os_marketing.py — OS Marketing & Promotion."""

import json
import time
from pathlib import Path

import pytest

import lib.os_marketing as osm
from lib.os_marketing import (
    OSMarketing,
    ContentType,
    CampaignType,
    MarketingContent,
)
from lib.github_ops import GitHubError


class MockGitHubOps:
    def get_repo_stats(self, repo_name):
        return {"stars": 10, "forks": 3}

    def _check_repo_allowed(self, repo_name):
        pass


def _patch_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(osm, "MARKETING_DIR", tmp_path / "os_marketing")
    monkeypatch.setattr(osm, "CONTENT_DIR", tmp_path / "os_marketing" / "content")
    monkeypatch.setattr(osm, "ANALYTICS_FILE", tmp_path / "os_marketing" / "analytics.jsonl")
    monkeypatch.setattr(osm, "_os_marketing", None)


@pytest.fixture
def marketing(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    return OSMarketing(github=MockGitHubOps())


# ─── MarketingContent ─────────────────────────────────────────────


def test_marketing_content_to_dict():
    c = MarketingContent(
        content_type=ContentType.BLOG,
        title="Test Post",
        body="Content here",
        project_slug="robin",
        campaign=CampaignType.LAUNCH,
        created_at=1000.0,
    )
    d = c.to_dict()
    assert d["content_type"] == "blog"
    assert d["campaign"] == "launch"
    assert d["project_slug"] == "robin"


# ─── Badge Generation ────────────────────────────────────────────


def test_generate_badges(marketing):
    badges = marketing.generate_badges("robin")
    assert "license" in badges
    assert "blerbz" in badges
    assert "kait_managed" in badges
    assert "stars" in badges
    assert "shields.io" in badges["license"]


def test_get_badge_block(marketing):
    block = marketing.get_badge_block("robin")
    assert "img.shields.io" in block
    assert "MIT" in block or "License" in block


# ─── Launch Materials ─────────────────────────────────────────────


def test_generate_launch_materials(marketing):
    materials = marketing.generate_launch_materials("robin", "A test project")
    assert len(materials) == 4  # blog, twitter, linkedin, discussion

    types = {m.content_type for m in materials}
    assert ContentType.BLOG in types
    assert ContentType.TWITTER in types
    assert ContentType.LINKEDIN in types
    assert ContentType.GITHUB_DISCUSSION in types


def test_launch_materials_contain_project_name(marketing):
    materials = marketing.generate_launch_materials("robin")
    for m in materials:
        assert "robin" in m.body.lower() or "Robin" in m.body


def test_launch_materials_contain_blerbz(marketing):
    materials = marketing.generate_launch_materials("robin")
    for m in materials:
        assert "BLERBZ" in m.body or "blerbz" in m.body


def test_launch_materials_saved(marketing, tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    marketing_dir = tmp_path / "os_marketing" / "content"
    marketing2 = OSMarketing(github=MockGitHubOps())
    marketing2.generate_launch_materials("robin")

    files = list(marketing_dir.glob("*.json"))
    assert len(files) == 4


# ─── Contributor Highlights ───────────────────────────────────────


def test_contributor_highlight(marketing):
    content = marketing.generate_contributor_highlight("robin", "dev-user", "Fixed the login page")
    assert content.content_type == ContentType.CONTRIBUTOR_HIGHLIGHT
    assert "dev-user" in content.body
    assert "Fixed the login page" in content.body
    assert content.metadata["username"] == "dev-user"


def test_contributor_highlight_no_contribution(marketing):
    content = marketing.generate_contributor_highlight("robin", "new-user")
    assert "new-user" in content.body


# ─── Milestone Announcements ─────────────────────────────────────


def test_milestone_announcement(marketing):
    materials = marketing.generate_milestone_announcement(
        "robin", "100 GitHub Stars!", "Thanks to our community"
    )
    assert len(materials) == 2  # twitter + discussion

    types = {m.content_type for m in materials}
    assert ContentType.TWITTER in types
    assert ContentType.GITHUB_DISCUSSION in types

    for m in materials:
        assert "100 GitHub Stars" in m.body


# ─── Content Listing ─────────────────────────────────────────────


def test_list_content(marketing):
    marketing.generate_launch_materials("robin")
    content = marketing.list_content()
    assert len(content) == 4


def test_list_content_filtered_by_project(marketing):
    marketing.generate_launch_materials("robin")
    marketing.generate_launch_materials("other-project")
    content = marketing.list_content(project_slug="robin")
    assert all(c["project_slug"] == "robin" for c in content)


def test_list_content_filtered_by_campaign(marketing):
    marketing.generate_launch_materials("robin")
    content = marketing.list_content(campaign=CampaignType.LAUNCH)
    assert all(c["campaign"] == "launch" for c in content)


# ─── Analytics ────────────────────────────────────────────────────


def test_track_event(marketing):
    marketing.track_event("launch_announced", "robin", {"channel": "twitter"})
    marketing.track_event("launch_announced", "robin", {"channel": "blog"})
    summary = marketing.get_analytics_summary()
    assert summary["total_events"] == 2
    assert summary["event_types"]["launch_announced"] == 2


def test_analytics_filtered(marketing):
    marketing.track_event("view", "robin")
    marketing.track_event("view", "other-project")
    summary = marketing.get_analytics_summary(project_slug="robin")
    assert summary["total_events"] == 1


def test_analytics_empty(marketing):
    summary = marketing.get_analytics_summary()
    assert summary["events"] == 0 or summary.get("total_events", 0) == 0


# ─── Twitter Post Length ──────────────────────────────────────────


def test_twitter_post_length(marketing):
    materials = marketing.generate_launch_materials("robin")
    twitter = [m for m in materials if m.content_type == ContentType.TWITTER][0]
    # Twitter posts should be reasonable length (not necessarily 280 chars due to links)
    assert len(twitter.body) < 500
