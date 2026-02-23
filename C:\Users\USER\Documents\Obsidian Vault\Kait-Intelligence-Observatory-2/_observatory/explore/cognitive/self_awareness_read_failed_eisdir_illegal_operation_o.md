---
type: "kait-cognitive-insight"
key: "self_awareness:read_failed:_eisdir:_illegal_operation_o"
category: "self_awareness"
reliability: 0.355
validations: 144
contradictions: 262
confidence: 0.99
promoted: false
promoted_to: "none"
source: "pipeline_macro"
created_at: "2026-02-22T13:20:28.930419"
---

# self_awareness:read_failed:_eisdir:_illegal_operation_o

> Back to [[_index|Cognitive Index]] | [[../flow|Intelligence Flow]]

## Insight

Read failed: EISDIR: illegal operation on a directory, read '/Users/rohnspringfield/kait-intel/lib/pattern_detection

## Metadata

| Field | Value |
|-------|-------|
| Category | self_awareness |
| Reliability | 35% |
| Validations | 144 |
| Contradictions | 262 |
| Confidence | 0.990 |
| Source | pipeline_macro |
| Promoted | no |
| Advisory readiness | 0.652 |
| Created | 2026-02-22T13:20:28.930419 |
| Last validated | 2026-02-22T15:46:38.754264 |

## Evidence (10 items)

1. `implicit_feedback:success:Edit`
2. `tool=Edit success=True`
3. `micro:single_failure:Read`
4. `implicit_feedback:success:Glob`
5. `tool=Glob success=True`
6. `tool=Task success=True`
7. `Outcome: Edit success: /Users/rohnspringfield/kait-intel/docs/sidekick_setup.md`
8. `Outcome: Edit success: /Users/rohnspringfield/kait-intel/tests/test_sidekick.py`
9. `Outcome: Edit success: /Users/rohnspringfield/kait-intel/kait_ai_sidekick.py`
10. `<task-notification> <task-id>a5ea48cb914496c79</task-id> <tool-use-id>toolu_01EDQZtSnjPC2k3VKB5RQRiD</tool-use-id> <status>completed</status> <summary>Agent "Add LLM retry with context trim" completed`

## Counter-Examples (3)

1. `implicit_feedback:failure:Bash`
2. `tool=Bash success=False`
3. `Tool Bash failed despite advice: Exit code 1
Traceback (most recent call last):
  File "<string>", line 38, in <module>
KeyError: 'va`
