# UniStore

WordPress + WooCommerce shop. [http://127.0.0.1:19180/](http://127.0.0.1:19180/)

Storefront theme. Shop, Cart, Checkout, My account. Cash on delivery. Empty catalog.

Handbook (WP REST + Woo v3): [http://127.0.0.1:19180/handbook/](http://127.0.0.1:19180/handbook/). Live roots: [http://127.0.0.1:19180/wp-json/](http://127.0.0.1:19180/wp-json/) and [http://127.0.0.1:19180/wp-json/wc/v3/](http://127.0.0.1:19180/wp-json/wc/v3/).

## `app.yaml` / `app.secrets.yaml`

| Field | File | Meaning |
|---|---|---|
| `api` / `wc_api` | app.yaml | Handbook + Woo REST roots |
| `login.url` | app.yaml | Public wp-admin URL |
| `admin.username` / `password` | app.secrets.yaml | Baker UI + REST login (in dump) |
| `admin.application_password` | app.secrets.yaml | Baker REST Application Password |

## Logins — reuse vs create

| Kind | Where | When |
|---|---|---|
| **Baker admin** (`bakeadmin`) | Dump + `app.secrets.yaml` | **Always reuse.** Never recreate. Never put in eval `instruction.md`. |
| **Task / scenery users** | Not in base dump | **Create via WP REST** when a bake/overlay needs them. Do not bake into the base dump unless scenery permanently needs the account. |

Base dump is **admin only**, zero products. WooCommerce, Storefront, and COD are in the snapshot.

```bash
make build      # pull, up, restore snapshots/
make snapshot
make reset
make down
```
