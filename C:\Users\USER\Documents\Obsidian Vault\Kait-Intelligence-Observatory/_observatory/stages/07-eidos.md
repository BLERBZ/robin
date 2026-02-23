# Stage 7: EIDOS

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[03-pipeline|Pipeline]] | [[11-predictions|Predictions]]
> Downstream: [[08-advisory|Advisory]]

**Purpose:** Episodic intelligence with mandatory predict-then-evaluate loop. Stores episodes (session-scoped), steps (prediction/outcome/evaluation triples), and distillations (extracted rules).
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Database | exists | healthy |
| DB size | 576.0KB | healthy |
| Episodes | 45 | healthy |
| Steps | 810 | healthy |
| Distillations | 4 | healthy |
| Active episodes | 1 | healthy |
| Active steps | 0 | healthy |
## Recent Distillations

1. **[policy]** (confidence: 0.7)
   Policy: Inspect ensure_kait.bat
2. **[anti_pattern]** (confidence: 0.7)
   When repeated Read operations attempts fail without progress, step back and try a different approach
3. **[policy]** (confidence: 0.7)
   Policy: Search codebase for 'Mandatory Creative Kait'
4. **[heuristic]** (confidence: 0.7)
   When budget is high without progress, simplify scope

## Source Files

- `lib/eidos/ (aggregator.py, distiller.py, store.py, models.py)` — Core implementation
- `~/.kait/eidos.db` — State storage
- `~/.kait/eidos_active_episodes.json` — State storage
- `~/.kait/eidos_active_steps.json` — State storage
