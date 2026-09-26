# UniStore WooCommerce plant

Baker-only. Reads reviewable JSON under `worlds/unistore-mail/populate/` and creates staff, categories, products, customers, coupons, and orders via WP/Woo REST.

```bash
python3 scripts/unistore/wc-plant/wc_plant.py \
  --app-yaml worlds/unistore-mail/apps/unistore/app.yaml \
  --fixtures worlds/unistore-mail/populate
```

Idempotent for products/customers/coupons/staff (match by sku/email/username). Orders skip if any order already has `_unistore_fixture_index` meta.

After create, order dates are applied with WooCommerce `WC_Order` setters (`--backdate-only` to fix an existing dump). WC REST ignores `date_created_gmt` on write.

Then analytics (`wp_wc_order_stats`) is synced so Customers order counts are non-zero.
