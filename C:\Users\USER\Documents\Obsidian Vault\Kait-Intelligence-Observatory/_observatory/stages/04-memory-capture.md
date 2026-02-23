# Stage 4: Memory Capture

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[03-pipeline|Pipeline]]
> Downstream: [[05-meta-ralph|Meta-Ralph]]

**Purpose:** Scans events for high-signal user intent (explicit markers + importance scoring). Detects domain hints and categorizes memories.
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Pending memories | 1 | healthy |
| Last capture | 2.3h ago | healthy |
## Category Distribution

| Category | Count |
|----------|-------|
| meta_learning | 1 |

## Recent Pending Items

1. **[meta_learning]** (score: 1.00, auto_saved)
   testing pipeline flow works correctly

## Source Files

- `lib/memory_capture.py` — Core implementation
- `~/.kait/pending_memory.json` — State storage
- `~/.kait/memory_capture_state.json` — State storage
