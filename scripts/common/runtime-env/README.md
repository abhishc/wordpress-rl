# runtime-env

Generate unique MySQL passwords, WordPress salts, and the Roundcube DES key **per world**.

Not checked in. Not shipped. Not eval credentials. First `make build` in an unpacked archive generates them.

`WORLD` / `--world` is required (no default).

```bash
WORLD=unistore-mail python3 scripts/common/runtime-env/ensure.py
# or: python3 scripts/common/runtime-env/ensure.py --world unistore-mail
# rewrite: --rotate   (then recreate DB volumes and restore)
# catalog parents only: --catalog
```
