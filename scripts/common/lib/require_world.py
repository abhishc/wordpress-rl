"""Require an explicit world id — never silently default to meridian-mail."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def require_world(cli_value: str | None = None, *, root: Path | None = None) -> str:
    world = (cli_value or "").strip() or (os.environ.get("WORLD") or "").strip()
    if not world:
        print(
            "WORLD is required (--world or env WORLD). "
            "No default — refusing silent meridian-mail fallback.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if root is not None:
        manifest = root / "worlds" / world / "world.yaml"
        if not manifest.is_file():
            print(f"missing world: {manifest}", file=sys.stderr)
            raise SystemExit(1)
    return world
