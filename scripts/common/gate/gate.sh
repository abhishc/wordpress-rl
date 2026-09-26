#!/usr/bin/env bash
# Gate: noop → 0, oracle → 1 for one world task.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=../lib/require_world.sh
source "${ROOT}/scripts/common/lib/require_world.sh"
require_world
TASK_SLUG="${1:?task slug required}"
WORLD_DIR="${ROOT}/worlds/${WORLD_ID}"
TASK_DIR="${WORLD_DIR}/tasks/${TASK_SLUG}"
GRADE=(python3 "${ROOT}/scripts/common/grade/run_grade.py" --world "${WORLD_ID}" --task "${TASK_SLUG}")
ORACLE="${TASK_DIR}/solution/oracle/run.py"

if [[ ! -f "${ORACLE}" ]]; then
  echo "missing oracle: ${ORACLE}" >&2
  exit 1
fi

echo "== reset + apply ${TASK_SLUG} (world=${WORLD_ID})"
WORLD="${WORLD_ID}" "${ROOT}/scripts/common/apply-task/apply_task.sh" "${TASK_SLUG}"

echo "== noop grade (expect fail / score 0)"
set +e
"${GRADE[@]}"
noop_rc=$?
set -e
if [[ "${noop_rc}" -eq 0 ]]; then
  echo "GATE FAIL: noop scored pass" >&2
  exit 1
fi
echo "noop ok (failed as expected)"

echo "== oracle"
python3 "${ORACLE}"

echo "== oracle grade (expect pass / score 1)"
"${GRADE[@]}"
python3 "${ROOT}/scripts/common/gate/stamp.py" --world "${WORLD_ID}" write --task "${TASK_SLUG}"
echo "GATE PASS: noop=0 oracle=1 (${WORLD_ID}/${TASK_SLUG})"
