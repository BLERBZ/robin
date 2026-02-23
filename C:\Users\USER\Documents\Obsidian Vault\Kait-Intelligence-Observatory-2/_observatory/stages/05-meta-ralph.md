# Stage 5: Meta-Ralph

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[04-memory-capture|Memory Capture]] | [[03-pipeline|Pipeline]]
> Downstream: [[06-cognitive-learner|Cognitive Learner]]

**Purpose:** Quality gate for ALL insights. Multi-dimensional scoring: actionability, novelty, reasoning, specificity, outcome-linkage, ethics. Detects primitives, tautologies, circular reasoning, and noise.
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Total roasted | 789 | healthy |
| Learnings stored | 2 | healthy |
| Pass rate (quality) | 5.8% | CRITICAL |
| Average total score | 2.0 | healthy |
## Verdict Distribution

| Verdict | Count | % |
|---------|-------|---|
| needs_work | 476 | 60.3% |
| duplicate | 254 | 32.2% |
| quality | 46 | 5.8% |
| primitive | 13 | 1.6% |

## Dimension Averages (all time)

*Each dimension scored 0-2, summed to total (0-12). Higher is better.*

| Dimension | Avg Score | Bar |
|-----------|-----------|-----|
| actionability | 0.18 | `█░░░░░░░░░` |
| novelty | 0.09 | `░░░░░░░░░░` |
| reasoning | 0.05 | `░░░░░░░░░░` |
| specificity | 0.59 | `███░░░░░░░` |
| outcome_linked | 0.08 | `░░░░░░░░░░` |
| ethics | 1.01 | `█████░░░░░` |

## Recommendations

*Auto-generated based on dimension averages below 1.5/2.0.*

- **reasoning**: Insights lack causal reasoning. Look for why/because/leads-to patterns in captures.
- **outcome_linked**: Few insights connect to measurable outcomes. Wire up more prediction-outcome pairs.

## Recent Verdicts

| Time | Source | Verdict | Score | Issues |
|------|--------|---------|-------|--------|
| 2026-02-22T15:32:43 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-22T15:32:43 | user_prompt | **duplicate** | 1 | This learning already exists |
| 2026-02-22T15:33:44 | pipeline_workflow | **needs_work** | 3 | This seems obvious or already known, Too generic |
| 2026-02-22T15:33:44 | pipeline_micro | **duplicate** | 1 | This learning already exists |
| 2026-02-22T15:33:44 | user_prompt | **quality** | 7 | No reasoning provided |
| 2026-02-22T15:37:59 | pipeline_workflow | **needs_work** | 3 | This seems obvious or already known, No reasoning provided |
| 2026-02-22T15:37:59 | pipeline_micro | **quality** | 6 | — |
| 2026-02-22T15:37:59 | pipeline_micro | **duplicate** | 1 | This learning already exists |
| 2026-02-22T15:37:59 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-22T15:37:59 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-22T15:39:14 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-22T15:39:14 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-22T15:40:14 | user_prompt | **quality** | 5 | This seems obvious or already known, No reasoning provided |
| 2026-02-22T15:41:29 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-22T15:41:29 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-22T15:41:29 | user_prompt | **duplicate** | 1 | This learning already exists |
| 2026-02-22T15:42:30 | user_prompt | **quality** | 5 | No reasoning provided |
| 2026-02-22T15:43:45 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-22T15:47:30 | pipeline_micro | **quality** | 6 | — |
| 2026-02-22T15:47:30 | pipeline_micro | **duplicate** | 1 | This learning already exists |

## Deep Dive

- [[../explore/verdicts/_index|Browse Individual Verdicts]] — score breakdowns, input text, issues

## Source Files

- `lib/meta_ralph.py` — Core implementation
- `~/.kait/meta_ralph/learnings_store.json` — State storage
- `~/.kait/meta_ralph/roast_history.json` — State storage
- `~/.kait/meta_ralph/outcome_tracking.json` — State storage
