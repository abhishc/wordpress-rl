#!/usr/bin/env bash
# Shared compose handles for Mail. Source from other scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi
: "${MYSQL_ROOT_PASSWORD:?missing ${ROOT}/.env — run scripts/common/runtime-env/ensure.py --world unistore-mail}"
COMPOSE=(docker compose --env-file "${ROOT}/.env" -f "${ROOT}/compose.yaml" --project-name world-unistore-mail)
SNAP="${ROOT}/snapshots"
MYSQL_IMAGE="mysql:8.4@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb"

compose() {
  "${COMPOSE[@]}" "$@"
}

ensure_mailbox() {
  python3 - "${ROOT}/app.yaml" "${ROOT}/users.runtime" <<'PY'
from pathlib import Path
import sys
app, dest = Path(sys.argv[1]), Path(sys.argv[2])
box, section = {}, None
for raw in app.read_text(encoding="utf-8").splitlines():
    line = raw.split("#", 1)[0].rstrip()
    if not line.strip():
        continue
    if line.strip() == "login:":
        section = "login"
        continue
    if section == "login" and ":" in line:
        k, _, v = line.strip().partition(":")
        box[k.strip()] = v.strip().strip("'").strip('"')
if not box.get("username") or not box.get("password"):
    raise SystemExit(f"app.yaml missing login.username / login.password: {app}")
name, password = box["username"], box["password"]
dest.write_text(
    f"# generated from app.yaml login\n"
    f"{name}:{{PLAIN}}{password}:1000:1000::/srv/vmail/{name}\n",
    encoding="utf-8",
)
dest.chmod(0o644)
print(f"ensured {name}@mail.example")
PY
}
