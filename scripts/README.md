# Baker scripts

Reusable tools for the **baker / backagent** and **harness operators**. Not for the eval agent mid-trial.

`apps/*/scripts/` stays dump / restore / injectd (app lifecycle). This tree is for baking, gating, and benchmarking helpers.

## Layout

| Kind | Path |
|---|---|
| App-specific | `scripts/<app>/<script>/` — same ids as `apps/<id>` |
| Cross-app | `scripts/common/<script>/` — takes app/world paths as args |

Do not put tools under `scripts/world/` — worlds change as apps are added.

## Rules

- Before baking an app, read that app’s `README.md` (login reuse vs create, `app.yaml` fields).
- One capability per folder under `scripts/<app|common>/<name>/`.
- Every folder has a `README.md`: purpose, how to run, inputs/outputs, which `apps/*/app.yaml` fields it reads.
- Add a one-line entry to the catalog below when you add a script.
- Creds: eval mailbox in `app.yaml`; ops secrets in gitignored `app.secrets.yaml`; runtime keys via `common/runtime-env/`. Never copy secrets into docs.
- Eval agent runs only in `common/agent-sandbox/`. It does not run the rest of this tree.

## Catalog

| Script | Purpose |
|---|---|
| `meridian/wp-create-user/` | Create a WordPress user via REST (`admin` Application Password from app.yaml). |
| `meridian/wp-create-post/` | Create a WordPress post via REST. |
| `common/synth-bank/` | Universal scenery: Snowfakery recipes, Faker fallback, optional SDV / NeMo. `bootstrap.sh` then `generate.py` or `nemo_generate.py`. |
| `mail/mail-inject/` | POST a raw `.eml` to the mail inject API (`admin.token` from app.yaml). |
| `common/apply-task/` | Reset world dumps, then inject a task’s `overlay/*.eml`. |
| `common/gate/` | noop → 0, oracle → 1 for a world task. |
| `common/grade/` | Shared rubric grader + check-type registry. |
| `common/bench/` | apply → OpenAI browser agent → grade (N trials). |
| `common/export-world/` | Pack review/lab `.tar.gz`. Secrets off unless `ALLOW_OPS_ENVELOPE=internal`. |
| `common/runtime-env/` | Generate per-bake MySQL/salt/DES keys into gitignored `.env`. |
| `common/rotate-ops/` | Rotate bakeadmin password, application password, inject token. |
| `common/agent-sandbox/` | Eval runtime: edge networks + `instruction.md` only. |
