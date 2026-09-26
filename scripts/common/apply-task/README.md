# apply-task

Reset every app in `worlds/<id>/world.yaml`, then apply overlays declared on those apps.

`WORLD` is required (no default).

## Run

```bash
WORLD=unistore-mail ./scripts/common/apply-task/apply_task.sh refund-or-replace
WORLD=meridian-mail ./scripts/common/apply-task/apply_task.sh publish-article
```

## Behavior

1. Validate `ports` in `world.yaml` against compose host bindings.
2. `make reset` for each `apps[].id`.
3. For each app with `overlay: eml`, POST `tasks/<slug>/overlay/*.eml` via `scripts/<app-role>/…` (`mail-inject` for mail).

Reads `app.yaml` + `app.secrets.yaml` through inject helpers.
