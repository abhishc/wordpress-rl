#!/usr/bin/env python3
"""REST oracle using instruction/eval ops credentials (not bakeadmin)."""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

TASK_DIR = Path(__file__).resolve().parents[2]
TASK_YAML = TASK_DIR / "task.yaml"
INSTRUCTION = TASK_DIR / "instruction.md"


def req(method: str, url: str, auth: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {url} -> {exc.code}: {exc.read().decode()}") from exc


def main() -> None:
    task = yaml.safe_load(TASK_YAML.read_text(encoding="utf-8"))
    ev = task.get("eval") or {}
    uni = ev.get("unistore") or {}
    mail = ev.get("mail") or {}
    text = INSTRUCTION.read_text(encoding="utf-8")
    for needle in (mail.get("username"), mail.get("password"), uni.get("username"), uni.get("password")):
        if needle and str(needle) not in text:
            raise SystemExit(f"instruction.md missing eval credential field: {needle!r}")

    user = uni["username"]
    app_pw = (uni.get("application_password") or "").replace(" ", "")
    if not app_pw:
        raise SystemExit("eval.unistore.application_password required for REST oracle")
    auth = base64.b64encode(f"{user}:{app_pw}".encode()).decode()
    base = str(uni["public"]).rstrip("/")
    slug = task["id"]

    def note(oid: int, msg: str) -> None:
        req("POST", f"{base}/wp-json/wc/v3/orders/{oid}/notes", auth, {"note": msg, "customer_note": False})

    def status(oid: int, st: str, **extra) -> None:
        body = {"status": st, **extra}
        req("PUT", f"{base}/wp-json/wc/v3/orders/{oid}", auth, body)

    if slug == "refund-or-replace":
        o = ev["order"]
        oid = int(o["id"])
        note(oid, o["note_token"])
        # fetch customer id from original order
        orig = req("GET", f"{base}/wp-json/wc/v3/orders/{oid}", auth)
        products = req("GET", f"{base}/wp-json/wc/v3/products?sku={o['sku']}", auth)
        pid = products[0]["id"]
        body = {
            "customer_id": orig.get("customer_id") or 0,
            "status": "processing",
            "payment_method": "cod",
            "payment_method_title": "Cash on delivery",
            "set_paid": False,
            "billing": orig.get("billing"),
            "shipping": orig.get("shipping"),
            "line_items": [{"product_id": pid, "quantity": 1}],
            "customer_note": o["replacement_customer_note"],
        }
        created = req("POST", f"{base}/wp-json/wc/v3/orders", auth, body)
        print(f"oracle replacement order id={created['id']}")

    elif slug == "fraud-hold":
        for oid in ev["hold_order_ids"]:
            status(int(oid), "on-hold")
            note(int(oid), ev["note_token"])
        # control untouched
        print("oracle fraud holds applied")

    elif slug == "stockout-substitute":
        o = ev["order"]
        oid = int(o["id"])
        status(oid, "on-hold")
        note(oid, f"{o['note_token']} substitutes {' '.join(o['substitutes'])}")
        print("oracle stockout hold applied")

    elif slug == "partial-fulfill-split":
        o = ev["order"]
        oid = int(o["id"])
        order = req("GET", f"{base}/wp-json/wc/v3/orders/{oid}", auth)
        keep = None
        for li in order.get("line_items") or []:
            if li.get("sku") == o["keep_sku"]:
                keep = {"id": li["id"], "quantity": li["quantity"]}
        if not keep:
            raise SystemExit("keep sku missing on order")
        # Woo update: set drop line qty 0 by sending only keep line with id
        drop_updates = []
        for li in order.get("line_items") or []:
            if li.get("sku") == o["drop_sku"]:
                drop_updates.append({"id": li["id"], "quantity": 0})
            elif li.get("sku") == o["keep_sku"]:
                drop_updates.append({"id": li["id"], "quantity": li["quantity"]})
        req("PUT", f"{base}/wp-json/wc/v3/orders/{oid}", auth, {"line_items": drop_updates})
        note(oid, o["note_token"])
        print("oracle partial fulfill applied")

    elif slug == "wrong-address-in-transit":
        o = ev["order"]
        oid = int(o["id"])
        # verify address not changed by us; cancel + note
        status(oid, "cancelled")
        note(oid, o["note_token"])
        print("oracle address-locked cancel applied")

    else:
        raise SystemExit(f"unknown task oracle: {slug}")


if __name__ == "__main__":
    main()
