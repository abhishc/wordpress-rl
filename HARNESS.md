# Harness contract — Env / Task / Rubric / Eval

Labs and reference runners plug into this world without adopting our agent code.

Paths below are from the **archive root** (same layout as the working repo after unpack).

## Vocabulary

| Concept | Path |
|---|---|
| **Env** | `worlds/unistore-mail/` (`world.yaml` + `apps/*/snapshots`) |
| **Task** | `worlds/unistore-mail/tasks/<slug>/` (`task.yaml` + `instruction.md` + `overlay/`) |
| **Rubric** | `worlds/unistore-mail/tasks/<slug>/solution/rubric.yaml` |
| **Eval** | apply → agent → grade |

World id: **`unistore-mail`**. Task slugs: `world.yaml` → `tasks:`.

## Fair trial

```bash
WORLD=unistore-mail ./scripts/common/apply-task/apply_task.sh <slug>
# agent: browser + instruction.md only
#   — no app.secrets.yaml, no inject API (127.0.0.1:19182), no DB/IMAP/SMTP
python3 scripts/common/grade/run_grade.py --world unistore-mail --task <slug>
```

Mail-first: standing ops policy and case facts live in Roundcube; `instruction.md` is credentials + brief only.

Grade WC checks use `task.yaml` → `eval.unistore` (ops Application Password), not baker `app.secrets.yaml`.

## Grade JSON (stable fields)

```json
{
  "score": 0.0,
  "passed": false,
  "rubric_id": "refund-or-replace-v2",
  "scoring": "all_or_nothing",
  "criteria": { "criterion_id": true }
}
```

- Scoring is **`all_or_nothing`**: any failed criterion → `score` 0.0.
- Failure analysis = `criteria` + optional agent traces **from that trial**.
- Do not rely on shipped `bench-results.jsonl` (excluded from lab packs).

Check types and CLI flags: `scripts/common/grade/README.md`.

## Forbidden agent channels

Isolated, not merely undocumented:

- Prefer `scripts/common/agent-sandbox/run.sh <slug>`: edge networks only, `instruction.md` mounted, repo not mounted.
- Mail inject is on the internal world network plus a host-only ops bind (`127.0.0.1:19182`). It is not on the edge network the sandbox joins.
- `app.secrets.yaml`, `runtime.env`, and MySQL/IMAP/SMTP are not mounted into the agent container.

Ops archives that include `app.secrets.yaml` require `ALLOW_OPS_ENVELOPE=internal`. Default export does not.

## Gate (solvability)

```bash
WORLD=unistore-mail ./scripts/common/gate/gate.sh <slug>
```

noop must fail (0.0); oracle must pass (1.0). Same for every slug in `world.yaml`. Export `MANIFEST.txt` records `gate_verified` and per-task contract hashes when stamps were present at pack time.

## Optional reference agent

`scripts/common/bench/` — host Chromium tool agent for calibration. Replace with BrowserGym / Computer Use / an internal harness freely. Bench is **not** the scoring contract.
