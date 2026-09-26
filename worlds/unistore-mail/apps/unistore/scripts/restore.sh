#!/usr/bin/env bash
# Restore the dump: SQL into MySQL, wp.tar.gz onto the WordPress volume.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

SQL="${SNAP}/wordpress.sql"
WP_TAR="${SNAP}/wp.tar.gz"
if [[ ! -f "${SQL}" || ! -f "${WP_TAR}" ]]; then
  echo "missing snapshot under ${SNAP}; run: make snapshot" >&2
  exit 1
fi

compose up -d --wait --wait-timeout 120 db

compose exec -T db mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e \
  "DROP DATABASE IF EXISTS wordpress; CREATE DATABASE wordpress;"
compose exec -T db mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" wordpress < "${SQL}"

compose stop wordpress
docker run --rm --user 0:0 \
  -v world-unistore_wp_data:/vol \
  -v "${SNAP}:/snap:ro" \
  --entrypoint bash \
  "${WP_IMAGE}" \
  -c "find /vol -mindepth 1 -delete && tar xzf /snap/wp.tar.gz -C /vol"

compose up -d --wait --wait-timeout 120 wordpress
echo "restored snapshot from ${SNAP}"
