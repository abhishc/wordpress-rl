#!/usr/bin/env python3
"""CLI: grade a task rubric against a world (shared check registry)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from grade_rubric import grade_rubric  # noqa: E402
from require_world import require_world  # noqa: E402


def load_world_apps(world_dir: Path) -> dict[str, Path]:
    import yaml

    manifest = yaml.safe_load((world_dir / "world.yaml").read_text(encoding="utf-8"))
    apps = {}
    for entry in manifest.get("apps") or []:
        aid = entry["id"] if isinstance(entry, dict) else entry
        path = world_dir / "apps" / aid / "app.yaml"
        if not path.is_file():
            raise SystemExit(f"missing {path}")
        apps[aid] = path
    return apps


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--world",
        default=None,
        help="World id under worlds/ (or set WORLD). Required — no default.",
    )
    ap.add_argument("--task", required=True)
    ap.add_argument("--rubric", type=Path, default=None)
    args = ap.parse_args()
    world = require_world(args.world, root=ROOT)

    world_dir = ROOT / "worlds" / world
    task_yaml = world_dir / "tasks" / args.task / "task.yaml"
    rubric = args.rubric or (
        world_dir / "tasks" / args.task / "solution" / "rubric.yaml"
    )
    apps = load_world_apps(world_dir)
    shop_eval = None
    if task_yaml.is_file():
        import yaml

        task = yaml.safe_load(task_yaml.read_text(encoding="utf-8")) or {}
        ev = task.get("eval") or {}
        shop_eval = ev.get("unistore") or ev.get("meridian")
    result = grade_rubric(rubric, apps, shop_eval=shop_eval)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("passed") else 1)


if __name__ == "__main__":
    main()
