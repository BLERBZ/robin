# Cursor / VS Code integration

Goal: feed Kait with **portable events** without coupling Kait core to any IDE.

## Prereqs

Start Kait services (recommended one-liner):
```bash
kait up
```

(Stops with `kait down`)

## One-keystroke “Remember this” (recommended)

Create a Cursor/VS Code Task that runs:

```bash
python3 scripts/emit_event.py \
  --source cursor \
  --kind command \
  --session "${workspaceFolderBasename}" \
  --intent remember \
  --text "${input:rememberText}" \
| python3 adapters/stdin_ingest.py --kaitd ${KAITD_URL:-http://127.0.0.1:${KAITD_PORT:-8787}}
```

### VS Code `tasks.json` example

```json
{
  "version": "2.0.0",
  "inputs": [
    {
      "id": "rememberText",
      "type": "promptString",
      "description": "What should Kait remember?"
    }
  ],
  "tasks": [
    {
      "label": "Kait: Remember",
      "type": "shell",
      "command": "python3 scripts/emit_event.py --source cursor --kind command --session ${workspaceFolderBasename} --intent remember --text \"${input:rememberText}\" | python3 adapters/stdin_ingest.py --kaitd ${KAITD_URL:-http://127.0.0.1:${KAITD_PORT:-8787}}",
      "problemMatcher": []
    }
  ]
}
```

If you override ports, replace `8787` or set `KAITD_URL` and use:
```bash
python3 adapters/stdin_ingest.py --kaitd ${KAITD_URL:-http://127.0.0.1:${KAITD_PORT:-8787}}
```

## Sending chat text (optional)

If you want Kait to auto-suggest memories from your IDE chat, emit `kind=message` events:

```bash
python3 scripts/emit_event.py --source cursor --kind message --session "${workspaceFolderBasename}" --role user --text "..." \
| python3 adapters/stdin_ingest.py --kaitd ${KAITD_URL:-http://127.0.0.1:${KAITD_PORT:-8787}}
```

In many environments, explicit `remember` is the cleanest UX and avoids false positives.
