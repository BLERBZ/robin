# Kait Intelligence Observatory

> Last generated: 2026-02-23 14:03:56
> Pipeline: 14,430 events processed, 2 insights created

## System Health

| Metric | Value | Status |
|--------|-------|--------|
| Queue depth | ~1,145 pending | healthy |
| Last pipeline cycle | 2.2h ago | CRITICAL |
| Processing rate | 50031.3 ev/s | healthy |
| Events processed | 14,430 | healthy |
| Insights created | 2 | healthy |
| Pending memories | 1 | healthy |
| Meta-Ralph roasted | 521 | healthy |
| Meta-Ralph pass rate | 3.5% | CRITICAL |
| Meta-Ralph avg score | 1.88 | healthy |
| Cognitive insights | 4 | healthy |
| EIDOS episodes | 45 | healthy |
| EIDOS distillations | 4 | healthy |
| Advisory given | 1 | healthy |
| Advisory followed | 0.0% | healthy |
| Advisory emit rate | 68.8% | healthy |
| Implicit follow rate | 100.0% | healthy |
| Promotion log entries | 20 | healthy |
| Active chips | 0 | healthy |

## Intelligence Flow

```mermaid
flowchart TD
    A["`**Event Capture**
    hooks/observe.py
    _Last: 2.2h ago_`"]
    --> B["`**Queue**
    ~1,145 pending
    _1.1MB_`"]

    B --> C["`**Pipeline**
    14,430 processed
    _50031.3 ev/s_`"]

    C --> D["`**Memory Capture**
    1 pending
    _Importance scoring_`"]

    D --> E{"`**Meta-Ralph**
    Quality Gate
    _521 roasted_`"}

    E -->|pass| F["`**Cognitive Learner**
    4 insights
    _1 categories_`"]

    E -->|reject| X["`**Rejected**
    _Below threshold_`"]

    C --> G["`**EIDOS**
    45 episodes
    _4 distillations_`"]

    F --> H["`**Advisory**
    1 given
    _0.0% followed_`"]

    G --> H

    H --> I["`**Promotion**
    20 log entries
    _CLAUDE.md + targets_`"]

    C --> J["`**Chips**
    0 active modules
    _0B_`"]

    J --> H

    C --> K["`**Predictions**
    145 outcomes
    _Surprise tracking_`"]

    K --> G

    L["`**Tuneables**
    27 sections
    _Hot-reload_`"]
    -.->|configures| E
    L -.->|configures| H

    style X fill:#4a2020,stroke:#ff6666,color:#ff9999
    style E fill:#2a3a2a,stroke:#66cc66,color:#88ee88
```

## Stage Detail Pages

1. [[stages/01-event-capture|Event Capture]] — Hook integration, session tracking, predictions
2. [[stages/02-queue|Queue]] — Event buffering, overflow, compaction
3. [[stages/03-pipeline|Pipeline]] — Batch processing, priority ordering, learning yield
4. [[stages/04-memory-capture|Memory Capture]] — Importance scoring, domain detection, pending items
5. [[stages/05-meta-ralph|Meta-Ralph]] — Quality gate, roast verdicts, noise filtering
6. [[stages/06-cognitive-learner|Cognitive Learner]] — Insight store, categories, reliability tracking
7. [[stages/07-eidos|EIDOS]] — Episodes, steps, distillations, predict-evaluate loop
8. [[stages/08-advisory|Advisory]] — Retrieval, ranking, emission, effectiveness feedback
9. [[stages/09-promotion|Promotion]] — Target files, criteria, promotion log
10. [[stages/10-chips|Chips]] — Domain modules, per-chip activity
11. [[stages/11-predictions|Predictions]] — Outcomes, links, surprise tracking
12. [[stages/12-tuneables|Tuneables]] — Configuration, hot-reload, all sections

## How Data Flows

- An **event** enters via [[stages/01-event-capture|Event Capture]] and lands in the [[stages/02-queue|Queue]]
- The [[stages/03-pipeline|Pipeline]] processes batches, feeding [[stages/04-memory-capture|Memory Capture]]
- [[stages/05-meta-ralph|Meta-Ralph]] gates every insight before it enters [[stages/06-cognitive-learner|Cognitive Learner]]
- [[stages/08-advisory|Advisory]] retrieves from [[stages/06-cognitive-learner|Cognitive Learner]], [[stages/07-eidos|EIDOS]], and [[stages/10-chips|Chips]]
- High-confidence insights get [[stages/09-promotion|promoted]] to CLAUDE.md
- [[stages/11-predictions|Predictions]] close the loop: predict, observe, evaluate, learn

## Quick Links

- [[explore/_index|Explore Individual Items]] — browse cognitive insights, distillations, episodes, verdicts
- [[../watchtower|Advisory Watchtower]] — existing advisory deep-dive
- [[../packets/index|Advisory Packet Catalog]] — existing packet view
