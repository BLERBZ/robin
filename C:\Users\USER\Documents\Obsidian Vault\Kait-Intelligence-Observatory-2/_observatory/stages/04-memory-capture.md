# Stage 4: Memory Capture

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[03-pipeline|Pipeline]]
> Downstream: [[05-meta-ralph|Meta-Ralph]]

**Purpose:** Scans events for high-signal user intent (explicit markers + importance scoring). Detects domain hints and categorizes memories.
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Pending memories | 7 | healthy |
| Last capture | 3m ago | healthy |
## Category Distribution

| Category | Count |
|----------|-------|
| meta_learning | 5 |
| user_understanding | 1 |
| wisdom | 1 |

## Recent Pending Items

1. **[meta_learning]** (score: 0.55, pending)
   continue iterating on this to resolve this error: Traceback (most recent call last):
  File "/Users/rohnspringfield/vibe...
2. **[meta_learning]** (score: 0.95, auto_saved)
   <task-notification>
<task-id>a5ea48cb914496c79</task-id>
<tool-use-id>toolu_01EDQZtSnjPC2k3VKB5RQRiD</tool-use-id>
<stat...
3. **[user_understanding]** (score: 0.90, auto_saved)
   <task-notification>
<task-id>a4cb5dc5039fecba0</task-id>
<tool-use-id>toolu_01AoYqGSvQTkSsun9AXUSZwF</tool-use-id>
<stat...
4. **[wisdom]** (score: 0.70, auto_saved)
   <task-notification>
<task-id>a924fd2d8e2edcf08</task-id>
<tool-use-id>toolu_01DhcnYojAMxVJvnsJNvrQ3H</tool-use-id>
<stat...
5. **[meta_learning]** (score: 0.70, auto_saved)
   <task-notification>
<task-id>b5ce84a</task-id>
<tool-use-id>toolu_011dTWmZijjpq4QiTQk29Cw8</tool-use-id>
<output-file>/p...
6. **[meta_learning]** (score: 0.70, auto_saved)
   <task-notification>
<task-id>b9ffc31</task-id>
<tool-use-id>toolu_01EHmBvUC2gCE6upvgFh7kPj</tool-use-id>
<output-file>/p...
7. **[meta_learning]** (score: 1.00, auto_saved)
   testing pipeline flow works correctly

## Source Files

- `lib/memory_capture.py` — Core implementation
- `~/.kait/pending_memory.json` — State storage
- `~/.kait/memory_capture_state.json` — State storage
