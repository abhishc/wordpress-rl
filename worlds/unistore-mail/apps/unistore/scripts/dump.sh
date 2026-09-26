#!/usr/bin/env bash
# Capture wordpress.sql + wp.tar.gz from the running stack.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

mkdir -p "${SNAP}"

compose exec -T db \
  mysqldump -uroot -p"${MYSQL_ROOT_PASSWORD}" \
  --single-transaction --routines --events wordpress \
  > "${SNAP}/wordpress.sql"

compose exec -T wordpress tar czf - -C /var/www/html . > "${SNAP}/wp.tar.gz"

python3 - <<PY
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
snap = Path("${SNAP}")
sql = snap / "wordpress.sql"
wp = snap / "wp.tar.gz"
meta = {
    "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "files": {
        "wordpress.sql": sql.stat().st_size,
        "wp.tar.gz": wp.stat().st_size,
        "wordpress.sql.sha256": hashlib.sha256(sql.read_bytes()).hexdigest(),
    },
}
(snap / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
PY

echo "snapshot written to ${SNAP}"
