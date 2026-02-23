# Kait OS Sidekick — Open Source Project Management

## Overview

Kait OS Sidekick is the open-source project management layer built into Kait.
It enables autonomous and instructed management of the full lifecycle of BLERBZ
open-source projects through the GitHub API.

## Architecture

```
CLI Interface (kait os / kait robin / kait gh)
        ↓
┌──────────────────────────────────────────┐
│           OS Sidekick Modules             │
├──────────┬──────────┬───────────┬────────┤
│ GitHub   │ Project  │ Release   │ OS     │
│ Ops      │ Manager  │ Pipeline  │ Learn  │
├──────────┼──────────┼───────────┼────────┤
│ Robin    │ OS       │           │        │
│ Sync     │ Marketing│           │        │
└──────────┴──────────┴───────────┴────────┘
        ↓
  GitHub API (REST, rate-limited, audit-logged)
```

## Modules

### lib/github_ops.py — GitHub API Operations

Core API layer providing:
- Repository CRUD operations
- Issue and PR management
- Release creation and tagging
- Branch management and protection
- Webhook management
- GitHub Actions workflow triggers
- Rate limiting with exponential backoff
- Token-scoped security with repo allowlist
- Full audit logging

### lib/os_project_manager.py — Project Lifecycle

Manages the complete OS project lifecycle:
- **Creation**: Scaffolds new repos with README, LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG, SECURITY, .gitignore
- **Phases**: Planning → Development → Testing → Release → Maintenance
- **Health checks**: Validates community health files, issue counts, PR status
- **Metrics**: Stars, forks, contributors, issue velocity
- **Viability assessment**: Heuristic scoring for new project ideas
- **Development ops**: Feature branches, issue creation, bug reports

### lib/release_pipeline.py — Automated Releases

Full release automation:
- **SemVer management**: Parse, bump (major/minor/patch/prerelease), validate
- **Auto-detection**: Determines bump type from commit messages
- **Changelog generation**: Groups commits by category (feat, fix, docs, etc.)
- **Release notes**: Human-readable release notes
- **GitHub Release**: Creates tagged releases with notes
- **Announcements**: Blog, Twitter, LinkedIn, GitHub Discussion drafts

### lib/os_learning.py — Self-Improvement Engine

Learns from project patterns:
- **Metrics collection**: Stars, forks, contributors, CI status, docs
- **Insight extraction**: Detects missing docs, CI, stale issues
- **Mastery tracking**: 7 domains (setup, quality, community, releases, docs, maintenance, marketing)
- **Benchmarking**: Compare against small/growing/mature project standards
- **Trend analysis**: Track growth over time
- **Recommendations**: Actionable improvement suggestions

### lib/robin_sync.py — Kait→Robin Sync

Synchronization pipeline:
- **Exclusion rules**: Filters proprietary files (.env, mind_bridge, etc.)
- **Branding**: Replaces kait-intel references with robin
- **Diff-based sync**: Only syncs changed files
- **Safety**: Deletes are skipped (manual review required)
- **Validation**: Checks Robin repo health and sync freshness
- **Initialization**: Full Robin repo setup with BLERBZ branding

### lib/os_marketing.py — Promotion Engine

Content generation:
- **Badge generation**: shields.io badges for README
- **Launch campaigns**: Blog, Twitter, LinkedIn, GitHub Discussion
- **Contributor highlights**: Spotlight individual contributors
- **Milestone announcements**: Celebrate project milestones
- **Analytics**: Track marketing events and content generation

## CLI Commands

### OS Project Management

```bash
# Create a new project
kait os new robin --description "BLERBZ OS Sidekick"

# Show project status
kait os status robin

# List all projects
kait os status

# Create a release
kait os release robin --bump minor

# Dry-run release
kait os release robin --bump patch --dry-run

# Health check
kait os health robin

# Learning cycle
kait os learn robin

# Mastery report
kait os learn

# Generate promotion materials
kait os promote robin
```

### Robin Sync

```bash
# Initialize Robin
kait robin init

# Sync Kait → Robin
kait robin sync

# Check sync status
kait robin status

# Validate sync
kait robin validate
```

### GitHub Operations

```bash
# Check GitHub API health
kait gh health

# List org repos
kait gh repos

# Check rate limits
kait gh rate
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KAIT_GITHUB_TOKEN` | GitHub personal access token | — |
| `KAIT_GITHUB_ORG` | GitHub organization | `blerbz` |
| `KAIT_GITHUB_ALLOWED_REPOS` | Repo allowlist (comma-separated) | — |
| `KAIT_BLERBZ_NAME` | Organization display name | `BLERBZ LLC` |
| `KAIT_BLERBZ_URL` | Organization URL | `https://blerbz.com` |
| `KAIT_BLERBZ_LICENSE` | Default license | `MIT` |
| `KAIT_ROBIN_REPO` | Robin repo slug | `robin` |
| `KAIT_ROBIN_SYNC_BRANCH` | Robin sync target branch | `main` |
| `KAIT_SOURCE_REPO` | Kait source repo slug | `kait-intel` |

### GitHub Token Scopes

Required scopes for full functionality:
- `repo` — Full repository access
- `workflow` — GitHub Actions management
- `admin:org` — Organization management (optional)

## Security

- **Token scoping**: All GitHub operations respect the `KAIT_GITHUB_ALLOWED_REPOS` allowlist
- **Audit logging**: Every GitHub API operation is logged to `~/.kait/github/audit.jsonl`
- **Rate limiting**: Exponential backoff with configurable buffer (stops at 100 remaining)
- **No secrets in sync**: `.env` and credentials are excluded from Robin sync

## State Files

All state is stored under `~/.kait/`:

```
~/.kait/
├── github/
│   ├── api_cache.json     # API response cache
│   └── audit.jsonl        # Audit log
├── os_projects/
│   └── projects.json      # Project registry
├── releases/
│   └── release_log.jsonl  # Release history
├── os_learning/
│   ├── metrics.jsonl      # Project metrics
│   ├── insights.json      # Learning insights
│   └── mastery.json       # Mastery progression
├── robin_sync/
│   ├── state.json         # Sync state
│   └── sync.jsonl         # Sync log
└── os_marketing/
    ├── content/           # Generated marketing content
    └── analytics.jsonl    # Marketing analytics
```

## GitHub Actions Workflows

### robin-sync.yml
Triggers on push to main; syncs Kait changes to Robin automatically.

### os-release.yml
Manual workflow dispatch; creates releases for any project with version bumping.

### os-health.yml
Weekly health check; runs learning cycle on all tracked projects.

## Testing

All modules have comprehensive tests:

```bash
# Run all OS Sidekick tests
pytest tests/test_github_ops.py tests/test_os_project_manager.py \
       tests/test_release_pipeline.py tests/test_os_learning.py \
       tests/test_robin_sync.py tests/test_os_marketing.py -v

# 136 tests covering:
# - GitHub API operations (auth, rate limiting, CRUD)
# - Project lifecycle management
# - SemVer parsing and bumping
# - Changelog and release notes generation
# - Learning and mastery tracking
# - Robin sync exclusions and branding
# - Marketing content generation
```
