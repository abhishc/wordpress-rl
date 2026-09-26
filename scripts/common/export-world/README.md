# export-world

Pack `worlds/<id>` + scripts listed by that world's `world.yaml`.

```bash
WORLD=unistore-mail ./scripts/common/export-world/export_world.sh
# → dist/world-unistore-mail-YYYYMMDD.tar.gz
# no app.secrets.yaml, no runtime.env, no apps/*/.env
# refuses if any task gate stamp is missing/stale
```

Before packing, export runs `stamp.py check-world`. Edit a rubric/instruction/`task.yaml`/oracle/overlay → stamp goes dirty → export blocked until:

```bash
WORLD=unistore-mail ./scripts/common/gate/gate_dirty.sh
```

WIP-only escape (never for lab drops): `SKIP_GATE_STAMP=1`. Stamps themselves are not shipped; `MANIFEST.txt` records `gate_verified: 1` plus per-task `contract_sha256` and `gated_utc` (or `gate_verified: 0` / `gate: skipped` when skipped) so a lab pack is self-evidencing.

```bash
# internal transfer only — refused without the flag
ALLOW_OPS_ENVELOPE=internal INCLUDE_SECRETS=1 ./scripts/common/export-world/export_world.sh
```

Manifest-driven: apps, tasks, ports written to `MANIFEST.txt`. App script trees under `scripts/<app>/` included only for apps in the world. `scripts/common/` always includes `runtime-env` and `agent-sandbox`.

```bash
WORLD=unistore-mail ./scripts/common/export-world/release_check.sh fraud-hold
# export, unpack into a clean directory, make build + gate.sh there
```
