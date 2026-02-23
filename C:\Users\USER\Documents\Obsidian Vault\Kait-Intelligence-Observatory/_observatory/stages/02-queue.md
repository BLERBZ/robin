# Stage 2: Queue

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[01-event-capture|Event Capture]]
> Downstream: [[03-pipeline|Pipeline]]

**Purpose:** Buffers events from hooks for batch processing. Uses append-only JSONL with overflow sidecar for lock contention.
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Estimated pending | ~1,145 | healthy |
| Events file size | 1.1MB | healthy |
| Head bytes | 1,128,500 | healthy |
| Overflow active | no | healthy |
| Last write | 2.3h ago | healthy |
## Source Files

- `lib/queue.py` — Core implementation
- `~/.kait/queue/events.jsonl` — State storage
- `~/.kait/queue/state.json` — State storage
- `~/.kait/queue/events.overflow.jsonl` — State storage
