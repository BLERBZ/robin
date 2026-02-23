---
type: "kait-decisions-index"
total: 1189
exported: 119
limit: 200
emit_rate: 5.9
---

# Advisory Decision Ledger (119/1189)

> [[../flow|Intelligence Flow]] | [[../stages/08-advisory|Stage 8: Advisory]]

**Emit rate (recent):** 5.9% (7/119) | **Blocked:** 112

*Showing most recent 119. Increase `explore_decisions_max` in tuneables to see more.*

## Decision Outcomes

| Outcome | Count | % |
|---------|-------|---|
| **blocked** | 112 | 94.1% |
| **emitted** | 7 | 5.9% |

## Delivery Routes

| Route | Count |
|-------|-------|
| `packet_relaxed` | 83 |
| `live` | 28 |
| `packet_exact` | 8 |

## Advisory Sources Used

| Source | Items Retrieved |
|--------|----------------|
| **eidos** | 134 |
| **semantic** | 134 |
| **cognitive** | 5 |
| **baseline** | 5 |
| **prefetch** | 4 |

## Suppression Reasons

*Why advice was blocked from delivery*

| Reason | Count |
|--------|-------|
| generic Read advice while already Reading | 20 |
| tool Bash on cooldown | 10 |
| budget exhausted (2 max) | 7 |
| shown 24s ago (TTL 600s) | 6 |
| shown 35s ago (TTL 600s) | 6 |
| shown 38s ago (TTL 600s) | 6 |
| shown 19s ago (TTL 600s) | 5 |
| shown 22s ago (TTL 600s) | 5 |
| shown 25s ago (TTL 600s) | 5 |
| shown 23s ago (TTL 600s) | 5 |
| shown 15s ago (TTL 600s) | 4 |
| shown 11s ago (TTL 600s) | 4 |
| shown 26s ago (TTL 600s) | 4 |
| shown 28s ago (TTL 600s) | 4 |
| shown 12s ago (TTL 600s) | 4 |
| shown 36s ago (TTL 600s) | 4 |
| shown 40s ago (TTL 600s) | 4 |
| shown 17s ago (TTL 600s) | 3 |
| shown 18s ago (TTL 600s) | 3 |
| shown 7s ago (TTL 600s) | 3 |
| shown 21s ago (TTL 600s) | 3 |
| shown 2s ago (TTL 600s) | 3 |
| shown 32s ago (TTL 600s) | 3 |
| shown 110s ago (TTL 600s) | 3 |
| shown 4s ago (TTL 600s) | 3 |
| shown 20s ago (TTL 600s) | 3 |
| shown 6s ago (TTL 600s) | 2 |
| shown 29s ago (TTL 600s) | 2 |
| shown 34s ago (TTL 600s) | 2 |
| shown 108s ago (TTL 600s) | 2 |
| shown 84s ago (TTL 600s) | 2 |
| shown 138s ago (TTL 600s) | 2 |
| shown 271s ago (TTL 600s) | 2 |
| shown 561s ago (TTL 600s) | 2 |
| shown 33s ago (TTL 600s) | 2 |
| shown 53s ago (TTL 600s) | 2 |
| shown 56s ago (TTL 600s) | 2 |
| shown 61s ago (TTL 600s) | 2 |
| shown 8s ago (TTL 600s) | 1 |
| shown 9s ago (TTL 600s) | 1 |
| shown 3s ago (TTL 600s) | 1 |
| shown 114s ago (TTL 600s) | 1 |
| shown 143s ago (TTL 600s) | 1 |
| shown 145s ago (TTL 600s) | 1 |
| shown 146s ago (TTL 600s) | 1 |
| shown 149s ago (TTL 600s) | 1 |
| shown 102s ago (TTL 600s) | 1 |
| shown 152s ago (TTL 600s) | 1 |
| shown 156s ago (TTL 600s) | 1 |
| shown 159s ago (TTL 600s) | 1 |
| shown 236s ago (TTL 600s) | 1 |
| shown 276s ago (TTL 600s) | 1 |
| shown 392s ago (TTL 600s) | 1 |
| shown 414s ago (TTL 600s) | 1 |
| shown 481s ago (TTL 600s) | 1 |
| shown 10s ago (TTL 600s) | 1 |
| shown 545s ago (TTL 600s) | 1 |
| shown 550s ago (TTL 600s) | 1 |
| shown 37s ago (TTL 600s) | 1 |
| shown 43s ago (TTL 600s) | 1 |
| shown 49s ago (TTL 600s) | 1 |
| shown 50s ago (TTL 600s) | 1 |
| shown 52s ago (TTL 600s) | 1 |
| shown 54s ago (TTL 600s) | 1 |
| shown 57s ago (TTL 600s) | 1 |
| shown 58s ago (TTL 600s) | 1 |
| shown 60s ago (TTL 600s) | 1 |
| shown 65s ago (TTL 600s) | 1 |
| shown 67s ago (TTL 600s) | 1 |
| shown 92s ago (TTL 600s) | 1 |
| shown 74s ago (TTL 600s) | 1 |
| shown 142s ago (TTL 600s) | 1 |
| shown 13s ago (TTL 600s) | 1 |

## Decisions by Tool

| Tool | Decisions |
|------|-----------|
| Bash | 43 |
| Read | 35 |
| Grep | 18 |
| TaskUpdate | 8 |
| Edit | 5 |
| TaskCreate | 4 |
| Write | 4 |
| Task | 1 |
| AskUserQuestion | 1 |

## Recent Decisions

| Time | Tool | Outcome | Route | Selected | Suppressed | Sources |
|------|------|---------|-------|----------|------------|---------|
| 2026-02-22 15:47:01 | AskUserQuestion | **blocked** | `packet_relaxed` | 0 | 1 | semantic:1 |
| 2026-02-22 15:46:53 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | semantic:1 |
| 2026-02-22 15:46:47 | Edit | **emitted** | `packet_relaxed` | 1 | 0 | semantic:1 |
| 2026-02-22 15:46:38 | Read | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:46:15 | Bash | **blocked** | `packet_exact` | 0 | 1 | prefetch:1 |
| 2026-02-22 15:45:48 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:23 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:21 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:17 | Read | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:17 | Read | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:17 | Read | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:14 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:13 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:13 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:12 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:10 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:10 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:09 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:09 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:06 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:06 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:45:00 | Bash | **emitted** | `packet_exact` | 1 | 0 | prefetch:1 |
| 2026-02-22 15:45:00 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:57 | Read | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:57 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:56 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:56 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:53 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:53 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:52 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:50 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:50 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:49 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:49 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:45 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:45 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:44 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:44 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:41 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:40 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:40 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:37 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:37 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:36 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:36 | Grep | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:34 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:33 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:31 | Task | **blocked** | `packet_exact` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:21 | Bash | **blocked** | `packet_relaxed` | 0 | 1 | eidos:1 |
| 2026-02-22 15:44:16 | Bash | **emitted** | `packet_relaxed` | 1 | 0 | eidos:1 |
