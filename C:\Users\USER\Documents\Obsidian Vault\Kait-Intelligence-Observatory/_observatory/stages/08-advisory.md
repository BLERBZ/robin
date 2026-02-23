# Stage 8: Advisory

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[06-cognitive-learner|Cognitive Learner]] | [[07-eidos|EIDOS]] | [[10-chips|Chips]]
> Downstream: [[09-promotion|Promotion]]

**Purpose:** Just-in-time advice engine. Retrieves from Cognitive, EIDOS, Chips, and Mind. RRF fusion + cross-encoder reranking. Tracks implicit feedback (tool success/failure after advice).
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Total advice given | 1 | healthy |
| Followed (effectiveness) | 0 (0.0%) | WARNING |
| Helpful | 0 | healthy |
| Decision emit rate | 68.8% | healthy |
| Implicit follow rate | 100.0% | healthy |
| Advice log entries | ~492 | healthy |
## Decision Ledger Summary

*Every advisory event is recorded: emitted (advice given), suppressed (filtered out), or blocked.*

| Outcome | Count | % |
|---------|-------|---|
| **emitted** | 110 | 68.8% |
| **blocked** | 50 | 31.2% |

## Implicit Feedback by Tool

*When advice is given before a tool call, the tool's success/failure signals whether advice was followed.*

| Tool | Followed | Ignored | Total | Follow Rate |
|------|----------|---------|-------|-------------|
| Edit | 35 | 0 | 35 | 100.0% |
| Bash | 32 | 0 | 33 | 100.0% |
| TaskList | 2 | 0 | 2 | 100.0% |

## Source Effectiveness

| Source | Total | Helpful | Rate |
|--------|-------|---------|------|
| cognitive | 345 | 0 | 0.0% |
| advisor | 340 | 6 | 1.8% |
| prefetch | 72 | 1 | 1.4% |
| baseline | 2 | 0 | 0.0% |

## Recent Advice Given

1. **Edit** (2026-02-23T06:23:13)
   - [semantic] Read failed 5/112 times (96% success rate). Most common: File content (39149 tokens) exceeds maximum

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
