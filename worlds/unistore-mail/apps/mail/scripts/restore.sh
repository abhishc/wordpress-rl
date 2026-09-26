#!/usr/bin/env bash
# Restore the dump: SQL into MySQL, vmail.tar.gz onto the mail volume.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

SQL="${SNAP}/roundcube.sql"
VMAIL_TAR="${SNAP}/vmail.tar.gz"
if [[ ! -f "${SQL}" || ! -f "${VMAIL_TAR}" ]]; then
  echo "missing snapshot under ${SNAP}; run: make snapshot" >&2
  exit 1
fi

compose up -d --wait --wait-timeout 120 db

compose exec -T db mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e \
  "DROP DATABASE IF EXISTS roundcubemail; CREATE DATABASE roundcubemail CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL PRIVILEGES ON roundcubemail.* TO 'roundcube'@'%';"
compose exec -T db mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" roundcubemail < "${SQL}"
# IMAP passwords in `users` are encrypted with this bake's DES key. Drop them
# so a rotated key cannot brick Roundcube login. Mailbox bytes live in vmail.
compose exec -T db mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" roundcubemail -e \
  "SET FOREIGN_KEY_CHECKS=0;
   TRUNCATE TABLE session;
   TRUNCATE TABLE cache;
   TRUNCATE TABLE cache_index;
   TRUNCATE TABLE cache_messages;
   TRUNCATE TABLE cache_shared;
   TRUNCATE TABLE cache_thread;
   TRUNCATE TABLE collected_addresses;
   TRUNCATE TABLE contactgroupmembers;
   TRUNCATE TABLE contactgroups;
   TRUNCATE TABLE contacts;
   TRUNCATE TABLE identities;
   TRUNCATE TABLE searches;
   TRUNCATE TABLE dictionary;
   TRUNCATE TABLE filestore;
   TRUNCATE TABLE responses;
   TRUNCATE TABLE users;
   SET FOREIGN_KEY_CHECKS=1;"

compose stop dovecot postfix
docker run --rm --user 0:0 \
  -v world-unistore-mail_vmail:/vol \
  -v "${SNAP}:/snap:ro" \
  --entrypoint bash \
  "${MYSQL_IMAGE}" \
  -c "find /vol -mindepth 1 -delete && tar xzf /snap/vmail.tar.gz -C /vol && chown -R 1000:1000 /vol"

ensure_mailbox
compose up -d --wait --wait-timeout 180 --force-recreate dovecot postfix inject
compose up -d --wait --wait-timeout 180 roundcube
echo "restored snapshot from ${SNAP}"
