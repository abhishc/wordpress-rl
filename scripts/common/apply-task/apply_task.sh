#!/usr/bin/env bash
# Reset world dumps from world.yaml, then apply task overlays per apps[].overlay.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=../lib/require_world.sh
source "${ROOT}/scripts/common/lib/require_world.sh"
require_world
TASK_SLUG="${1:-}"
if [[ -z "${TASK_SLUG}" ]]; then
  echo "usage: WORLD=<id> $0 <task-slug>" >&2
  exit 1
fi

WORLD_DIR="${ROOT}/worlds/${WORLD_ID}"
MANIFEST="${WORLD_DIR}/world.yaml"
TASK_DIR="${WORLD_DIR}/tasks/${TASK_SLUG}"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "missing world manifest: ${MANIFEST}" >&2
  exit 1
fi
if [[ ! -d "${TASK_DIR}" ]]; then
  echo "missing task dir: ${TASK_DIR}" >&2
  exit 1
fi

mapfile -t META < <(python3 - "${ROOT}" "${WORLD_DIR}" <<'PY'
import shlex, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts" / "common" / "lib"))
from world_manifest import load_manifest, app_ids, overlay_apps, validate_ports

world_dir = Path(sys.argv[2])
m = load_manifest(world_dir)
errs = validate_ports(world_dir, m)
if errs:
    for e in errs:
        print(f"ERR\t{e}")
    sys.exit(1)
for a in app_ids(m):
    print(f"APP\t{a}")
for a in overlay_apps(m):
    print(f"OV\t{a['id']}\t{a['overlay']}")
PY
)

APP_IDS=()
OVERLAY_APPS=()
OVERLAY_KINDS=()
for line in "${META[@]}"; do
  kind="${line%%$'\t'*}"
  rest="${line#*$'\t'}"
  case "${kind}" in
    ERR) echo "world.yaml validation: ${rest}" >&2; exit 1 ;;
    APP) APP_IDS+=("${rest}") ;;
    OV)
      OVERLAY_APPS+=("${rest%%$'\t'*}")
      OVERLAY_KINDS+=("${rest#*$'\t'}")
      ;;
  esac
done

for app in "${APP_IDS[@]}"; do
  echo "reset ${WORLD_ID}/${app}"
  make -C "${WORLD_DIR}/apps/${app}" reset
done

shopt -s nullglob
applied=0
for i in "${!OVERLAY_APPS[@]}"; do
  app="${OVERLAY_APPS[$i]}"
  kind="${OVERLAY_KINDS[$i]}"
  case "${kind}" in
    eml)
      emls=("${TASK_DIR}/overlay"/*.eml)
      if ((${#emls[@]} == 0)); then
        echo "app ${app} overlay=eml but no overlay/*.eml" >&2
        exit 1
      fi
      for eml in "${emls[@]}"; do
        echo "inject $(basename "${eml}") -> ${app}"
        python3 "${ROOT}/scripts/mail/mail-inject/mail_inject.py" \
          --app-yaml "${WORLD_DIR}/apps/${app}/app.yaml" \
          --eml "${eml}"
        applied=$((applied + 1))
      done
      ;;
    *)
      echo "unknown overlay kind '${kind}' for app ${app}" >&2
      exit 1
      ;;
  esac
done

if [[ "${applied}" -eq 0 ]]; then
  echo "no overlays applied (no apps[].overlay or empty)"
fi

if [[ -f "${TASK_DIR}/users/meridian" ]]; then
  echo "note: users/meridian present; ensure accounts exist in world dump or create via scripts/meridian/wp-create-user"
fi

echo "applied task ${TASK_SLUG} on world ${WORLD_ID}"
