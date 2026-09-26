# Resolve WORLD with no silent default.
# Meridian-mail was the first world; defaulting to it caused cross-world bugs.
# Source from bash:  source "${ROOT}/scripts/common/lib/require_world.sh"
# Then:              require_world   # sets WORLD_ID from $WORLD
require_world() {
  if [[ -z "${WORLD:-}" ]]; then
    echo "WORLD is required (example: WORLD=unistore-mail $0 …)." >&2
    echo "No default world — refusing silent meridian-mail fallback." >&2
    exit 2
  fi
  WORLD_ID="${WORLD}"
  if [[ ! -f "${ROOT}/worlds/${WORLD_ID}/world.yaml" ]]; then
    echo "missing world: ${ROOT}/worlds/${WORLD_ID}/world.yaml" >&2
    exit 1
  fi
}
