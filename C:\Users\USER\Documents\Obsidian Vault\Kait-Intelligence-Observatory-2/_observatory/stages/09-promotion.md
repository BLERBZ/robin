# Stage 9: Promotion

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[06-cognitive-learner|Cognitive Learner]] | [[08-advisory|Advisory]]
> Downstream: End of flow

**Purpose:** Promotes high-reliability insights (80%+ reliability, 5+ validations) to project files: CLAUDE.md, AGENTS.md, TOOLS.md, SOUL.md. Rate-limited to once per hour.
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Total log entries | 14 | healthy |
| Log size | 1.8KB | healthy |
| Last activity | 34m ago | healthy |
## Target Distribution (recent)

| Target | Count |
|--------|-------|
| CLAUDE.md | 14 |

## Results (recent)

| Result | Count |
|--------|-------|
| demoted | 11 |
| promoted | 3 |

## Recent Activity

| Time | Key | Target | Result | Reason |
|------|-----|--------|--------|--------|
| 2026-02-22T11:46:22 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T11:48:33 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T12:04:50 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T12:20:22 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T12:24:49 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T14:12:19 | `reasoning:bad_assumption:File exists at expected path` | CLAUDE.md | promoted |  |
| 2026-02-22T14:12:19 | `reasoning:large_edit_on_settingsdropdown.module.cs` | CLAUDE.md | promoted |  |
| 2026-02-22T14:43:19 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T14:43:28 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T14:55:48 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T15:07:48 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T15:12:25 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T15:15:29 | `k1` | CLAUDE.md | demoted | reliability_degraded |
| 2026-02-22T15:15:48 | `self_awareness:read_failed:_file_does_not_exist._note:_` | CLAUDE.md | promoted |  |

## Source Files

- `lib/promoter.py` — Core implementation
- `~/.kait/promotion_log.jsonl` — State storage
