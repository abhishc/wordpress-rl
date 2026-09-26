# grade (shared)

Rubric grader with a **check-type registry**. Tasks ship `rubric.yaml`; they do not fork grader logic.

`--world` / `WORLD` and `--task` are required (no defaults).

## Run

```bash
WORLD=unistore-mail python3 scripts/common/grade/run_grade.py --task refund-or-replace
# meridian peer:
WORLD=meridian-mail python3 scripts/common/grade/run_grade.py --task publish-article
```

## Registry

| `check.type` | Meaning |
|---|---|
| `wp_post_title` | Post with exact title exists |
| `wp_post_status` | Post status matches |
| `wp_post_author_slug` | Author slug matches |
| `wp_post_body_contains` | Body contains verbatim text |
| `http_url_ok` | URL returns 2xx |
| `mail_ui_reachable` | Mail app `login.url` reachable |
| `mail_inject_health` | Mail app `{api}/health` reachable |
| `wc_order_status` | Woo order status equals `status` or is in `status_in` |
| `wc_order_note_contains` | Notes contain `text` (or `exact: true` for full-note match) |
| `wc_order_shipping_address1` | Shipping `address_1` exact match |
| `wc_order_line_skus` | Positive-qty line SKUs equal `skus` (sorted) |
| `wc_order_no_refunds` | Order has zero refunds |
| `wc_replacement_order` | Replacement matches customer_id/email/sku/qty/COD/exact note |

Add new types in `grade_rubric.py` `REGISTRY`. Prefer semantic outcomes + negatives over breadcrumbs.
