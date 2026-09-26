# mail-inject

Plant one message into Roundcube by POSTing a raw `.eml` to the mail inject API.

Baker-only. Eval must never see the inject token.

## Run

```bash
python3 scripts/mail/mail-inject/mail_inject.py \
  --app-yaml worlds/meridian-mail/apps/mail/app.yaml \
  --eml worlds/meridian-mail/tasks/publish-article/overlay/01-publish-brief.eml
```

## Inputs / outputs

| | |
|---|---|
| Input | `--app-yaml` (`api`, `admin.token`) |
| Input | `--eml` raw RFC822; `To:` should match `login.username`@domain |
| Output | HTTP status line on stdout |
| Side effect | `POST {api}/send` with `Authorization: Bearer <token>` |

## `app.yaml` fields

- `api` — inject base URL (world: `:19082`)
- `admin.token` — bearer token
- `login.username` — usually the message `To:` local-part
