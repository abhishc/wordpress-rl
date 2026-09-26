# Mail

Roundcube webmail. [http://127.0.0.1:19181/](http://127.0.0.1:19181/)

Domain: `mail.example` (see `app.yaml` `domain`).

## `app.yaml` / `app.secrets.yaml`

| Field | File | Meaning |
|---|---|---|
| `api` | app.yaml | Inject API base (`:19182`) |
| `login.*` | app.yaml | Default agent mailbox (eval may use via instruction) |
| `admin.token` | app.secrets.yaml | Bearer for inject API (ops only) |

On first `make build`, `scripts/common/runtime-env/ensure.py` creates `app.secrets.yaml` with a random inject token if the file is missing (lab unpack path).

## Logins — reuse vs create

| Kind | Where | When |
|---|---|---|
| **Default mailbox** (`login`) | Dump + `app.yaml` `login` | **Reuse** for Roundcube UI and as `To:` when injecting mail. |
| **Inject API** | `app.secrets.yaml` `admin.token` | **Always reuse** once generated. Host-only. Never give to eval. |
| **Extra mailboxes** | Not in base dump | **Create** only when a bake/overlay needs another inbox. |

There is no ops inbox. Baker plants mail via the inject API; `From:` can be anyone and does not get a login.

## Seed (baker)

```
POST http://127.0.0.1:19182/send
Authorization: Bearer <app.secrets.yaml admin.token>
Content-Type: message/rfc822
```

Body is a raw `.eml`. `To:` is normally `login` in `app.yaml`.

```bash
make build
make snapshot
make reset
make down
```
