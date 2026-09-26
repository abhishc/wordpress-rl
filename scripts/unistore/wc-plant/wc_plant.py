#!/usr/bin/env python3
"""Plant UniStore populate fixtures via WP + Woo REST. Baker-only."""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "common" / "lib"))
from app_config import load_app_config, site_from_login_url  # noqa: E402


def auth_header(admin: dict) -> str:
    user = admin.get("username")
    app_pw = admin.get("application_password")
    if not user or not app_pw:
        raise SystemExit("admin.username / admin.application_password required")
    token = base64.b64encode(f"{user}:{app_pw}".encode()).decode()
    return f"Basic {token}"


def request_json(method: str, url: str, headers: dict, body: dict | None = None, timeout: int = 60):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc


def load_list(fixtures: Path, name: str) -> list:
    path = fixtures / name
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path} must be a JSON list")
    return data


def find_user(base: str, headers: dict, username: str) -> dict | None:
    url = (
        f"{base}/wp-json/wp/v2/users?search={urllib.parse.quote(username)}"
        f"&context=edit&per_page=100"
    )
    _, users = request_json("GET", url, headers)
    for user in users or []:
        if user.get("slug") == username or user.get("username") == username:
            return user
    return None


def ensure_staff(base: str, headers: dict, staff: list[dict]) -> None:
    for person in staff:
        existing = find_user(base, headers, person["username"])
        if existing:
            print(f"staff exists: {person['username']} id={existing['id']}")
            continue
        body = {
            "username": person["username"],
            "email": person["email"],
            "password": person["password"],
            "name": person.get("name") or person["username"],
            "roles": [person.get("role") or "shop_manager"],
        }
        _, created = request_json("POST", f"{base}/wp-json/wp/v2/users", headers, body)
        print(f"staff created: {person['username']} id={created['id']}")


def ensure_categories(base: str, headers: dict, cats: list[dict]) -> dict[str, int]:
    """Return slug -> term_id."""
    _, existing = request_json(
        "GET", f"{base}/wp-json/wc/v3/products/categories?per_page=100", headers
    )
    by_slug = {c["slug"]: c["id"] for c in existing or []}
    for cat in cats:
        if cat["slug"] in by_slug:
            continue
        _, created = request_json(
            "POST",
            f"{base}/wp-json/wc/v3/products/categories",
            headers,
            {"name": cat["name"], "slug": cat["slug"]},
        )
        by_slug[cat["slug"]] = created["id"]
        print(f"category: {cat['slug']} -> {created['id']}")
    return by_slug


def find_product_by_sku(base: str, headers: dict, sku: str) -> dict | None:
    url = f"{base}/wp-json/wc/v3/products?sku={urllib.parse.quote(sku)}&per_page=10"
    _, items = request_json("GET", url, headers)
    for item in items or []:
        if item.get("sku") == sku:
            return item
    return None


def plant_products(base: str, headers: dict, products: list[dict], cat_ids: dict[str, int]) -> dict[str, int]:
    """Return sku -> product_id (parents for variables; variation skus included)."""
    sku_to_id: dict[str, int] = {}
    for prod in products:
        existing = find_product_by_sku(base, headers, prod["sku"])
        if existing:
            sku_to_id[prod["sku"]] = existing["id"]
            print(f"product exists: {prod['sku']} id={existing['id']}")
            if prod["type"] == "variable":
                _, vars_ = request_json(
                    "GET",
                    f"{base}/wp-json/wc/v3/products/{existing['id']}/variations?per_page=100",
                    headers,
                )
                for v in vars_ or []:
                    if v.get("sku"):
                        sku_to_id[v["sku"]] = v["id"]
            continue

        cats = [{"id": cat_ids[s]} for s in prod["categories"] if s in cat_ids]
        if prod["type"] == "simple":
            body = {
                "name": prod["name"],
                "type": "simple",
                "sku": prod["sku"],
                "regular_price": prod["regular_price"],
                "description": prod.get("description") or "",
                "manage_stock": prod.get("manage_stock", True),
                "stock_quantity": prod["stock_quantity"],
                "stock_status": prod["stock_status"],
                "categories": cats,
            }
            _, created = request_json("POST", f"{base}/wp-json/wc/v3/products", headers, body)
            sku_to_id[prod["sku"]] = created["id"]
            print(f"product: {prod['sku']} -> {created['id']}")
            continue

        # variable parent
        body = {
            "name": prod["name"],
            "type": "variable",
            "sku": prod["sku"],
            "description": prod.get("description") or "",
            "categories": cats,
            "attributes": prod["attributes"],
        }
        _, parent = request_json("POST", f"{base}/wp-json/wc/v3/products", headers, body)
        sku_to_id[prod["sku"]] = parent["id"]
        print(f"variable: {prod['sku']} -> {parent['id']}")
        for var in prod.get("variations") or []:
            vbody = {
                "sku": var["sku"],
                "regular_price": var["regular_price"],
                "manage_stock": var.get("manage_stock", True),
                "stock_quantity": var["stock_quantity"],
                "stock_status": var["stock_status"],
                "attributes": var["attributes"],
            }
            _, created = request_json(
                "POST",
                f"{base}/wp-json/wc/v3/products/{parent['id']}/variations",
                headers,
                vbody,
            )
            sku_to_id[var["sku"]] = created["id"]
            print(f"  variation: {var['sku']} -> {created['id']}")
    return sku_to_id


def find_customer(base: str, headers: dict, email: str) -> dict | None:
    url = f"{base}/wp-json/wc/v3/customers?email={urllib.parse.quote(email)}&per_page=10"
    _, items = request_json("GET", url, headers)
    for item in items or []:
        if item.get("email") == email:
            return item
    return None


def plant_customers(base: str, headers: dict, customers: list[dict]) -> dict[str, int]:
    email_to_id: dict[str, int] = {}
    for cust in customers:
        existing = find_customer(base, headers, cust["email"])
        if existing:
            email_to_id[cust["email"]] = existing["id"]
            continue
        body = {
            "email": cust["email"],
            "first_name": cust["first_name"],
            "last_name": cust["last_name"],
            "username": cust["username"],
            "password": cust["password"],
            "billing": cust["billing"],
            "shipping": cust["shipping"],
        }
        _, created = request_json("POST", f"{base}/wp-json/wc/v3/customers", headers, body)
        email_to_id[cust["email"]] = created["id"]
        print(f"customer: {cust['email']} -> {created['id']}")
    return email_to_id


def plant_coupons(base: str, headers: dict, coupons: list[dict]) -> None:
    _, existing = request_json("GET", f"{base}/wp-json/wc/v3/coupons?per_page=100", headers)
    have = {c["code"].lower() for c in existing or []}
    for coup in coupons:
        if coup["code"].lower() in have:
            print(f"coupon exists: {coup['code']}")
            continue
        body = {
            "code": coup["code"],
            "discount_type": coup["discount_type"],
            "amount": coup["amount"],
            "description": coup.get("description") or "",
            "individual_use": coup.get("individual_use", False),
        }
        if coup.get("date_expires"):
            body["date_expires"] = coup["date_expires"]
        _, created = request_json("POST", f"{base}/wp-json/wc/v3/coupons", headers, body)
        print(f"coupon: {coup['code']} -> {created['id']}")


def add_order_note(base: str, headers: dict, order_id: int, note: str) -> None:
    request_json(
        "POST",
        f"{base}/wp-json/wc/v3/orders/{order_id}/notes",
        headers,
        {"note": note, "customer_note": False},
    )


def plant_orders(
    base: str,
    headers: dict,
    orders: list[dict],
    sku_to_id: dict[str, int],
    email_to_id: dict[str, int],
) -> None:
    # Skip if we already have many orders (idempotent-ish)
    _, existing = request_json("GET", f"{base}/wp-json/wc/v3/orders?per_page=1", headers)
    # Always plant; use fixture meta to detect? For first plant empty store.
    # If products empty plant would fail earlier. Check order count:
    _, counted = request_json(
        "GET", f"{base}/wp-json/wc/v3/orders?per_page=1&status=any", headers
    )
    # Woo returns X-WP-Total header — urllib doesn't expose easily; probe search
    # For simplicity: if any order exists with meta fixture, skip all.
    _, probe = request_json(
        "GET",
        f"{base}/wp-json/wc/v3/orders?search=fixture&per_page=5&status=any",
        headers,
    )
    # Better: list first page and look for meta_data key
    _, page = request_json(
        "GET", f"{base}/wp-json/wc/v3/orders?per_page=20&status=any", headers
    )
    for o in page or []:
        for m in o.get("meta_data") or []:
            if m.get("key") == "_unistore_fixture_index":
                print(f"orders already planted (saw fixture meta on order {o['id']}); skip")
                return

    for order in orders:
        line_items = []
        for line in order["line_items"]:
            sku = line["sku"]
            pid = sku_to_id.get(sku)
            if not pid:
                raise SystemExit(f"unknown sku in order fixture {order['fixture_index']}: {sku}")
            line_items.append({"product_id": pid, "quantity": line["quantity"]})

        body: dict = {
            "status": order["status"],
            "customer_id": email_to_id.get(order["customer_email"], 0),
            "payment_method": order.get("payment_method") or "cod",
            "payment_method_title": order.get("payment_method_title") or "Cash on delivery",
            "set_paid": order.get("set_paid", False),
            "billing": order["billing"],
            "shipping": order["shipping"],
            "line_items": line_items,
            "meta_data": [
                {"key": "_unistore_fixture_index", "value": str(order["fixture_index"])},
                {
                    "key": "_unistore_scenario",
                    "value": (order.get("meta") or {}).get("scenario") or "",
                },
            ],
        }
        if order.get("coupon_lines"):
            body["coupon_lines"] = order["coupon_lines"]
        if order.get("customer_note"):
            body["customer_note"] = order["customer_note"]

        _, created = request_json("POST", f"{base}/wp-json/wc/v3/orders", headers, body)
        oid = created["id"]
        # WC REST treats date_created_gmt as read-only on create/update — backdate
        # after plant via WooCommerce CRUD (see backdate_orders_via_wp).
        for note in order.get("order_notes") or []:
            add_order_note(base, headers, oid, note)
        print(f"order fixture={order['fixture_index']} -> id={oid} status={order['status']}")
        time.sleep(0.05)


def _compose_wordpress_php(app_yaml: Path, script: str) -> None:
    app_dir = app_yaml.parent
    compose_file = app_dir / "compose.yaml"
    env_file = app_dir / ".env"
    if not compose_file.is_file() or not env_file.is_file():
        raise SystemExit(f"missing compose/.env under {app_dir}")
    name = "unistore"
    for line in compose_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            break
    subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "--project-name",
            name,
            "exec",
            "-T",
            "wordpress",
            "php",
            "-r",
            script,
        ],
        check=True,
        cwd=str(ROOT),
    )


def backdate_orders_via_wp(app_yaml: Path, fixtures: Path) -> None:
    """Set order created/paid/completed from fixtures (REST cannot).

    Maps `_unistore_fixture_index` → fixture date fields, then uses
    WC_Order setters + save so post_date, paid/completed meta, and
    subsequent analytics sync see the intended timeline.
    """
    print("backdating orders from fixtures (WC_Order setters)...")
    by_index: dict[str, dict] = {}
    for order in load_list(fixtures, "orders.json"):
        created = order.get("date_created_gmt")
        if not created:
            continue
        entry: dict = {"created": created}
        if order.get("date_completed_gmt"):
            entry["completed"] = order["date_completed_gmt"]
        if order.get("set_paid"):
            entry["paid"] = created
        by_index[str(order["fixture_index"])] = entry
    payload = json.dumps(by_index)
    # Embed JSON; escape for single-quoted PHP string is messy — write to container stdin via env file
    map_path = fixtures / ".date_map.json"
    map_path.write_text(payload + "\n", encoding="utf-8")
    # copy into container
    app_dir = app_yaml.parent
    compose_file = app_dir / "compose.yaml"
    env_file = app_dir / ".env"
    name = "unistore"
    for line in compose_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            break
    subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "--project-name",
            name,
            "cp",
            str(map_path),
            "wordpress:/tmp/unistore_date_map.json",
        ],
        check=True,
        cwd=str(ROOT),
    )
    script = r"""
require "/var/www/html/wp-load.php";
$map = json_decode(file_get_contents("/tmp/unistore_date_map.json"), true);
if (!is_array($map)) { fwrite(STDERR, "bad date map\n"); exit(1); }
$q = new WP_Query([
  "post_type" => "shop_order",
  "post_status" => "any",
  "posts_per_page" => -1,
  "fields" => "ids",
]);
$n = 0; $miss = 0;
foreach ($q->posts as $oid) {
  $fi = get_post_meta($oid, "_unistore_fixture_index", true);
  if ($fi === "" || $fi === null || !isset($map[(string)$fi])) { continue; }
  $row = $map[(string)$fi];
  $order = wc_get_order($oid);
  if (!$order) { $miss++; continue; }
  $created = new WC_DateTime($row["created"], new DateTimeZone("UTC"));
  $order->set_date_created($created);
  if (!empty($row["paid"])) {
    $order->set_date_paid(new WC_DateTime($row["paid"], new DateTimeZone("UTC")));
  }
  if (!empty($row["completed"])) {
    $order->set_date_completed(new WC_DateTime($row["completed"], new DateTimeZone("UTC")));
  }
  $order->save();
  $n++;
}
echo "backdated=$n miss=$miss\n";
"""
    _compose_wordpress_php(app_yaml, script)
    try:
        map_path.unlink()
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--app-yaml", type=Path, required=True)
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument(
        "--backdate-only",
        action="store_true",
        help="Only rewrite order dates from fixtures (no plant)",
    )
    args = ap.parse_args()
    fixtures = args.fixtures.resolve()
    app_yaml = args.app_yaml.resolve()
    if not (fixtures / "manifest.json").is_file():
        raise SystemExit(f"missing fixtures under {fixtures}")

    if args.backdate_only:
        backdate_orders_via_wp(app_yaml, fixtures)
        sync_wc_analytics(app_yaml)
        print("backdate complete")
        return 0

    cfg = load_app_config(app_yaml)
    admin = cfg.get("admin") or {}
    base = site_from_login_url(cfg["login"]["url"])
    headers = {
        "Authorization": auth_header(admin),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    ensure_staff(base, headers, load_list(fixtures, "staff.json"))
    cat_ids = ensure_categories(base, headers, load_list(fixtures, "categories.json"))
    sku_to_id = plant_products(base, headers, load_list(fixtures, "products.json"), cat_ids)
    email_to_id = plant_customers(base, headers, load_list(fixtures, "customers.json"))
    plant_coupons(base, headers, load_list(fixtures, "coupons.json"))
    plant_orders(base, headers, load_list(fixtures, "orders.json"), sku_to_id, email_to_id)
    backdate_orders_via_wp(app_yaml, fixtures)
    sync_wc_analytics(app_yaml)
    print("plant complete")
    return 0


def sync_wc_analytics(app_yaml: Path) -> None:
    """Fill wp_wc_order_stats so WooCommerce > Customers shows order counts.

    REST create sets _customer_user but does not populate analytics lookup tables.
    """
    print("syncing WooCommerce order analytics (wp_wc_order_stats)...")
    script = r"""
require "/var/www/html/wp-load.php";
use Automattic\WooCommerce\Admin\API\Reports\Orders\Stats\DataStore as OrdersStatsDataStore;
use Automattic\WooCommerce\Admin\API\Reports\Customers\DataStore as CustomersDataStore;
$ids = get_posts(["post_type"=>"shop_order","post_status"=>"any","numberposts"=>-1,"fields"=>"ids"]);
$n = 0;
foreach ($ids as $id) {
  if (OrdersStatsDataStore::sync_order($id) !== false) {
    $n++;
  }
  if (method_exists(CustomersDataStore::class, "sync_order_customer")) {
    CustomersDataStore::sync_order_customer($id);
  }
}
echo "analytics_synced=$n\n";
"""
    _compose_wordpress_php(app_yaml, script)


if __name__ == "__main__":
    raise SystemExit(main())
