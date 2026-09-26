# Secrets posture

- `app.yaml` — public endpoints + eval mailbox login.
- `app.secrets.yaml` — baker/ops only. Excluded unless INCLUDE_SECRETS=1 and ALLOW_OPS_ENVELOPE=internal.
- `runtime.env` / `apps/*/.env` — generated per bake, not shipped. Not eval credentials.

This archive was built with INCLUDE_SECRETS=0.
