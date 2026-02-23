---
type: "kait-cognitive-insight"
key: "reasoning:bad_assumption:File exists at expected path"
category: "wisdom"
reliability: 1.0
validations: 173
contradictions: 0
confidence: 0.99
promoted: true
promoted_to: "CLAUDE.md"
source: ""
created_at: "2026-02-22T13:19:56.593581"
---

# reasoning:bad_assumption:File exists at expected path

> Back to [[_index|Cognitive Index]] | [[../flow|Intelligence Flow]]

## Insight

Assumption 'File exists at expected path' often wrong. Reality: Use Glob to search for files before operating on them

## Metadata

| Field | Value |
|-------|-------|
| Category | wisdom |
| Reliability | 100% |
| Validations | 173 |
| Contradictions | 0 |
| Confidence | 0.990 |
| Source |  |
| Promoted | yes |
| Promoted to | CLAUDE.md |
| Advisory readiness | 0.260 |
| Created | 2026-02-22T13:19:56.593581 |
| Last validated | 2026-02-22T15:51:35.118559 |

## Evidence (10 items)

1. `implicit_feedback:success:Bash`
2. `<task-notification> <task-id>a924fd2d8e2edcf08</task-id> <tool-use-id>toolu_01DhcnYojAMxVJvnsJNvrQ3H</tool-use-id> <status>completed</status> <summary>Agent "Persist behavior rules in DB" completed</s`
3. `tool=Task success=True`
4. `implicit_feedback:success:Task`
5. `<task-notification> <task-id>a4cb5dc5039fecba0</task-id> <tool-use-id>toolu_01AoYqGSvQTkSsun9AXUSZwF</tool-use-id> <status>completed</status> <summary>Agent "Add semantic context retrieval" completed<`
6. `<task-notification> <task-id>a5ea48cb914496c79</task-id> <tool-use-id>toolu_01EDQZtSnjPC2k3VKB5RQRiD</tool-use-id> <status>completed</status> <summary>Agent "Add LLM retry with context trim" completed`
7. `tool=Bash success=True`
8. `tool=Grep success=True`
9. `implicit_feedback:success:TaskCreate`
10. `tool=TaskCreate success=True`
