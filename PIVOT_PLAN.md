# Kait OS Sidekick Pivot Plan

## Overview

Kait is being restructured as the AI Agent and Open Source Sidekick for Rohn, the builder/founder of BLERBZ.com. This document outlines the architecture, roadmap, and implementation details for the pivot.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    KAIT OS SIDEKICK                       │
│              Text & Audio/Voice-Only Interface             │
├──────────────┬──────────────┬──────────────┬─────────────┤
│   GitHub Ops │  OS Project  │   Release    │  OS Learning │
│  (API Layer) │   Manager    │   Pipeline   │   Engine     │
├──────────────┼──────────────┼──────────────┼─────────────┤
│              │  Robin Sync  │  OS Marketing│             │
│              │   System     │  & Promotion │             │
├──────────────┴──────────────┴──────────────┴─────────────┤
│              EXISTING KAIT INTELLIGENCE                    │
│  Events → Queue → Bridge → Learning → Advisory → Output   │
│  Sidekick: TTS, Agents, Reasoning, Reflection             │
└─────────────────────────────────────────────────────────┘
```

## New Modules

### 1. lib/github_ops.py — GitHub API Operations
- Repository CRUD (create, configure, delete)
- Issue and PR management (create, label, comment, merge)
- Release management (create, tag, publish)
- Branch management and protection rules
- Webhook listener registration
- Rate limiting with exponential backoff
- Token-based authentication with scope validation

### 2. lib/os_project_manager.py — Open Source Project Lifecycle
- Project initialization (README, LICENSE, .gitignore, boilerplate)
- Development tracking (issues, milestones, boards)
- Code review workflows
- Dependency management and security audits
- Community health files (CONTRIBUTING, CODE_OF_CONDUCT)
- Project viability assessment

### 3. lib/release_pipeline.py — Automated Release System
- Semantic versioning (SemVer) management
- Automated changelog generation from commits/PRs
- GitHub Release creation with assets
- Tag management
- Registry publishing preparation (PyPI, npm)
- Release notes generation (human-readable)

### 4. lib/os_learning.py — OS Best Practices Engine
- Project metrics analysis (stars, forks, issues, PRs)
- Best practices extraction from successful OS projects
- Mastery progression tracking
- Contributor engagement benchmarking
- Feedback loop integration with cognitive_learner

### 5. lib/robin_sync.py — Robin Synchronization
- Kait→Robin code synchronization pipeline
- OS suitability review (strip proprietary elements)
- Documentation enhancement for contributors
- BLERBZ branding enforcement
- Automated diff review before sync

### 6. lib/os_marketing.py — Promotion & Marketing
- Release announcement generation
- Social media post creation
- Blog draft generation
- README badge management
- Contributor highlights
- Marketing analytics tracking

## CLI Extensions (kait/cli.py)

New commands:
- `kait os new <name>` — Initialize a new OS project
- `kait os status [project]` — Show OS project status
- `kait os release <project> <version>` — Create a release
- `kait os review <project>` — Run code review
- `kait os learn` — Run learning cycle
- `kait robin sync` — Sync Kait→Robin
- `kait robin status` — Robin sync status
- `kait os promote <project>` — Generate promotion materials

## Configuration

### Environment Variables (new)
```
# GitHub Integration
KAIT_GITHUB_TOKEN=ghp_xxx
KAIT_GITHUB_ORG=blerbz
KAIT_GITHUB_ALLOWED_REPOS=robin,kait-intel

# BLERBZ Branding
KAIT_BLERBZ_NAME=BLERBZ LLC
KAIT_BLERBZ_URL=https://blerbz.com
KAIT_BLERBZ_LICENSE=MIT

# Robin Sync
KAIT_ROBIN_REPO=blerbz/robin
KAIT_ROBIN_SYNC_BRANCH=main
KAIT_ROBIN_AUTO_SYNC=false
```

## Phased Implementation

### Phase 1: Foundation (Current Sprint)
- [x] Architecture plan
- [ ] GitHub Operations module
- [ ] OS Project Manager
- [ ] Release Pipeline
- [ ] CLI extensions

### Phase 2: Intelligence (Sprint 2)
- [ ] OS Learning Engine
- [ ] Robin Sync System
- [ ] OS Marketing module
- [ ] GitHub Actions workflows

### Phase 3: Testing & QA (Sprint 3)
- [ ] Unit tests for all modules
- [ ] Integration tests
- [ ] End-to-end project lifecycle test
- [ ] Robin initialization and sync test

### Phase 4: Launch (Sprint 4)
- [ ] Robin repository creation
- [ ] Documentation updates
- [ ] Sample OS projects (3 minimum)
- [ ] Performance validation

## Success Metrics
- Kait manages 3+ OS projects end-to-end
- Robin launched with >90% code parity
- Response times: <2s text, <5s audio
- 99% uptime for background services

## Security Considerations
- GitHub token scoped to BLERBZ org only
- Repository allowlist enforcement
- Rate limiting on all GitHub API calls
- No secrets in sync pipeline
- Audit logging for all OS operations
