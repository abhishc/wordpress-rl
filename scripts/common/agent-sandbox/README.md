# agent-sandbox

The **eval agent** runs here — not on the host, and not with the repo mounted.

- Networks: world **edge** only (from `world.yaml` `compose_projects` → `<project>-edge`). Inject is on world + host-only `ops`, not edge.
- Files: `instruction.md` only. Host loopback inject port is not reachable from the container.
- URL rewrite: shop UI host port → `http://wordpress`, `mail_ui` → `http://roundcube` (ports from `world.yaml`).

```bash
# stacks must be up
WORLD=unistore-mail ./scripts/common/agent-sandbox/run.sh refund-or-replace
WORLD=meridian-mail ./scripts/common/agent-sandbox/run.sh publish-article
```

Optional overrides: `EDGE_NETS=net-a,net-b` or legacy `MER_NET` / `MAIL_NET`.

The current entrypoint probes the boundary (UIs reachable, inject blocked). Model tool-loops should use this same container contract.
