# Stage 7: EIDOS

> Part of the [[../flow|Intelligence Flow]]
> Upstream: [[03-pipeline|Pipeline]] | [[11-predictions|Predictions]]
> Downstream: [[08-advisory|Advisory]]

**Purpose:** Episodic intelligence with mandatory predict-then-evaluate loop. Stores episodes (session-scoped), steps (prediction/outcome/evaluation triples), and distillations (extracted rules).
## Health

| Metric | Value | Status |
|--------|-------|--------|
| Database | exists | healthy |
| DB size | 764.0KB | healthy |
| Episodes | 16 | healthy |
| Steps | 920 | healthy |
| Distillations | 21 | healthy |
| Active episodes | 1 | healthy |
| Active steps | 1 | healthy |
## Recent Distillations

1. **[heuristic]** (confidence: 0.9637)
   When Edit kait_ai_sidekick.py (replace '# Run the sidekick     sidekick ='), try: Modify kait_ai_sidekick.py: '# Warn early if --avatar-gui but 
2. **[policy]** (confidence: 0.04)
   Always verify functionality - Complet' failed with approach: TaskUp because it's important to verify functionality - complet' failed with approach: ta
3. **[sharp_edge]** (confidence: 0.7)
   Watch out when testing: it's important to verify functionality - complet' failed with approach: taskupdate. need different
4. **[heuristic]** (confidence: 0.4)
   When continue iterating on this for, use Read. This approach succeeded 8 times.
5. **[sharp_edge]** (confidence: 0.7)
   Watch out when feature addition: Request 'create new functionality - <ta' resolved by: TaskUpdate
6. **[heuristic]** (confidence: 0.9039)
   When feature addition, use TaskUpdate. This approach succeeded 2 times.
7. **[heuristic]** (confidence: 0.4)
   When bug fixing, use Read. This approach succeeded 6 times.
8. **[sharp_edge]** (confidence: 0.35)
   Inconsistent results for continue iterating on this for: 58% success across 12 attempts. Context matters — verify assumptions before proceeding.
9. **[heuristic]** (confidence: 0.45)
   When tasknotification taskidb, use Bash. This approach succeeded 8 times.
10. **[heuristic]** (confidence: 0.9943)
   When Edit sidekick_setup.md (replace '| `/correct <text>` | Correct the last r'), try: Modify sidekick_setup.md: '| `/export [name]` | Export conver

## Source Files

- `lib/eidos/ (aggregator.py, distiller.py, store.py, models.py)` — Core implementation
- `~/.kait/eidos.db` — State storage
- `~/.kait/eidos_active_episodes.json` — State storage
- `~/.kait/eidos_active_steps.json` — State storage
