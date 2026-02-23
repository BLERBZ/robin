# Stage 3: Pipeline

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[02-queue|Queue]]
> Downstream: [[04-memory-capture|Memory Capture]] | [[05-meta-ralph|Meta-Ralph]] | [[07-eidos|EIDOS]] | [[10-chips|Chips]] | [[11-predictions|Predictions]]

**Purpose:** Processes event batches in priority order (HIGH > MEDIUM > LOW). Extracts patterns, tool effectiveness, error patterns, and session workflows.
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Events processed | 14,430 | healthy |
| Insights created | 2 | healthy |
| Processing rate | 50031.3 ev/s | healthy |
| Last batch size | 1,000 | healthy |
| Empty cycles | 2 | healthy |
| Last cycle | 2.2h ago | healthy |
## Recent Cycles

| Duration | Events | Insights | Patterns | Rate | Health |
|----------|--------|----------|----------|------|--------|
| 0ms | 0 | 0 | 0 | 0 ev/s | healthy |
| 20ms | 1000 | 0 | 0 | 50896 ev/s | critical |
| 11ms | 559 | 0 | 0 | 50031 ev/s | critical |
| 0ms | 0 | 0 | 0 | 0 ev/s | healthy |
| 0ms | 0 | 0 | 0 | 0 ev/s | healthy |

## Source Files

- `lib/pipeline.py + lib/bridge_cycle.py` — Core implementation
- `~/.kait/pipeline_state.json` — State storage
- `~/.kait/pipeline_metrics.json` — State storage
