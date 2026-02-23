# Stage 8: Advisory

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[06-cognitive-learner|Cognitive Learner]] | [[07-eidos|EIDOS]] | [[10-chips|Chips]]
> Downstream: [[09-promotion|Promotion]]

**Purpose:** Just-in-time advice engine. Retrieves from Cognitive, EIDOS, Chips, and Mind. RRF fusion + cross-encoder reranking. Tracks implicit feedback (tool success/failure after advice).
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Total advice given | 423 | healthy |
| Followed (effectiveness) | 34 (8.0%) | WARNING |
| Helpful | 34 | healthy |
| Decision emit rate | 5.9% | WARNING |
| Implicit follow rate | 100.0% | healthy |
| Advice log entries | ~2,066 | healthy |
## Decision Ledger Summary

*Every advisory event is recorded: emitted (advice given), suppressed (filtered out), or blocked.*

| Outcome | Count | % |
|---------|-------|---|
| **blocked** | 112 | 94.1% |
| **emitted** | 7 | 5.9% |

## Implicit Feedback by Tool

*When advice is given before a tool call, the tool's success/failure signals whether advice was followed.*

| Tool | Followed | Ignored | Total | Follow Rate |
|------|----------|---------|-------|-------------|
| Bash | 68 | 0 | 70 | 100.0% |
| Read | 58 | 0 | 58 | 100.0% |
| TaskUpdate | 21 | 0 | 21 | 100.0% |
| Grep | 21 | 0 | 21 | 100.0% |
| TaskCreate | 15 | 0 | 15 | 100.0% |
| Edit | 7 | 0 | 7 | 100.0% |
| Task | 5 | 0 | 5 | 100.0% |
| TaskOutput | 2 | 0 | 2 | 100.0% |
| TaskList | 1 | 0 | 1 | 100.0% |

## Source Effectiveness

| Source | Total | Helpful | Rate |
|--------|-------|---------|------|
| cognitive | 219 | 4 | 1.8% |
| eidos | 194 | 1 | 0.5% |
| prefetch | 181 | 3 | 1.7% |
| semantic | 154 | 2 | 1.3% |
| advisor | 62 | 1 | 1.6% |
| baseline | 16 | 0 | 0.0% |

## Recent Advice Given

1. **task** (2026-02-22T15:47:30)
   - [eidos] [EIDOS HEURISTIC] When Edit sidekick_setup.md (replace '| `/correct <text>` | Correct the last r'),
   - [eidos] [EIDOS HEURISTIC] When TaskUpdate operation: TaskUpdate
   - [eidos] [EIDOS HEURISTIC] When tasknotification taskidb: Bash. This approach succeeded 8 times

## Deep Dive

- [[../explore/decisions/_index|Advisory Decision Ledger]] — emit/suppress/block decisions
- [[../explore/feedback/_index|Implicit Feedback Loop]] — per-tool follow rates
- [[../explore/advisory/_index|Advisory Effectiveness]] — source breakdown + recent advice
- [[../explore/routing/_index|Retrieval Routing]] — route distribution and decisions

## Source Files

- `lib/advisor.py` — Core implementation
- `~/.kait/advisor/advice_log.jsonl` — State storage
- `~/.kait/advisor/effectiveness.json` — State storage
- `~/.kait/advisor/metrics.json` — State storage
- `~/.kait/advisor/implicit_feedback.jsonl` — State storage
- `~/.kait/advisor/retrieval_router.jsonl` — State storage
- `~/.kait/advisory_decision_ledger.jsonl` — State storage
