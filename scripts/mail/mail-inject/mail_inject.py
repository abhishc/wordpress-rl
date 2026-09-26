#!/usr/bin/env python3
"""POST a raw .eml to the mail inject API (baker ops)."""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "common" / "lib"))
from app_config import load_app_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-yaml", required=True, type=Path, help="Path to Mail app.yaml")
    parser.add_argument("--eml", required=True, type=Path, help="Raw RFC822 .eml file")
    args = parser.parse_args()

    app_yaml = args.app_yaml.resolve()
    eml = args.eml.resolve()
    if not app_yaml.is_file():
        raise SystemExit(f"missing app.yaml: {app_yaml}")
    if not eml.is_file():
        raise SystemExit(f"missing eml: {eml}")

    cfg = load_app_config(app_yaml)
    api = (cfg.get("api") or "").rstrip("/")
    token = (cfg.get("admin") or {}).get("token")
    if not api:
        raise SystemExit(f"app.yaml missing api: {app_yaml}")
    if not token:
        raise SystemExit(f"missing admin.token (app.yaml / app.secrets.yaml): {app_yaml}")

    url = api + "/send"
    body = eml.read_bytes()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "message/rfc822",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(
                f"injected {eml.name} -> HTTP {resp.status} "
                f"{resp.read().decode(errors='replace')}"
            )
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"POST {url} -> HTTP {exc.code}: {exc.read().decode(errors='replace')}"
        ) from exc
    return 0


if __name__ == "__main__":
    sys.exit(main())
