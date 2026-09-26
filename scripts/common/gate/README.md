# gate

Harbor-style gate for one world task: reset → apply → noop must fail → oracle must pass.

Also writes a **contract stamp** (`tasks/<slug>/solution/.gate-stamp`) so export can refuse packs whose rubric/instruction/eval/oracle changed since the last green gate.

## Run

```bash
WORLD=unistore-mail ./scripts/common/gate/gate.sh fraud-hold

# only tasks with missing/stale stamps
WORLD=unistore-mail ./scripts/common/gate/gate_dirty.sh

# inspect without running stacks
WORLD=unistore-mail python3 scripts/common/gate/stamp.py check-world
WORLD=unistore-mail python3 scripts/common/gate/stamp.py list-dirty
```

`WORLD` is required (no default).

Requires world stacks up and task `solution/grade.py` + `solution/oracle/run.py`.

## Contract stamp

Hashed paths (relative to the task dir): `instruction.md`, `task.yaml`, `overlay/`, `solution/rubric.yaml`, `solution/grade.py`, `solution/oracle/`.

Also hashed (shared): `scripts/common/grade/grade_rubric.py` — registry changes dirty **all** task stamps.

Stamps are local (gitignored, not shipped as files). `export_world.sh` fails if any world task is dirty unless `SKIP_GATE_STAMP=1` (WIP only — never for lab drops). Export copies each stamp’s `contract_sha256` + `gated_utc` into `MANIFEST.txt` (`gate_verified: 1`), so a gated pack does not look like a skipped one.

| Tier | What | When |
|---|---|---|
| A | `gate.sh` / `gate_dirty.sh` (noop→0, oracle→1) | After any contract edit; before export |
| B | `release_check.sh` + agent-sandbox | Per release tarball |
| C | multi-trial bench | Difficulty band; not a ship blocker |
