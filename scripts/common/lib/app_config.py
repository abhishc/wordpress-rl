"""Load app.yaml merged with optional app.secrets.yaml (ops only)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _parse_simple_yaml(path: Path) -> dict[str, Any]:
    """Minimal YAML subset used by app.yaml files (no nested lists of maps)."""
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"expected mapping in {path}")
        return data
    except ImportError:
        # Fallback: very small parser for our files
        root: dict[str, Any] = {}
        stack: list[tuple[int, dict[str, Any]]] = [(0, root)]
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            line = raw.strip()
            while stack and indent < stack[-1][0]:
                stack.pop()
            cur = stack[-1][1]
            if line.endswith(":") and ":" == line[-1] and line.count(":") == 1:
                key = line[:-1].strip()
                nxt: dict[str, Any] = {}
                cur[key] = nxt
                stack.append((indent + 2, nxt))
                continue
            if line.startswith("- "):
                # list under last key — skip detailed; yaml preferred
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                cur[k.strip()] = v.strip().strip("'").strip('"')
        return root


def deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_app_config(app_yaml: Path) -> dict[str, Any]:
    app_yaml = Path(app_yaml)
    cfg = _parse_simple_yaml(app_yaml)
    secrets = app_yaml.with_name("app.secrets.yaml")
    if secrets.is_file():
        cfg = deep_merge(cfg, _parse_simple_yaml(secrets))
    return cfg


def site_from_login_url(login_url: str) -> str:
    site = login_url.rstrip("/")
    if site.endswith("/wp-admin"):
        site = site[: -len("/wp-admin")]
    return site
