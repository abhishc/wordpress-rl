# bench

Run model trials on a world task: **apply → browser agent (API) → grade**.

Harness / operator tool. The eval model only receives `instruction.md` + browser tool results — not baker creds.

## Setup

Repo-root `.env` (gitignored):

```
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
# optional:
# OPENAI_BASE_URL=https://api.openai.com/v1
# BENCH_MODEL=gpt-4o
```

Requires: `openai` and/or `anthropic`, `playwright`, Chromium, **`browsergym-core`** (AXTree observations). Prefer project `.venv`.

```bash
.venv/bin/pip install browsergym-core openai anthropic playwright pyyaml
.venv/bin/playwright install chromium
```

Observations use BrowserGym accessibility trees (`[bid] role 'name'`). Actions return short confirmations; call `snapshot` to re-observe (lean, WebArena-style).

## Run

```bash
# one trial (OpenAI-compatible)
WORLD=<id> python3 scripts/common/bench/run_bench.py --task <slug> --trials 1

# Anthropic Opus + video + transcript (thinking off by default)
WORLD=unistore-mail .venv/bin/python scripts/common/bench/run_bench.py \
  --task stockout-substitute --model claude-opus-4-5 --max-steps 150 --trials 1
```

Results append to `worlds/<world>/tasks/<task>/solution/bench-results.jsonl` (local; do not ship secrets).

Per-trial artifacts: `.../solution/episodes/<utc>-<model>-tN/` — `model.json`, `thinking.jsonl` (if enabled), `detailed-trace.json`, `session.webm`, `playwright.trace.zip`, `result.json`.

## Fairness

Each trial resets and applies the task unless `--skip-apply` (debug only).

This reference agent launches a local Chromium on the host. It does **not** run inside `scripts/common/agent-sandbox/`. A green bench does not validate the isolation contract — use `agent-sandbox/run.sh` for that.
