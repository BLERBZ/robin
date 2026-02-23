# Support Macros (Canned Responses)

Use these to respond quickly while still collecting the info needed to debug.

## Macro: Need Logs + Health

Thanks for the report. To help debug quickly, can you paste:
- OS + Python version
- output of `kait health`
- output of `kait services`
- the last ~50 lines of relevant log(s) from `~/.kait/logs`

If this is a security/safety issue, please follow `SECURITY.md` instead of posting details publicly.

## Macro: Port Conflict

This looks like a port bind conflict.

1. Run `kait services` to see which components are attempting to bind.
2. Override the port with env vars (see `lib/ports.py` and `docs/QUICKSTART.md`).
3. Restart services (`kait down`, then `kait up`).

## Macro: Guardrail Block

Kait blocked this action by design.

Please share:
- the `[EIDOS] BLOCKED:` message
- what you were trying to do (high-level)

If you intentionally need to allow this, use an explicit override and document the justification.

