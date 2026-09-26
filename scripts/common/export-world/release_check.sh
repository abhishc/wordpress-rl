#!/usr/bin/env bash
# Prove the tarball stands up. A green gate in this repo is not that proof.
#
# Exports, unpacks into a clean directory, then runs make build + gate.sh
# from that copy. Ops secrets are copied in after unpack so gate can
# authenticate — they are not part of the archive.
#
# Reads apps + compose project names from worlds/<id>/world.yaml.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=../lib/require_world.sh
source "${ROOT}/scripts/common/lib/require_world.sh"
require_world
TASK="${1:-}"
WORLD_DIR="${ROOT}/worlds/${WORLD_ID}"

if [[ ! -f "${WORLD_DIR}/world.yaml" ]]; then
  echo "missing ${WORLD_DIR}/world.yaml" >&2
  exit 1
fi

mapfile -t META < <(python3 - "${ROOT}" "${WORLD_DIR}" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts" / "common" / "lib"))
from world_manifest import load_manifest, app_ids, task_slugs

m = load_manifest(Path(sys.argv[2]))
projects = m.get("compose_projects") or {}
apps = app_ids(m)
tasks = task_slugs(m)
if not apps:
    raise SystemExit("world.yaml has no apps")
for a in apps:
    print(f"APP\t{a}\t{projects.get(a) or ''}")
print("TASKS\t" + ",".join(tasks))
PY
)

APP_IDS=()
PROJECTS=()
TASKS_CSV=""
for line in "${META[@]}"; do
  kind="${line%%$'\t'*}"
  rest="${line#*$'\t'}"
  case "${kind}" in
    APP)
      aid="${rest%%$'\t'*}"
      proj="${rest#*$'\t'}"
      APP_IDS+=("${aid}")
      PROJECTS+=("${proj}")
      ;;
    TASKS) TASKS_CSV="${rest}" ;;
  esac
done

if [[ -z "${TASK}" ]]; then
  TASK="${TASKS_CSV%%,*}"
fi
if [[ -z "${TASK}" ]]; then
  echo "usage: WORLD=<id> $0 <task-slug>" >&2
  exit 1
fi

log="$(mktemp)"
WORLD="${WORLD_ID}" "${ROOT}/scripts/common/export-world/export_world.sh" | tee "${log}"
TAR="$(sed -n 's/^wrote //p' "${log}")"
rm -f "${log}"
if [[ -z "${TAR}" || ! -f "${TAR}" ]]; then
  echo "export did not write an archive" >&2
  exit 1
fi

CLEAN="$(mktemp -d)"
echo "unpack ${TAR} -> ${CLEAN}"
tar -xzf "${TAR}" -C "${CLEAN}"
mapfile -t tops < <(find "${CLEAN}" -mindepth 1 -maxdepth 1 -type d)
if [[ "${#tops[@]}" -ne 1 ]]; then
  echo "archive should have one top-level directory" >&2
  exit 1
fi
UNPACK="${tops[0]}"

for need in \
  scripts/common/runtime-env/ensure.py \
  scripts/common/agent-sandbox/run.sh
do
  if [[ ! -f "${UNPACK}/${need}" ]]; then
    echo "unpacked archive missing ${need}" >&2
    exit 1
  fi
done
shipped="$(find "${UNPACK}" \( -name '.env' -o -name 'runtime.env' -o -name 'app.secrets.yaml' \) -print)"
if [[ -n "${shipped}" ]]; then
  echo "archive shipped generated env or ops secrets" >&2
  exit 1
fi

# Lab path: do NOT copy baker shop secrets. Mail inject token is created by
# runtime-env/ensure.py on make build. Grade authenticates via task.yaml eval.
# Optional: RELEASE_COPY_SECRETS=1 copies baker secrets (legacy / internal).
if [[ "${RELEASE_COPY_SECRETS:-0}" == "1" ]]; then
  echo "WARN: RELEASE_COPY_SECRETS=1 — copying baker app.secrets.yaml into unpack" >&2
  for app in "${APP_IDS[@]}"; do
    src="${ROOT}/worlds/${WORLD_ID}/apps/${app}/app.secrets.yaml"
    dest="${UNPACK}/worlds/${WORLD_ID}/apps/${app}/app.secrets.yaml"
    if [[ -f "${src}" ]]; then
      cp "${src}" "${dest}"
      chmod 600 "${dest}"
    fi
  done
fi

down_app() {
  local root="$1" app="$2" project="$3"
  local app_dir="${root}/worlds/${WORLD_ID}/apps/${app}"
  if [[ ! -d "${app_dir}" ]]; then
    echo "missing app dir ${app_dir}" >&2
    exit 1
  fi
  make -C "${app_dir}" down || true
  if [[ -n "${project}" && -f "${app_dir}/.env" ]]; then
    docker compose --env-file "${app_dir}/.env" \
      -f "${app_dir}/compose.yaml" \
      --project-name "${project}" down -v || true
  fi
}

echo "== stop working-repo stacks (same ports/projects)"
for i in "${!APP_IDS[@]}"; do
  down_app "${ROOT}" "${APP_IDS[$i]}" "${PROJECTS[$i]}"
done

echo "== make build from unpacked archive"
for app in "${APP_IDS[@]}"; do
  make -C "${UNPACK}/worlds/${WORLD_ID}/apps/${app}" build
done

echo "== gate.sh from unpacked archive"
WORLD="${WORLD_ID}" "${UNPACK}/scripts/common/gate/gate.sh" "${TASK}"

echo "RELEASE CHECK PASS: ${TAR}"
echo "clean tree: ${UNPACK}"

echo "== restore working-repo volumes (archive keys are not this repo's .env)"
for i in "${!APP_IDS[@]}"; do
  down_app "${UNPACK}" "${APP_IDS[$i]}" "${PROJECTS[$i]}"
done
for app in "${APP_IDS[@]}"; do
  make -C "${ROOT}/worlds/${WORLD_ID}/apps/${app}" build
done
echo "working repo restored"
