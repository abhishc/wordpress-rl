#!/usr/bin/env python3
"""Contract fingerprint for Harbor-style gates.

Hashes the files that define a task's target (instruction, eval knobs,
rubric, grade, oracle, overlay). A matching stamp means this host ran
gate.sh after the last contract edit. Export refuses stale/missing stamps
so a lab pack cannot ship unverified rubric/oracle drift.

Local-only: stamps are gitignored and excluded from archives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "scripts" / "common" / "lib"
sys.path.insert(0, str(LIB))
from world_manifest import load_manifest, task_slugs  # noqa: E402

STAMP_NAME = ".gate-stamp"
STAMP_VERSION = 1

# Paths relative to task dir. Directories are walked recursively.
CONTRACT_ENTRIES = (
    "instruction.md",
    "task.yaml",
    "overlay",
    "solution/rubric.yaml",
    "solution/grade.py",
    "solution/oracle",
)


def task_dir(world_id: str, task_slug: str) -> Path:
    return ROOT / "worlds" / world_id / "tasks" / task_slug


def stamp_path(world_id: str, task_slug: str) -> Path:
    return task_dir(world_id, task_slug) / "solution" / STAMP_NAME


def _iter_contract_files(td: Path) -> list[Path]:
    files: list[Path] = []
    for entry in CONTRACT_ENTRIES:
        p = td / entry
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if not f.is_file():
                    continue
                if f.name == STAMP_NAME:
                    continue
                if f.name.endswith(".pyc") or "__pycache__" in f.parts:
                    continue
                files.append(f)
    return files


def contract_hash(world_id: str, task_slug: str) -> str:
    td = task_dir(world_id, task_slug)
    if not td.is_dir():
        raise FileNotFoundError(f"missing task dir: {td}")
    h = hashlib.sha256()
    # Shared grader registry — a check change invalidates every task stamp.
    shared = ROOT / "scripts" / "common" / "grade" / "grade_rubric.py"
    if shared.is_file():
        h.update(b"shared:grade_rubric.py\0")
        h.update(shared.read_bytes())
        h.update(b"\0")
    for f in _iter_contract_files(td):
        rel = f.relative_to(td).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def read_stamp(world_id: str, task_slug: str) -> dict | None:
    path = stamp_path(world_id, task_slug)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def is_fresh(world_id: str, task_slug: str) -> bool:
    stamp = read_stamp(world_id, task_slug)
    if not stamp:
        return False
    if stamp.get("version") != STAMP_VERSION:
        return False
    if stamp.get("world") != world_id or stamp.get("task") != task_slug:
        return False
    try:
        expected = contract_hash(world_id, task_slug)
    except FileNotFoundError:
        return False
    return stamp.get("contract_sha256") == expected


def write_stamp(world_id: str, task_slug: str) -> Path:
    digest = contract_hash(world_id, task_slug)
    path = stamp_path(world_id, task_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STAMP_VERSION,
        "world": world_id,
        "task": task_slug,
        "contract_sha256": digest,
        "gated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def dirty_tasks(world_id: str) -> list[str]:
    world_dir = ROOT / "worlds" / world_id
    if not (world_dir / "world.yaml").is_file():
        raise FileNotFoundError(f"missing world: {world_dir}")
    tasks = task_slugs(load_manifest(world_dir))
    return [t for t in tasks if not is_fresh(world_id, t)]


def manifest_gate_lines(world_id: str, *, verified: bool) -> list[str]:
    """Lines for MANIFEST.txt so a pack is self-evidencing.

    Stamps stay local/excluded; their contract_sha256 + gated_utc are copied
    into the archive manifest. SKIP exports must record gate_verified: 0.
    """
    if not verified:
        return ["gate_verified: 0", "gate: skipped"]
    world_dir = ROOT / "worlds" / world_id
    tasks = task_slugs(load_manifest(world_dir))
    lines = ["gate_verified: 1"]
    for t in tasks:
        if not is_fresh(world_id, t):
            raise SystemExit(
                f"refusing manifest gate lines: stale/missing stamp for {world_id}/{t}"
            )
        stamp = read_stamp(world_id, t) or {}
        digest = stamp.get("contract_sha256") or ""
        gated = stamp.get("gated_utc") or ""
        if not digest or not gated:
            raise SystemExit(f"incomplete stamp for {world_id}/{t}")
        lines.append(f"gate.{t}: contract_sha256={digest} gated_utc={gated}")
    return lines


def cmd_hash(args: argparse.Namespace) -> int:
    print(contract_hash(args.world, args.task))
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    path = write_stamp(args.world, args.task)
    print(f"wrote {path}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    if is_fresh(args.world, args.task):
        stamp = read_stamp(args.world, args.task) or {}
        print(
            f"fresh: {args.world}/{args.task} "
            f"gated_utc={stamp.get('gated_utc', '?')}"
        )
        return 0
    digest = contract_hash(args.world, args.task)
    stamp = read_stamp(args.world, args.task)
    if stamp is None:
        print(
            f"dirty: {args.world}/{args.task} (no stamp; "
            f"contract_sha256={digest[:12]}…)"
        )
    else:
        print(
            f"dirty: {args.world}/{args.task} "
            f"(stamp={str(stamp.get('contract_sha256', ''))[:12]}… "
            f"now={digest[:12]}…)"
        )
    return 1


def cmd_list_dirty(args: argparse.Namespace) -> int:
    dirty = dirty_tasks(args.world)
    for t in dirty:
        print(t)
    return 1 if dirty else 0


def cmd_check_world(args: argparse.Namespace) -> int:
    dirty = dirty_tasks(args.world)
    if not dirty:
        print(f"all tasks fresh: {args.world}")
        return 0
    print(f"stale/missing gate stamps ({len(dirty)}):", file=sys.stderr)
    for t in dirty:
        print(f"  {t}", file=sys.stderr)
    print(
        f"Run: WORLD={args.world} ./scripts/common/gate/gate_dirty.sh",
        file=sys.stderr,
    )
    print(
        "Or gate one task, then re-export. "
        "WIP only: SKIP_GATE_STAMP=1 ./scripts/common/export-world/export_world.sh",
        file=sys.stderr,
    )
    return 1


def cmd_manifest_lines(args: argparse.Namespace) -> int:
    verified = not bool(args.skipped)
    for line in manifest_gate_lines(args.world, verified=verified):
        print(line)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--world",
        default="",
        help="world id (required via --world or $WORLD; no default)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("hash", help="print contract sha256")
    h.add_argument("--task", required=True)
    h.set_defaults(func=cmd_hash)

    w = sub.add_parser("write", help="write stamp after a successful gate")
    w.add_argument("--task", required=True)
    w.set_defaults(func=cmd_write)

    c = sub.add_parser("check", help="exit 0 if stamp matches contract")
    c.add_argument("--task", required=True)
    c.set_defaults(func=cmd_check)

    ld = sub.add_parser("list-dirty", help="print dirty task slugs")
    ld.set_defaults(func=cmd_list_dirty)

    cw = sub.add_parser("check-world", help="exit 1 if any task is dirty")
    cw.set_defaults(func=cmd_check_world)

    ml = sub.add_parser(
        "manifest-lines",
        help="print gate evidence lines for MANIFEST.txt",
    )
    ml.add_argument(
        "--skipped",
        action="store_true",
        help="emit gate_verified: 0 (SKIP_GATE_STAMP export)",
    )
    ml.set_defaults(func=cmd_manifest_lines)

    args = p.parse_args()
    from require_world import require_world

    world = require_world(args.world or None, root=ROOT)
    args.world = world
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
