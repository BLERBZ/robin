# Stage 9: Promotion

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[06-cognitive-learner|Cognitive Learner]] | [[08-advisory|Advisory]]
> Downstream: End of flow

**Purpose:** Promotes high-reliability insights (80%+ reliability, 5+ validations) to project files: CLAUDE.md, AGENTS.md, TOOLS.md, SOUL.md. Rate-limited to once per hour.
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Total log entries | 20 | healthy |
| Log size | 2.5KB | healthy |
| Last activity | 2.3h ago | healthy |
## Target Distribution (recent)

| Target | Count |
|--------|-------|
| CLAUDE.md | 20 |

## Results (recent)

| Result | Count |
|--------|-------|
| demoted | 20 |

## Recent Activity

| Time | Key | Target | Result | Reason |
|------|-----|--------|--------|--------|
| 2026-02-22T16:47:59 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T16:52:04 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T16:55:07 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T17:02:37 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T17:23:52 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T17:25:04 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T17:41:09 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T17:41:47 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T06:23:15 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T06:24:12 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T06:28:36 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T06:34:18 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T08:40:40 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T09:42:07 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T09:50:33 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T09:58:30 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T10:05:23 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T10:25:39 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T10:31:23 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-23T11:44:46 | `k1` | CLAUDE.md | demoted | reliability_degraded |

## Source Files

- `lib/promoter.py` — Core implementation
- `~/.kait/promotion_log.jsonl` — State storage
