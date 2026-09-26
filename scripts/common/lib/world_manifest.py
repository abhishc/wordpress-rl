"""Load and query worlds/<id>/world.yaml."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def load_manifest(world_dir: Path) -> dict[str, Any]:
    path = Path(world_dir) / "world.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"bad manifest: {path}")
    return data


def app_entries(manifest: dict) -> list[dict]:
    out = []
    for a in manifest.get("apps") or []:
        if isinstance(a, str):
            out.append({"id": a})
        else:
            out.append(dict(a))
    return out


def app_ids(manifest: dict) -> list[str]:
    return [a["id"] for a in app_entries(manifest)]


def overlay_apps(manifest: dict) -> list[dict]:
    """Apps that declare an overlay handler (e.g. overlay: eml)."""
    return [a for a in app_entries(manifest) if a.get("overlay")]


def task_slugs(manifest: dict) -> list[str]:
    tasks = manifest.get("tasks") or []
    out = []
    for t in tasks:
        out.append(t if isinstance(t, str) else t["id"])
    return out


def validate_ports(world_dir: Path, manifest: dict) -> list[str]:
    """Return list of error strings if compose host ports disagree with manifest."""
    errors: list[str] = []
    ports = manifest.get("ports") or {}
    if not ports:
        return errors
    # Collect published host ports from all app compose files
    found: set[int] = set()
    for aid in app_ids(manifest):
        compose = Path(world_dir) / "apps" / aid / "compose.yaml"
        if not compose.is_file():
            errors.append(f"missing compose: {compose}")
            continue
        text = compose.read_text(encoding="utf-8")
        for m in re.finditer(r"127\.0\.0\.1:(\d+):", text):
            found.add(int(m.group(1)))
    expected = {int(v) for v in ports.values()}
    missing = expected - found
    extra_doc = found - expected
    if missing:
        errors.append(f"manifest ports not in compose: {sorted(missing)}")
    if extra_doc:
        # warn only — compose may publish only subset; treat unexpected as error
        errors.append(f"compose ports not in manifest: {sorted(extra_doc)}")
    return errors
