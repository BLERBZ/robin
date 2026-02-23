# Kait OSS Boundary (Public + Premium)

This page defines what ships in the open repo by default and what requires premium flags.

## 1) What is included in OSS core

Included by default:
- Event capture and ingest (`kaitd`, queue, event schema)
- Learning and memory stores (`cognitive_learner`, patterns, outcomes)
- Guardrails and advisory runtime (`advisory_*`, `eidos`, `kaitd` hooks)
- Output adapters for local agent workflows (`KAIT_CONTEXT.md`, `KAIT_ADVISORY.md`, `KAIT_NOTIFICATIONS.md`)
- OpenClaw + Cursor/Claude adapters
- Chip module files and schema

## 2) What is disabled by default

Kait OSS keeps the following surfaces inert unless explicitly enabled:
- X/social automation and research surfaces
- `convo`, `niche`, and `engagement` advisory branches
- Chip runtime merge/processing and engagement pulse loop
- Any direct social intent routing inside advisory retrieval

The repo still contains the chips module and files, but OSS runs with no usable runtime exposure for those premium surfaces.

## 3) Launch flags

Use both flags for chip/runtime-capable behavior:
- `KAIT_PREMIUM_TOOLS=1`
- `KAIT_CHIPS_ENABLED=1`

To keep chips permanently off in OSS, use:
- `KAIT_ADVISORY_DISABLE_CHIPS=1`

Default (safe) launch posture:
- `KAIT_PREMIUM_TOOLS` not set
- `KAIT_CHIPS_ENABLED` not set
- `KAIT_ADVISORY_DISABLE_CHIPS` unset (or set to any truthy value for hard-off)

## 4) Explicitly excluded from OSS default

- Moltbook integration/runtime
- DEPTH/Forge training and benchmark suites
- Other high-risk social tooling not needed for coding intelligence loops
- Archive/reporting folders, local runtime traces, and runtime artifact dumps are trimmed for OSS hygiene
- Retained launch directories: `benchmarks/` (compat entrypoints + test fixtures) and `.kait/` state are documented as out-of-band launch data.

These excluded surfaces are tracked in `docs/OPEN_CORE_FREEMIUM_MODEL.md` and are intentionally marked for premium/private packaging.
