#!/usr/bin/env bash
# Gate every task whose contract stamp is missing or stale.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=../lib/require_world.sh
source "${ROOT}/scripts/common/lib/require_world.sh"
require_world
STAMP=(python3 "${ROOT}/scripts/common/gate/stamp.py" --world "${WORLD_ID}")

mapfile -t DIRTY < <("${STAMP[@]}" list-dirty || true)
if [[ "${#DIRTY[@]}" -eq 0 ]]; then
  echo "nothing dirty: ${WORLD_ID}"
  exit 0
fi

echo "dirty tasks (${#DIRTY[@]}): ${DIRTY[*]}"
for task in "${DIRTY[@]}"; do
  [[ -n "${task}" ]] || continue
  WORLD="${WORLD_ID}" "${ROOT}/scripts/common/gate/gate.sh" "${task}"
done
echo "GATE DIRTY PASS: ${WORLD_ID} (${#DIRTY[@]} task(s))"
