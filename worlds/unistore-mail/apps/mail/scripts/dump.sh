#!/usr/bin/env bash
# Capture roundcube.sql + vmail.tar.gz from the running stack.
set -euo pipefail
# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

mkdir -p "${SNAP}"

compose exec -T db \
  mysqldump -uroot -p"${MYSQL_ROOT_PASSWORD}" \
  --single-transaction --routines --events roundcubemail \
  > "${SNAP}/roundcube.sql"

docker run --rm --user 0:0 \
  -v world-unistore-mail_vmail:/vol:ro \
  --entrypoint tar \
  "${MYSQL_IMAGE}" \
  czf - -C /vol . > "${SNAP}/vmail.tar.gz"

python3 - <<PY
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
snap = Path("${SNAP}")
sql = snap / "roundcube.sql"
vmail = snap / "vmail.tar.gz"
meta = {
    "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "files": {
        "roundcube.sql": sql.stat().st_size,
        "vmail.tar.gz": vmail.stat().st_size,
        "roundcube.sql.sha256": hashlib.sha256(sql.read_bytes()).hexdigest(),
    },
}
(snap / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
PY

echo "snapshot written to ${SNAP}"
