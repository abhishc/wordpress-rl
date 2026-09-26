# unistore-mail — lab / human-review pack

Self-contained **WooCommerce (UniStore) + Roundcube Mail** world with five ops-desk tasks.

Unpack this archive as the working tree root (it must contain `worlds/` and `scripts/`).

**Integration contract:** [`HARNESS.md`](HARNESS.md)  
**Secrets posture:** [`SECRETS.md`](SECRETS.md) (also summarized below)

## What the agent sees

Each trial is **mail-first**:

1. Read `worlds/unistore-mail/tasks/<slug>/instruction.md` (URLs + eval credentials only).
2. Open Roundcube for the standing **ops policy** mail and the **case** ticket.
3. Investigate and mutate live UniStore state in wp-admin.
4. Grade against `tasks/<slug>/solution/rubric.yaml` (exact note tokens + order semantics).

Do **not** give the agent `app.secrets.yaml`, MySQL/IMAP/SMTP, or the mail inject API.

## Vocabulary

| Concept | Path |
|---|---|
| **Env** | `worlds/unistore-mail/` (`world.yaml` + `apps/*/snapshots`) |
| **Task** | `worlds/unistore-mail/tasks/<slug>/` (`task.yaml`, `instruction.md`, `overlay/`) |
| **Rubric** | `…/solution/rubric.yaml` |
| **Eval** | apply → agent → `scripts/common/grade` |

World id: **`unistore-mail`**. Every CLI that targets a world requires `WORLD=unistore-mail` or `--world unistore-mail`.

## Tasks

| Slug | Brief |
|---|---|
| `refund-or-replace` | Damaged hoodie → issue replacement; do not refund/cancel original |
| `fraud-hold` | Hold matching Lake Shore velocity burst; leave non-matching controls |
| `stockout-substitute` | OOS line → on-hold + substitute SKUs in private note |
| `partial-fulfill-split` | Ship in-stock line; drop OOS line |
| `wrong-address-in-transit` | Carrier in-transit → cancel/refund; do not rewrite shipping address |

Full list: `worlds/unistore-mail/world.yaml` → `tasks:`.

## Ports (published UIs)

| Service | URL |
|---|---|
| UniStore shop / wp-admin | http://127.0.0.1:19180/ |
| Roundcube | http://127.0.0.1:19181/ |
| Mail inject (ops only) | http://127.0.0.1:19182/ — **not** for eval agents |

Eval mailbox / ops UI logins are in each task’s `instruction.md` (and mirrored under `task.yaml` `eval:`).

## Quick start

Requires Docker Compose and `make`.

```bash
# 1) Bring apps up from snapshots
#    - generates local runtime.env / .env (not eval creds)
#    - creates apps/mail/app.secrets.yaml inject token if missing
make -C worlds/unistore-mail/apps/unistore build
make -C worlds/unistore-mail/apps/mail build

# 2) Reset dumps + inject the task overlay mail
WORLD=unistore-mail ./scripts/common/apply-task/apply_task.sh refund-or-replace

# 3a) Human review — follow instruction.md in the two UIs only
# 3b) Or run your agent, then grade:
python3 scripts/common/grade/run_grade.py --world unistore-mail --task refund-or-replace
```

Repeat steps 2–3 for each slug. Always **apply** before a fair trial so state matches the task contract.

Grade authenticates to WooCommerce with the **ops** Application Password in each task’s `task.yaml` `eval:` block (not baker `bakeadmin`). Do not mount `task.yaml` or `app.secrets.yaml` into the agent sandbox.

If `make build` fails with MySQL access denied on a host that previously ran this world, wipe volumes then rebuild (`docker compose … down -v` for projects `world-unistore` and `world-unistore-mail`). A first-time host does not need this.

### Isolation (recommended for agent eval)

```bash
WORLD=unistore-mail ./scripts/common/agent-sandbox/run.sh refund-or-replace
```

Sandbox mounts `instruction.md` only and joins edge networks — not the full repo, not inject/ops.

### Solvability gate (optional on your side)

```bash
WORLD=unistore-mail ./scripts/common/gate/gate.sh <slug>
```

noop must score **0.0**; oracle must score **1.0**. This pack was gated before export when `MANIFEST.txt` shows `gate_verified: 1`.

### Optional reference agent

`scripts/common/bench/` — host Chromium tool agent for calibration. Replace freely with BrowserGym / Computer Use / your harness. Bench traces are **not** part of the scoring contract; do not ship or rely on `bench-results.jsonl`.

## Grade output

Stable JSON fields (see `HARNESS.md`):

- `score` — `0.0` or `1.0` under `all_or_nothing`
- `passed` — boolean
- `rubric_id`, `scoring`, `criteria` — per-criterion booleans

Failure analysis = that trial’s `criteria` (+ your own agent traces). Rubrics check live WooCommerce state (status, lines, notes, negatives), not free-form email prose.

## Secrets

| File | Role |
|---|---|
| `apps/*/app.yaml` | Public endpoints + eval mailbox login |
| `apps/*/app.secrets.yaml` | Ops only — **excluded** from default lab packs. Mail inject token is **generated on first `make build`** if missing. |
| `runtime.env`, `apps/*/.env` | Generated on `make build`; not in the archive; not eval credentials |

Do not set `INCLUDE_SECRETS=1` for lab or reviewer packs.

Baker-only trees (`BAKE.md`, `populate/`, `families/`, `HUMAN_UI_PASS.md`) are **not** included in the archive.

## Doc map

| Doc | Audience |
|---|---|
| This `README.md` | Lab / human review entrypoint |
| [`HARNESS.md`](HARNESS.md) | Env / Task / Rubric / Eval contract |
| [`SECRETS.md`](SECRETS.md) | What was packed |
| [`MANIFEST.txt`](MANIFEST.txt) | Apps, tasks, gate evidence |
| `scripts/common/*/README.md` | Operator CLIs (apply, grade, gate, sandbox, bench) |
| `worlds/unistore-mail/apps/*/README.md` | App build / dump notes |

