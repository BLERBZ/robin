# Stage 5: Meta-Ralph

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[04-memory-capture|Memory Capture]] | [[03-pipeline|Pipeline]]
> Downstream: [[06-cognitive-learner|Cognitive Learner]]

**Purpose:** Quality gate for ALL insights. Multi-dimensional scoring: actionability, novelty, reasoning, specificity, outcome-linkage, ethics. Detects primitives, tautologies, circular reasoning, and noise.
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Total roasted | 521 | healthy |
| Learnings stored | 2 | healthy |
| Pass rate (quality) | 3.5% | CRITICAL |
| Average total score | 1.88 | healthy |
## Verdict Distribution

| Verdict | Count | % |
|---------|-------|---|
| needs_work | 300 | 57.6% |
| duplicate | 155 | 29.8% |
| primitive | 48 | 9.2% |
| quality | 18 | 3.5% |

## Dimension Averages (all time)

*Each dimension scored 0-2, summed to total (0-12). Higher is better.*

| Dimension | Avg Score | Bar |
|-----------|-----------|-----|
| actionability | 0.13 | `█░░░░░░░░░` |
| novelty | 0.1 | `░░░░░░░░░░` |
| reasoning | 0.04 | `░░░░░░░░░░` |
| specificity | 0.56 | `███░░░░░░░` |
| outcome_linked | 0.02 | `░░░░░░░░░░` |
| ethics | 1.02 | `█████░░░░░` |

## Recommendations

*Auto-generated based on dimension averages below 1.5/2.0.*

- **outcome_linked**: Few insights connect to measurable outcomes. Wire up more prediction-outcome pairs.
- **reasoning**: Insights lack causal reasoning. Look for why/because/leads-to patterns in captures.

## Recent Verdicts

| Time | Source | Verdict | Score | Issues |
|------|--------|---------|-------|--------|
| 2026-02-23T11:45:45 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-23T11:45:45 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-23T11:51:52 | pipeline_workflow | **needs_work** | 3 | This seems obvious or already known, Too generic |
| 2026-02-23T11:51:52 | pipeline_workflow | **needs_work** | 3 | This seems obvious or already known, No reasoning provided |
| 2026-02-23T11:51:52 | pipeline_micro | **duplicate** | 1 | This learning already exists |
| 2026-02-23T11:51:52 | pipeline_micro | **duplicate** | 1 | This learning already exists |
| 2026-02-23T11:51:52 | pipeline_micro | **duplicate** | 1 | This learning already exists |
| 2026-02-23T11:51:52 | user_prompt | **duplicate** | 1 | This learning already exists |
| 2026-02-23T11:51:52 | user_prompt | **needs_work** | 3 | This seems obvious or already known, No reasoning provided |
| 2026-02-23T11:51:52 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-23T11:51:52 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-23T11:51:52 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-23T11:51:52 | user_prompt | **duplicate** | 1 | This learning already exists |
| 2026-02-23T11:51:52 | user_prompt | **duplicate** | 1 | This learning already exists |
| 2026-02-23T11:51:52 | user_prompt | **duplicate** | 1 | This learning already exists |
| 2026-02-23T11:51:52 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-23T11:51:52 | user_prompt | **needs_work** | 3 | No actionable guidance, This seems obvious or already known |
| 2026-02-23T11:51:52 | user_prompt | **primitive** | 1 | No actionable guidance, This seems obvious or already known |
| 2026-02-23T11:51:52 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |
| 2026-02-23T11:51:52 | user_prompt | **needs_work** | 2 | No actionable guidance, This seems obvious or already known |

## Deep Dive

- [[../explore/verdicts/_index|Browse Individual Verdicts]] — score breakdowns, input text, issues

## Source Files

- `lib/meta_ralph.py` — Core implementation
- `~/.kait/meta_ralph/learnings_store.json` — State storage
- `~/.kait/meta_ralph/roast_history.json` — State storage
- `~/.kait/meta_ralph/outcome_tracking.json` — State storage
