"""
Kait OS Marketing & Promotion — Content generation for OS projects

Generates marketing and promotional materials:
- Release announcements (blog, social, newsletter)
- README badges and shields
- Contributor highlights and shoutouts
- Project launch materials
- Social media post templates
- Marketing analytics tracking

Usage:
    from lib.os_marketing import OSMarketing
    marketing = OSMarketing()
    marketing.generate_launch_materials("robin")
    marketing.generate_contributor_highlight("robin", "username")
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
MARKETING_DIR = KAIT_DIR / "os_marketing"
CONTENT_DIR = MARKETING_DIR / "content"
ANALYTICS_FILE = MARKETING_DIR / "analytics.jsonl"

BLERBZ_ORG = os.environ.get("KAIT_GITHUB_OWNER", "") or os.environ.get("KAIT_GITHUB_ORG", "BLERBZ")
BLERBZ_NAME = os.environ.get("KAIT_BLERBZ_NAME", "BLERBZ LLC")
BLERBZ_URL = os.environ.get("KAIT_BLERBZ_URL", "https://blerbz.com")


class ContentType(str, Enum):
    BLOG = "blog"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    NEWSLETTER = "newsletter"
    GITHUB_DISCUSSION = "github_discussion"
    RELEASE_NOTES = "release_notes"
    CONTRIBUTOR_HIGHLIGHT = "contributor_highlight"


class CampaignType(str, Enum):
    LAUNCH = "launch"
    RELEASE = "release"
    MILESTONE = "milestone"
    CONTRIBUTOR = "contributor"
    UPDATE = "update"


@dataclass
class MarketingContent:
    """A piece of marketing content."""

    content_type: ContentType
    title: str
    body: str
    project_slug: str
    campaign: CampaignType
    created_at: float = 0.0
    published: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_type": self.content_type.value,
            "title": self.title,
            "body": self.body,
            "project_slug": self.project_slug,
            "campaign": self.campaign.value,
            "created_at": self.created_at,
            "published": self.published,
            "metadata": self.metadata,
        }


class OSMarketing:
    """Marketing and promotion engine for BLERBZ OS projects."""

    def __init__(self, github: Optional[GitHubOps] = None):
        self._gh = github or get_github_ops()
        MARKETING_DIR.mkdir(parents=True, exist_ok=True)
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Badge Generation ─────────────────────────────────────────

    def generate_badges(self, repo_name: str) -> Dict[str, str]:
        """Generate shields.io badge markdown for a project."""
        base = f"https://github.com/{BLERBZ_ORG}/{repo_name}"

        badges = {
            "license": f"[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]({base}/blob/main/LICENSE)",
            "blerbz": f"[![BLERBZ OS](https://img.shields.io/badge/BLERBZ-Open%20Source-blue.svg)]({BLERBZ_URL})",
            "kait_managed": f"[![Managed by Kait](https://img.shields.io/badge/Managed%20by-Kait%20OS%20Sidekick-green.svg)](https://github.com/{BLERBZ_ORG}/kait-intel)",
            "stars": f"[![GitHub stars](https://img.shields.io/github/stars/{BLERBZ_ORG}/{repo_name}?style=social)]({base})",
            "forks": f"[![GitHub forks](https://img.shields.io/github/forks/{BLERBZ_ORG}/{repo_name}?style=social)]({base}/fork)",
            "issues": f"[![GitHub issues](https://img.shields.io/github/issues/{BLERBZ_ORG}/{repo_name})]({base}/issues)",
            "prs": f"[![GitHub pull requests](https://img.shields.io/github/issues-pr/{BLERBZ_ORG}/{repo_name})]({base}/pulls)",
            "last_commit": f"[![GitHub last commit](https://img.shields.io/github/last-commit/{BLERBZ_ORG}/{repo_name})]({base}/commits)",
            "python": "[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)",
        }
        return badges

    def get_badge_block(self, repo_name: str) -> str:
        """Get a formatted block of badges for README insertion."""
        badges = self.generate_badges(repo_name)
        priority = ["license", "blerbz", "kait_managed", "stars", "python"]
        return " ".join(badges[k] for k in priority if k in badges)

    # ─── Launch Materials ─────────────────────────────────────────

    def generate_launch_materials(self, repo_name: str, description: str = "") -> List[MarketingContent]:
        """Generate complete launch campaign materials."""
        now = time.time()
        date = datetime.now(timezone.utc).strftime("%B %d, %Y")
        repo_url = f"https://github.com/{BLERBZ_ORG}/{repo_name}"

        materials = []

        # Blog post
        blog = MarketingContent(
            content_type=ContentType.BLOG,
            title=f"Introducing {repo_name.title()} — A New Open Source Project by {BLERBZ_NAME}",
            body=f"""# Introducing {repo_name.title()}

**{date}** — We're excited to announce the launch of [{repo_name.title()}]({repo_url}),
the latest open-source project from {BLERBZ_NAME}.

## What is {repo_name.title()}?

{description or f'{repo_name.title()} is a new open-source project designed to push the boundaries of what AI sidekicks can do.'}

## Why Open Source?

At {BLERBZ_NAME}, we believe in building in the open. Open source enables:

- **Transparency** — See exactly how it works
- **Community** — Build together, grow together
- **Quality** — More eyes, better code
- **Innovation** — Fork, extend, customize

## Get Started

```bash
git clone {repo_url}.git
cd {repo_name}
pip install -e ".[dev]"
```

## Contributing

We welcome contributors of all experience levels! Check out our
[Contributing Guide]({repo_url}/blob/main/CONTRIBUTING.md) and look for
issues labeled `good first issue`.

## What's Next

We have an exciting roadmap planned. Follow our progress on
[GitHub]({repo_url}) and join the conversation in
[Discussions]({repo_url}/discussions).

---

Built by [{BLERBZ_NAME}]({BLERBZ_URL}) | Managed by [Kait OS Sidekick](https://github.com/{BLERBZ_ORG}/kait-intel)
""",
            project_slug=repo_name,
            campaign=CampaignType.LAUNCH,
            created_at=now,
        )
        materials.append(blog)

        # Twitter post
        twitter = MarketingContent(
            content_type=ContentType.TWITTER,
            title=f"Launch: {repo_name.title()}",
            body=(
                f"Announcing {repo_name.title()} — our newest open-source project! "
                f"{description[:100] if description else 'Built for the community, by the community.'} "
                f"Check it out: {repo_url} "
                f"#OpenSource #BLERBZ #AI"
            ),
            project_slug=repo_name,
            campaign=CampaignType.LAUNCH,
            created_at=now,
        )
        materials.append(twitter)

        # LinkedIn post
        linkedin = MarketingContent(
            content_type=ContentType.LINKEDIN,
            title=f"New Open Source Project: {repo_name.title()}",
            body=f"""Excited to announce the launch of {repo_name.title()}, the latest open-source project from {BLERBZ_NAME}!

{description or f'{repo_name.title()} brings AI sidekick capabilities to the open-source community.'}

What makes this special:
- Built with open-source principles from day one
- Community-driven development
- Comprehensive documentation and contributor guides
- Managed by our AI sidekick, Kait

We're looking for contributors! Whether you're a seasoned developer or just getting started,
there's a place for you in this project.

Check it out: {repo_url}

#OpenSource #AI #Innovation #BLERBZ #Community
""",
            project_slug=repo_name,
            campaign=CampaignType.LAUNCH,
            created_at=now,
        )
        materials.append(linkedin)

        # GitHub Discussion announcement
        discussion = MarketingContent(
            content_type=ContentType.GITHUB_DISCUSSION,
            title=f"Welcome to {repo_name.title()}!",
            body=f"""# Welcome to {repo_name.title()}!

We're thrilled to launch {repo_name.title()} as an open-source project!

## Getting Started

1. **Star** the repo to stay updated
2. **Fork** it to start contributing
3. Check out the [README]({repo_url}#readme) for setup instructions
4. Browse [good first issues]({repo_url}/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)

## Community Guidelines

- Be respectful and inclusive
- Follow our [Code of Conduct]({repo_url}/blob/main/CODE_OF_CONDUCT.md)
- Ask questions! No question is too basic

## How to Contribute

See our [Contributing Guide]({repo_url}/blob/main/CONTRIBUTING.md) for details.

We can't wait to see what you build!

— The {BLERBZ_NAME} Team
""",
            project_slug=repo_name,
            campaign=CampaignType.LAUNCH,
            created_at=now,
        )
        materials.append(discussion)

        # Save materials
        self._save_content(materials)
        return materials

    # ─── Contributor Highlights ───────────────────────────────────

    def generate_contributor_highlight(
        self, repo_name: str, username: str, contribution: str = ""
    ) -> MarketingContent:
        """Generate a contributor highlight/shoutout."""
        repo_url = f"https://github.com/{BLERBZ_ORG}/{repo_name}"
        profile_url = f"https://github.com/{username}"
        now = time.time()

        content = MarketingContent(
            content_type=ContentType.CONTRIBUTOR_HIGHLIGHT,
            title=f"Contributor Spotlight: @{username}",
            body=f"""## Contributor Spotlight: @{username}

A huge thank you to [@{username}]({profile_url}) for their contribution to
[{repo_name.title()}]({repo_url})!

{f'**What they did:** {contribution}' if contribution else ''}

Open source is powered by amazing contributors like @{username}.
Thank you for making {repo_name.title()} better!

Want to contribute? Check out our [Contributing Guide]({repo_url}/blob/main/CONTRIBUTING.md)
and find a [good first issue]({repo_url}/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
""",
            project_slug=repo_name,
            campaign=CampaignType.CONTRIBUTOR,
            created_at=now,
            metadata={"username": username, "contribution": contribution},
        )

        self._save_content([content])
        return content

    # ─── Milestone Announcements ──────────────────────────────────

    def generate_milestone_announcement(
        self, repo_name: str, milestone: str, details: str = ""
    ) -> List[MarketingContent]:
        """Generate milestone celebration content."""
        repo_url = f"https://github.com/{BLERBZ_ORG}/{repo_name}"
        now = time.time()
        materials = []

        twitter = MarketingContent(
            content_type=ContentType.TWITTER,
            title=f"Milestone: {milestone}",
            body=(
                f"{repo_name.title()} just hit a milestone: {milestone}! "
                f"{details[:80] if details else 'Thank you to our amazing community!'} "
                f"{repo_url} #OpenSource #BLERBZ"
            ),
            project_slug=repo_name,
            campaign=CampaignType.MILESTONE,
            created_at=now,
            metadata={"milestone": milestone},
        )
        materials.append(twitter)

        discussion = MarketingContent(
            content_type=ContentType.GITHUB_DISCUSSION,
            title=f"Milestone Reached: {milestone}!",
            body=f"""# We hit a milestone: {milestone}!

Thank you to everyone who has contributed to making {repo_name.title()} what it is today.

{details if details else 'This milestone is a testament to our amazing community.'}

Here's to the next milestone!

— {BLERBZ_NAME}
""",
            project_slug=repo_name,
            campaign=CampaignType.MILESTONE,
            created_at=now,
        )
        materials.append(discussion)

        self._save_content(materials)
        return materials

    # ─── Content Management ───────────────────────────────────────

    def _save_content(self, materials: List[MarketingContent]):
        """Save generated content to disk."""
        for m in materials:
            filename = f"{m.project_slug}_{m.campaign.value}_{m.content_type.value}_{int(m.created_at)}.json"
            filepath = CONTENT_DIR / filename
            filepath.write_text(json.dumps(m.to_dict(), indent=2))

    def list_content(
        self,
        project_slug: Optional[str] = None,
        campaign: Optional[CampaignType] = None,
    ) -> List[Dict[str, Any]]:
        """List generated marketing content."""
        results = []
        for filepath in sorted(CONTENT_DIR.glob("*.json")):
            try:
                data = json.loads(filepath.read_text())
                if project_slug and data.get("project_slug") != project_slug:
                    continue
                if campaign and data.get("campaign") != campaign.value:
                    continue
                results.append(data)
            except (json.JSONDecodeError, OSError):
                pass
        return results

    # ─── Analytics ────────────────────────────────────────────────

    def track_event(self, event_type: str, project_slug: str, details: Optional[Dict] = None):
        """Track a marketing event for analytics."""
        entry = {
            "ts": time.time(),
            "event_type": event_type,
            "project_slug": project_slug,
            "details": details or {},
        }
        try:
            with open(ANALYTICS_FILE, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def get_analytics_summary(self, project_slug: Optional[str] = None) -> Dict[str, Any]:
        """Get analytics summary."""
        if not ANALYTICS_FILE.exists():
            return {"events": 0}

        events = []
        try:
            with open(ANALYTICS_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if project_slug and entry.get("project_slug") != project_slug:
                        continue
                    events.append(entry)
        except (json.JSONDecodeError, OSError):
            pass

        event_types: Dict[str, int] = {}
        for e in events:
            t = e.get("event_type", "unknown")
            event_types[t] = event_types.get(t, 0) + 1

        return {
            "total_events": len(events),
            "event_types": event_types,
            "content_generated": len(self.list_content(project_slug)),
        }


# ─── Singleton ────────────────────────────────────────────────────

_os_marketing: Optional[OSMarketing] = None


def get_os_marketing(**kwargs) -> OSMarketing:
    global _os_marketing
    if _os_marketing is None:
        _os_marketing = OSMarketing(**kwargs)
    return _os_marketing
