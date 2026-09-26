#!/usr/bin/env bash
# Supported eval-agent runtime. Host Playwright is ops/oracle only.
#
# The container joins only the world *edge* networks (UIs). Inject is not on
# those networks. The repo (secrets, runtime.env) is not mounted.
#
# Networks and URL rewrites come from worlds/<id>/world.yaml (override with
# EDGE_NETS / still supported MER_NET+MAIL_NET for one-off experiments).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=../lib/require_world.sh
source "${ROOT}/scripts/common/lib/require_world.sh"
require_world
TASK="${1:-}"
WORLD_DIR="${ROOT}/worlds/${WORLD_ID}"
if [[ -z "${TASK}" ]]; then
  echo "usage: WORLD=<id> $0 <task-slug>" >&2
  exit 1
fi
INSTR="${WORLD_DIR}/tasks/${TASK}/instruction.md"
if [[ ! -f "${INSTR}" ]]; then
  echo "missing ${INSTR}" >&2
  exit 1
fi
if [[ ! -f "${WORLD_DIR}/world.yaml" ]]; then
  echo "missing ${WORLD_DIR}/world.yaml" >&2
  exit 1
fi

mapfile -t SANDBOX_META < <(python3 - "${ROOT}" "${WORLD_DIR}" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts" / "common" / "lib"))
from world_manifest import load_manifest, app_ids

world_dir = Path(sys.argv[2])
m = load_manifest(world_dir)
ports = m.get("ports") or {}
projects = m.get("compose_projects") or {}
edges = []
for aid in app_ids(m):
    proj = projects.get(aid)
    if not proj:
        raise SystemExit(f"world.yaml missing compose_projects.{aid}")
    edges.append(f"{proj}-edge")
seen = set()
uniq = []
for e in edges:
    if e not in seen:
        seen.add(e)
        uniq.append(e)
print("EDGES\t" + ",".join(uniq))
shop_port = None
mail_ui = None
mail_inject = None
for k, v in ports.items():
    key = str(k).lower()
    if key in ("mail_ui", "mail"):
        mail_ui = int(v)
    elif key in ("mail_inject", "inject"):
        mail_inject = int(v)
    elif shop_port is None:
        shop_port = int(v)
if shop_port is None or mail_ui is None:
    raise SystemExit(f"world.yaml ports need a shop UI + mail_ui; got {ports}")
print(f"PORTS\t{shop_port}\t{mail_ui}\t{mail_inject or 0}")
PY
)

EDGE_CSV=""
SHOP_PORT=""
MAIL_UI_PORT=""
INJECT_PORT="0"
for line in "${SANDBOX_META[@]}"; do
  kind="${line%%$'\t'*}"
  rest="${line#*$'\t'}"
  case "${kind}" in
    EDGES) EDGE_CSV="${rest}" ;;
    PORTS)
      SHOP_PORT="${rest%%$'\t'*}"
      rest2="${rest#*$'\t'}"
      MAIL_UI_PORT="${rest2%%$'\t'*}"
      INJECT_PORT="${rest2#*$'\t'}"
      ;;
  esac
done

# Optional overrides (legacy MER_NET/MAIL_NET or EDGE_NETS=a,b)
if [[ -n "${EDGE_NETS:-}" ]]; then
  EDGE_CSV="${EDGE_NETS}"
elif [[ -n "${MER_NET:-}" || -n "${MAIL_NET:-}" ]]; then
  EDGE_CSV="${MER_NET:-},${MAIL_NET:-}"
  EDGE_CSV="${EDGE_CSV#,}"
  EDGE_CSV="${EDGE_CSV%,}"
fi

IFS=',' read -r -a EDGE_ARR <<< "${EDGE_CSV}"
if [[ "${#EDGE_ARR[@]}" -lt 1 ]]; then
  echo "no edge networks" >&2
  exit 1
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT
cp "${INSTR}" "${WORKDIR}/instruction.md"
python3 - "${WORKDIR}/instruction.md" "${SHOP_PORT}" "${MAIL_UI_PORT}" "${INJECT_PORT}" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
shop, mail_ui, inject = sys.argv[2], sys.argv[3], sys.argv[4]
t = p.read_text(encoding="utf-8")
t = t.replace(f"http://127.0.0.1:{shop}", "http://wordpress")
t = t.replace(f"http://127.0.0.1:{mail_ui}", "http://roundcube")
if inject != "0" and inject in t:
    raise SystemExit(f"instruction leaks inject port {inject}")
if "bakeadmin" in t:
    raise SystemExit("instruction leaks ops surface")
p.write_text(t, encoding="utf-8")
PY

PRIMARY="${EDGE_ARR[0]}"
CID="$(docker run -d --rm \
  --network "${PRIMARY}" \
  -v "${WORKDIR}/instruction.md:/task/instruction.md:ro" \
  python:3.12-alpine sleep 60)"
cleanup() { docker rm -f "${CID}" >/dev/null 2>&1 || true; }
trap 'cleanup; rm -rf "${WORKDIR}"' EXIT
for net in "${EDGE_ARR[@]:1}"; do
  [[ -n "${net}" ]] || continue
  docker network connect "${net}" "${CID}"
done

docker exec -i "${CID}" python - "${INJECT_PORT}" <<'PY'
import http.client
import sys
from pathlib import Path

inject_port = sys.argv[1]
instr = Path("/task/instruction.md").read_text(encoding="utf-8")
if "bakeadmin" in instr:
    raise SystemExit("instruction leaks ops surface")
if Path("/worlds").exists() or Path("/app.secrets.yaml").exists():
    raise SystemExit("ops files visible in sandbox")


def reachable(host: str) -> int:
    conn = http.client.HTTPConnection(host, 80, timeout=15)
    try:
        conn.request("GET", "/")
        resp = conn.getresponse()
        resp.read(64)
        return resp.status
    finally:
        conn.close()


for host in ("wordpress", "roundcube"):
    status = reachable(host)
    if status >= 500:
        raise SystemExit(f"{host}: HTTP {status}")
    print(f"{host}: reachable ({status})")

try:
    conn = http.client.HTTPConnection("inject", 8080, timeout=3)
    conn.request("GET", "/health")
    resp = conn.getresponse()
    raise SystemExit(f"inject reachable from agent sandbox ({resp.status})")
except OSError as exc:
    print(f"inject: blocked ({type(exc).__name__})")

# Host loopback inject (this world's mail_inject port) must be unreachable.
probe_ports = set()
if inject_port != "0":
    probe_ports.add(int(inject_port))
if not probe_ports:
    print("inject: no mail_inject port in world.yaml (skip host probe)")
for port in sorted(probe_ports):
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        raise SystemExit(f"host inject port {port} reachable from agent sandbox ({resp.status})")
    except OSError as exc:
        print(f"127.0.0.1:{port}: blocked ({type(exc).__name__})")
print("sandbox boundary ok")
PY
