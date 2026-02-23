# Stage 3: Pipeline

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[02-queue|Queue]]
> Downstream: [[04-memory-capture|Memory Capture]] | [[05-meta-ralph|Meta-Ralph]] | [[07-eidos|EIDOS]] | [[10-chips|Chips]] | [[11-predictions|Predictions]]

**Purpose:** Processes event batches in priority order (HIGH > MEDIUM > LOW). Extracts patterns, tool effectiveness, error patterns, and session workflows.
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Events processed | 8,484 | healthy |
| Insights created | 3 | healthy |
| Processing rate | 2747.3 ev/s | healthy |
| Last batch size | 300 | healthy |
| Empty cycles | 3 | healthy |
| Last cycle | 3m ago | healthy |
## Recent Cycles

| Duration | Events | Insights | Patterns | Rate | Health |
|----------|--------|----------|----------|------|--------|
| 4ms | 35 | 0 | 0 | 8879 ev/s | healthy |
| 4ms | 10 | 0 | 0 | 2747 ev/s | healthy |
| 1ms | 0 | 0 | 0 | 0 ev/s | healthy |
| 1ms | 0 | 0 | 0 | 0 ev/s | healthy |
| 0ms | 0 | 0 | 0 | 0 ev/s | healthy |

## Source Files

- `lib/pipeline.py + lib/bridge_cycle.py` — Core implementation
- `~/.kait/pipeline_state.json` — State storage
- `~/.kait/pipeline_metrics.json` — State storage
