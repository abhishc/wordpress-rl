#!/usr/bin/env bash
# Pack a review/lab world archive from world.yaml (apps/tasks/scripts).
# Default excludes ops secrets and runtime keys.
# INCLUDE_SECRETS=1 is refused unless ALLOW_OPS_ENVELOPE=internal.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=../lib/require_world.sh
source "${ROOT}/scripts/common/lib/require_world.sh"
require_world
STAMP="$(date -u +%Y%m%d)"
NAME="${ARCHIVE_NAME:-world-${WORLD_ID}-${STAMP}}"
WORLD_DIR="${ROOT}/worlds/${WORLD_ID}"
OUT_DIR="${ROOT}/dist"
STAGE="${OUT_DIR}/.stage-${NAME}"
TAR="${OUT_DIR}/${NAME}.tar.gz"
INCLUDE_SECRETS="${INCLUDE_SECRETS:-0}"

if [[ "${INCLUDE_SECRETS}" == "1" && "${ALLOW_OPS_ENVELOPE:-}" != "internal" ]]; then
  echo "refusing INCLUDE_SECRETS=1 (live ops creds must not leave this host by default)." >&2
  echo "internal transfer only: ALLOW_OPS_ENVELOPE=internal INCLUDE_SECRETS=1 $0" >&2
  exit 2
fi

if [[ ! -f "${WORLD_DIR}/world.yaml" ]]; then
  echo "missing ${WORLD_DIR}/world.yaml" >&2
  exit 1
fi

# Refuse to pack if any task contract changed since last successful gate.
# SKIP_GATE_STAMP=1 is WIP-only — do not use for lab drops.
if [[ "${SKIP_GATE_STAMP:-0}" != "1" ]]; then
  echo "== gate stamp check (${WORLD_ID})"
  python3 "${ROOT}/scripts/common/gate/stamp.py" --world "${WORLD_ID}" check-world
else
  echo "WARN: SKIP_GATE_STAMP=1 — packing without verified noop/oracle gates" >&2
fi

rm -rf "${STAGE}"
mkdir -p "${STAGE}/${NAME}/worlds" "${STAGE}/${NAME}/scripts" "${OUT_DIR}"

cp "${WORLD_DIR}/ARCHIVE_README.md" "${STAGE}/${NAME}/README.md"
cp "${WORLD_DIR}/HARNESS.md" "${STAGE}/${NAME}/HARNESS.md"

RSYNC_EXCL=(
  --exclude 'BACKAGENT_INSTRUCTIONS.md'
  --exclude 'BACKAGENT_VERIFIER.md'
  --exclude 'ARCHIVE_README.md'
  --exclude 'BAKE.md'
  --exclude 'HUMAN_UI_PASS.md'
  --exclude 'populate/'
  --exclude 'families/'
  --exclude '**/bench-results.jsonl'
  --exclude '**/solution/episodes/'
  --exclude '**/.gate-stamp'
  --exclude '**/__pycache__/'
  --exclude '**/*.pyc'
  --exclude '**/users.runtime'
  --exclude '**/runtime.env'
  --exclude '**/.env'
  --exclude '.git/'
)
if [[ "${INCLUDE_SECRETS}" != "1" ]]; then
  RSYNC_EXCL+=(--exclude '**/app.secrets.yaml')
fi

rsync -a "${RSYNC_EXCL[@]}" \
  "${WORLD_DIR}/" "${STAGE}/${NAME}/worlds/${WORLD_ID}/"

cat > "${STAGE}/${NAME}/SECRETS.md" <<EOF
# Secrets posture

- \`app.yaml\` — public endpoints + eval mailbox login.
- \`app.secrets.yaml\` — baker/ops only. Excluded unless INCLUDE_SECRETS=1 and ALLOW_OPS_ENVELOPE=internal.
- \`runtime.env\` / \`apps/*/.env\` — generated per bake, not shipped. Not eval credentials.

This archive was built with INCLUDE_SECRETS=${INCLUDE_SECRETS}.
EOF

rsync -a --exclude '**/__pycache__/' --exclude '**/*.pyc' \
  "${ROOT}/scripts/README.md" "${STAGE}/${NAME}/scripts/"

mapfile -t APP_IDS < <(python3 - "${ROOT}" "${WORLD_DIR}" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts" / "common" / "lib"))
from world_manifest import load_manifest, app_ids
print("\n".join(app_ids(load_manifest(Path(sys.argv[2])))))
PY
)

for app in "${APP_IDS[@]}"; do
  if [[ -d "${ROOT}/scripts/${app}" ]]; then
    rsync -a --exclude '**/__pycache__/' \
      "${ROOT}/scripts/${app}/" "${STAGE}/${NAME}/scripts/${app}/"
  fi
done

mkdir -p "${STAGE}/${NAME}/scripts/common"
# runtime-env is required for make build. agent-sandbox is the isolation
# contract HARNESS.md points at. Both must ship; do not silently skip.
for part in apply-task gate bench grade lib export-world runtime-env agent-sandbox; do
  src="${ROOT}/scripts/common/${part}"
  if [[ ! -d "${src}" ]]; then
    echo "export whitelist missing scripts/common/${part}" >&2
    exit 1
  fi
  rsync -a --exclude '**/__pycache__/' --exclude '**/*.pyc' \
    "${src}/" "${STAGE}/${NAME}/scripts/common/${part}/"
done

GATE_SKIP="${SKIP_GATE_STAMP:-0}"
python3 - "${ROOT}" "${WORLD_DIR}" "${STAGE}/${NAME}/MANIFEST.txt" "${NAME}" "${INCLUDE_SECRETS}" "${GATE_SKIP}" <<'PY'
import datetime, sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts" / "common" / "lib"))
sys.path.insert(0, str(root / "scripts" / "common" / "gate"))
from world_manifest import load_manifest, app_ids, task_slugs
from stamp import manifest_gate_lines

m = load_manifest(Path(sys.argv[2]))
out = Path(sys.argv[3])
name, inc, gate_skip = sys.argv[4], sys.argv[5], sys.argv[6]
world_id = m.get("id") or Path(sys.argv[2]).name
lines = [
    f"name: {name}",
    f"created_utc: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
    f"world: {world_id}",
    f"apps: {', '.join(app_ids(m))}",
    f"tasks: {', '.join(task_slugs(m))}",
    f"include_secrets: {inc}",
]
ports = m.get("ports") or {}
if ports:
    lines.append("ports: " + ", ".join(f"{k}={v}" for k, v in ports.items()))
lines.extend(manifest_gate_lines(world_id, verified=(gate_skip != "1")))
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

(cd "${STAGE}" && tar -czf "${TAR}" "${NAME}")
rm -rf "${STAGE}"

listing="$(tar -tzf "${TAR}")"
missing=0
for need in \
  "scripts/common/runtime-env/ensure.py" \
  "scripts/common/agent-sandbox/run.sh"
do
  if ! grep -F -q "/${need}" <<< "${listing}"; then
    echo "archive missing ${need}" >&2
    missing=1
  fi
done
if [[ "${missing}" -ne 0 ]]; then
  exit 1
fi

echo "wrote ${TAR}"
echo "files: $(tar -tzf "${TAR}" | wc -l)  size: $(du -h "${TAR}" | cut -f1)"
