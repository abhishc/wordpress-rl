"""Shared rubric grader + check-type registry."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import yaml

from app_config import load_app_config, site_from_login_url

CheckFn = Callable[[dict, dict, dict], tuple[bool, dict]]


def _request(url: str, auth: str | None = None) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    if auth:
        req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _title_of(post: dict) -> str:
    t = post.get("title") or {}
    return (t.get("raw") or t.get("rendered") or "").strip()


def _content_of(post: dict) -> str:
    c = post.get("content") or {}
    return (c.get("raw") or "") + "\n" + (c.get("rendered") or "")


def _basic_auth(admin: dict) -> str:
    return base64.b64encode(
        f"{admin['username']}:{admin['application_password']}".encode()
    ).decode()


def _find_post(posts: list, title: str) -> dict | None:
    exact = [p for p in posts if _title_of(p) == title]
    if not exact:
        return None
    published = [p for p in exact if p.get("status") == "publish"]
    pool = published or exact
    if len(pool) > 1:
        raise AmbiguousPost(
            f"{len(pool)} posts titled {title!r} (statuses={[p.get('status') for p in pool]})"
        )
    return pool[0]


class AmbiguousPost(Exception):
    pass


class GradeContext:
    def __init__(
        self,
        apps: dict[str, Path],
        shop_eval: dict[str, Any] | None = None,
    ):
        """apps: logical name → app.yaml path (secrets merged).

        shop_eval: optional task.yaml eval.<shop> block (username +
        application_password). Preferred for WC/WP REST so lab packs
        grade without baker app.secrets.yaml.
        """
        self.apps = {k: load_app_config(v) for k, v in apps.items()}
        self.paths = apps
        self.shop_eval = dict(shop_eval) if shop_eval else None
        self._posts: dict[tuple[str, str], dict | None] = {}
        self._authors: dict[tuple[str, int], str] = {}
        self.detail: dict[str, Any] = {"posts": {}}

    def meridian(self) -> dict:
        return self.apps["meridian"]

    def fetch_post(self, title: str) -> dict | None:
        key = ("meridian", title)
        if key in self._posts:
            return self._posts[key]
        cfg = self.meridian()
        site = site_from_login_url(cfg["login"]["url"])
        admin = cfg.get("admin") or {}
        token = _basic_auth(admin)
        q = urllib.parse.urlencode(
            {
                "per_page": 100,
                "status": "publish,draft,pending,private",
                "search": title,
                "context": "edit",
            }
        )
        try:
            posts = _request(f"{site}/wp-json/wp/v2/posts?{q}", auth=token)
        except urllib.error.URLError:
            self._posts[key] = None
            return None
        try:
            post = _find_post(posts, title)
        except AmbiguousPost as exc:
            self.detail.setdefault("ambiguous", []).append(str(exc))
            self._posts[key] = None
            return None
        self._posts[key] = post
        return post

    def author_slug(self, post: dict) -> str:
        cfg = self.meridian()
        site = site_from_login_url(cfg["login"]["url"])
        admin = cfg.get("admin") or {}
        token = _basic_auth(admin)
        aid = int(post.get("author") or 0)
        key = ("meridian", aid)
        if key in self._authors:
            return self._authors[key]
        try:
            user = _request(f"{site}/wp-json/wp/v2/users/{aid}", auth=token)
            slug = user.get("slug") or ""
        except urllib.error.HTTPError:
            slug = ""
        self._authors[key] = slug
        return slug


def check_wp_post_title(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    title = check["title"]
    post = ctx.fetch_post(title)
    d = {"title": title, "found": post is not None}
    if post:
        ctx.detail["posts"].setdefault(title, {})["post_id"] = post.get("id")
    return post is not None, d


def check_wp_post_status(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    title = check["title"]
    post = ctx.fetch_post(title)
    status = post.get("status") if post else None
    if post:
        ctx.detail["posts"].setdefault(title, {})["status"] = status
    return bool(post) and status == check.get("status"), {"status": status}


def check_wp_post_author_slug(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    title = check["title"]
    post = ctx.fetch_post(title)
    if not post:
        return False, {"author_slug": None}
    slug = ctx.author_slug(post)
    ctx.detail["posts"].setdefault(title, {})["author_slug"] = slug
    return slug == check.get("author_slug"), {"author_slug": slug}


def check_wp_post_body_contains(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    title = check["title"]
    post = ctx.fetch_post(title)
    if not post:
        return False, {"matched": False}
    content = _content_of(post)
    ctx.detail["posts"].setdefault(title, {})["content_len"] = len(content.strip())
    text = check.get("text") or ""
    return text in content, {"matched": text in content}


def check_http_url_ok(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    url = check.get("url") or ""
    if not url:
        return False, {"error": "missing url"}
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            code = getattr(resp, "status", 200)
            return 200 <= int(code) < 400, {"status": code}
    except Exception as exc:
        return False, {"error": str(exc)}


def check_mail_ui_reachable(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    app_id = check.get("app") or "mail"
    cfg = ctx.apps.get(app_id)
    if not cfg:
        return False, {"error": f"no app {app_id}"}
    url = (cfg.get("login") or {}).get("url") or ""
    return check_http_url_ok(ctx, {"url": url}, _crit)


def check_mail_inject_health(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    app_id = check.get("app") or "mail"
    cfg = ctx.apps.get(app_id)
    if not cfg:
        return False, {"error": f"no app {app_id}"}
    api = (cfg.get("api") or "").rstrip("/")
    if not api:
        return False, {"error": "missing api"}
    return check_http_url_ok(ctx, {"url": api + "/health"}, _crit)


def _shop_cfg(ctx: GradeContext) -> dict | None:
    return ctx.apps.get("unistore") or ctx.apps.get("meridian")


def _shop_auth(ctx: GradeContext) -> tuple[str, str] | tuple[None, None]:
    cfg = _shop_cfg(ctx)
    if not cfg:
        return None, None
    site = site_from_login_url(cfg["login"]["url"])
    # Lab path: task eval ops credentials (shipped in task.yaml).
    if ctx.shop_eval:
        user = ctx.shop_eval.get("username")
        app_pw = (ctx.shop_eval.get("application_password") or "").replace(" ", "")
        if user and app_pw:
            return site, base64.b64encode(f"{user}:{app_pw}".encode()).decode()
    # Baker path: app.secrets.yaml / app.yaml admin.
    admin = cfg.get("admin") or {}
    if not admin.get("username") or not admin.get("application_password"):
        return None, None
    return site, _basic_auth(admin)


def _wc_get(ctx: GradeContext, path: str) -> Any | None:
    site, auth = _shop_auth(ctx)
    if not site or not auth:
        return None
    try:
        return _request(f"{site}/wp-json/wc/v3/{path.lstrip('/')}", auth=auth)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def _order_notes(ctx: GradeContext, order_id: int) -> list[dict]:
    notes = _wc_get(ctx, f"orders/{order_id}/notes?per_page=100")
    return notes if isinstance(notes, list) else []


def check_wc_order_status(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    oid = int(check["order_id"])
    order = _wc_get(ctx, f"orders/{oid}")
    status = order.get("status") if order else None
    expected = check.get("status")
    allowed = check.get("status_in")
    if allowed:
        ok = status in list(allowed)
    else:
        ok = status == expected
    return bool(ok), {"order_id": oid, "status": status}


def check_wc_order_note_contains(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    oid = int(check["order_id"])
    needle = check.get("text") or ""
    notes = _order_notes(ctx, oid)
    if check.get("exact"):
        ok = any((n.get("note") or "") == needle for n in notes)
        return ok and bool(needle), {"order_id": oid, "matched": ok, "exact": True}
    hay = "\n".join((n.get("note") or "") for n in notes).lower()
    return needle.lower() in hay and bool(needle), {
        "order_id": oid,
        "matched": needle.lower() in hay,
    }


def check_wc_order_shipping_address1(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    oid = int(check["order_id"])
    order = _wc_get(ctx, f"orders/{oid}")
    got = ((order or {}).get("shipping") or {}).get("address_1")
    exp = check.get("address_1")
    return got == exp, {"order_id": oid, "address_1": got}


def check_wc_order_line_skus(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    oid = int(check["order_id"])
    order = _wc_get(ctx, f"orders/{oid}")
    if not order:
        return False, {"order_id": oid, "skus": None}
    skus = sorted(
        li.get("sku") or ""
        for li in (order.get("line_items") or [])
        if int(li.get("quantity") or 0) > 0
    )
    expected = sorted(check.get("skus") or [])
    return skus == expected, {"order_id": oid, "skus": skus, "expected": expected}


def check_wc_order_no_refunds(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    oid = int(check["order_id"])
    refunds = _wc_get(ctx, f"orders/{oid}/refunds")
    if refunds is None:
        return False, {"order_id": oid, "error": "refunds fetch failed"}
    n = len(refunds) if isinstance(refunds, list) else -1
    return n == 0, {"order_id": oid, "refund_count": n}


def check_wc_replacement_order(ctx: GradeContext, check: dict, _crit: dict) -> tuple[bool, dict]:
    """Find a replacement order matching the full expected semantic state.

    Required-ish knobs (set what the task promises):
      exclude_order_id, customer_email, sku, quantity, payment_method,
      customer_note (exact) or customer_note_contains (legacy soft),
      match_customer_id_from_order, sole_line_item (bool).
    """
    exclude = int(check.get("exclude_order_id") or 0)
    sku = check.get("sku") or ""
    note_exact = check.get("customer_note")
    note_sub = check.get("customer_note_contains") or ""
    customer_email = (check.get("customer_email") or "").lower()
    quantity = int(check.get("quantity") or 1)
    payment_method = check.get("payment_method")
    sole = bool(check.get("sole_line_item", True))
    source_oid = check.get("match_customer_id_from_order")

    source_customer_id = None
    if source_oid is not None:
        orig = _wc_get(ctx, f"orders/{int(source_oid)}")
        if not orig:
            return False, {"error": f"source order {source_oid} missing"}
        source_customer_id = int(orig.get("customer_id") or 0)

    orders = _wc_get(ctx, "orders?per_page=100&status=any&orderby=date&order=desc") or []
    hits = []
    rejected = []
    for o in orders:
        oid = int(o.get("id") or 0)
        if oid == exclude:
            continue
        email = ((o.get("billing") or {}).get("email") or "").lower()
        if customer_email and email != customer_email:
            continue
        lines = [li for li in (o.get("line_items") or []) if int(li.get("quantity") or 0) > 0]
        sku_lines = [li for li in lines if (li.get("sku") or "") == sku]
        if len(sku_lines) != 1:
            continue
        qty = int(sku_lines[0].get("quantity") or 0)
        if qty != quantity:
            rejected.append({"id": oid, "reason": "qty", "qty": qty})
            continue
        if sole and len(lines) != 1:
            rejected.append({"id": oid, "reason": "extra_lines", "skus": [li.get("sku") for li in lines]})
            continue
        if payment_method and (o.get("payment_method") or "") != payment_method:
            rejected.append({"id": oid, "reason": "payment", "payment_method": o.get("payment_method")})
            continue
        cnote = o.get("customer_note") or ""
        if note_exact is not None:
            if cnote != note_exact:
                rejected.append({"id": oid, "reason": "note_exact"})
                continue
        elif note_sub and note_sub not in cnote:
            rejected.append({"id": oid, "reason": "note_sub"})
            continue
        if source_customer_id is not None and int(o.get("customer_id") or 0) != source_customer_id:
            rejected.append({"id": oid, "reason": "customer_id"})
            continue
        hits.append(oid)
    return bool(hits), {"matches": hits, "rejected_near": rejected[:5]}


REGISTRY: dict[str, CheckFn] = {
    "wp_post_title": check_wp_post_title,
    "wp_post_status": check_wp_post_status,
    "wp_post_author_slug": check_wp_post_author_slug,
    "wp_post_body_contains": check_wp_post_body_contains,
    "http_url_ok": check_http_url_ok,
    "mail_ui_reachable": check_mail_ui_reachable,
    "mail_inject_health": check_mail_inject_health,
    "wc_order_status": check_wc_order_status,
    "wc_order_note_contains": check_wc_order_note_contains,
    "wc_order_shipping_address1": check_wc_order_shipping_address1,
    "wc_order_line_skus": check_wc_order_line_skus,
    "wc_order_no_refunds": check_wc_order_no_refunds,
    "wc_replacement_order": check_wc_replacement_order,
}


def grade_rubric(
    rubric_path: Path,
    apps: dict[str, Path],
    shop_eval: dict[str, Any] | None = None,
) -> dict:
    rubric = yaml.safe_load(Path(rubric_path).read_text(encoding="utf-8"))
    criteria = list(rubric.get("criteria") or [])
    scoring = rubric.get("scoring") or "all_or_nothing"
    ctx = GradeContext(apps, shop_eval=shop_eval)
    results: dict[str, bool] = {}
    per: dict[str, Any] = {}

    needs_wp = any(
        (c.get("check") or {}).get("type", "").startswith(("wp_", "wc_")) for c in criteria
    )
    shop = _shop_cfg(ctx)
    if needs_wp and shop:
        try:
            site = site_from_login_url(shop["login"]["url"])
            urllib.request.urlopen(site, timeout=10)
        except Exception as exc:
            return {
                "score": 0.0,
                "passed": False,
                "rubric_id": rubric.get("id"),
                "error": f"shop unreachable: {exc}",
                "criteria": {},
            }
    elif needs_wp:
        return {
            "score": 0.0,
            "passed": False,
            "rubric_id": rubric.get("id"),
            "error": "no shop app in world (expected unistore or meridian)",
            "criteria": {},
        }

    for c in criteria:
        cid = c["id"]
        check = c.get("check") or {}
        ctype = check.get("type")
        fn = REGISTRY.get(ctype or "")
        if not fn:
            results[cid] = False
            per[cid] = {"error": f"unknown check type: {ctype}"}
            continue
        ok, detail = fn(ctx, check, c)
        results[cid] = ok
        per[cid] = detail

    if scoring == "weighted_sum":
        total_w = sum(float(c.get("weight") or 1) for c in criteria) or 1.0
        got = sum(
            float(c.get("weight") or 1) for c in criteria if results.get(c["id"])
        )
        score = got / total_w
        passed = score >= 1.0
    else:
        passed = all(results.values()) if results else False
        score = 1.0 if passed else 0.0

    return {
        "score": score,
        "passed": passed,
        "rubric_id": rubric.get("id"),
        "scoring": scoring,
        "criteria": results,
        "criterion_detail": per,
        "detail": ctx.detail,
        "registry": sorted(REGISTRY.keys()),
    }
