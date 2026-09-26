#!/usr/bin/env bash
# Shared compose handles for UniStore. Source from other scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi
: "${MYSQL_ROOT_PASSWORD:?missing ${ROOT}/.env — run scripts/common/runtime-env/ensure.py --world unistore-mail}"
COMPOSE=(docker compose --env-file "${ROOT}/.env" -f "${ROOT}/compose.yaml" --project-name world-unistore)
SNAP="${ROOT}/snapshots"
WP_IMAGE="wordpress:php8.4-apache@sha256:8c895fbeb5a2cfc5bdabb1dde9cf3cb7209ed60ab48650630ed57333777b7d55"
compose() {
  "${COMPOSE[@]}" "$@"
}
