#!/usr/bin/env python3
"""Benchmark a model on a world task: apply → agent → grade (N trials).

Loads API keys from repo-root .env (OPENAI_API_KEY / ANTHROPIC_API_KEY).
Harness-side only — never expose baker secrets to the model.

Anthropic episodes (us-cons-style) write under:
  worlds/<world>/tasks/<task>/solution/episodes/<utc>/
    model.json          full messages (incl. thinking blocks)
    thinking.jsonl      extracted thought text per model turn
    detailed-trace.json tool attempts with full outputs
    session.webm        Playwright video
    playwright.trace.zip
    result.json         score + summary
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from agent import run_agent  # noqa: E402
from require_world import require_world  # noqa: E402


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'").strip('"')
        if k and k not in os.environ:
            os.environ[k] = v


def run_apply(task: str, world: str) -> None:
    script = ROOT / "scripts" / "common" / "apply-task" / "apply_task.sh"
    env = {**os.environ, "WORLD": world}
    subprocess.run([str(script), task], check=True, cwd=str(ROOT), env=env)


def run_grade(task: str, world: str) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "common" / "grade" / "run_grade.py"),
            "--world",
            world,
            "--task",
            task,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        data = {
            "score": 0.0,
            "passed": False,
            "error": "bad grade stdout",
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }
    data["exit_code"] = proc.returncode
    return data


def infer_provider(model: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    m = model.lower()
    if m.startswith("claude") or "anthropic" in m:
        return "anthropic"
    return "openai"


def resolve_api_key(provider: str, cli_key: str) -> str:
    if cli_key:
        return cli_key
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY", "")
    return os.environ.get("OPENAI_API_KEY", "")


def write_episode_artifacts(episode_dir: Path, agent, *, model: str, grade: dict, row: dict) -> None:
    episode_dir.mkdir(parents=True, exist_ok=True)
    model_body = {
        "model": model,
        "provider": agent.provider,
        "stop_reason": agent.stop_reason,
        "done": agent.done,
        "reason": agent.reason,
        "steps": agent.steps,
        "error": agent.error,
        "tokens": {
            "input": agent.input_tokens,
            "output": agent.output_tokens,
            "cache_write": agent.cache_write_tokens,
            "cache_read": agent.cache_read_tokens,
        },
        "grade": grade,
        "messages": agent.messages,
        "video_path": agent.video_path,
        "playwright_trace_path": agent.playwright_trace_path,
    }
    (episode_dir / "model.json").write_text(
        json.dumps(model_body, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    with (episode_dir / "thinking.jsonl").open("w", encoding="utf-8") as fh:
        for entry in agent.thinking_log:
            fh.write(json.dumps(entry, default=str) + "\n")
    (episode_dir / "detailed-trace.json").write_text(
        json.dumps(agent.trace, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    (episode_dir / "result.json").write_text(
        json.dumps(row, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    load_dotenv(ROOT / ".env")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", required=True)
    ap.add_argument(
        "--world",
        default=None,
        help="World id (or set WORLD). Required — no default.",
    )
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--model", default=os.environ.get("BENCH_MODEL", "gpt-4o"))
    ap.add_argument(
        "--provider",
        choices=["openai", "anthropic"],
        default=None,
        help="Defaults from model name (claude* → anthropic).",
    )
    ap.add_argument(
        "--api-key",
        default="",
        help="Defaults to OPENAI_API_KEY or ANTHROPIC_API_KEY from env/.env",
    )
    ap.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL") or None,
        help="Optional OpenAI-compatible base URL",
    )
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument(
        "--thinking-budget",
        type=int,
        default=0,
        help="Anthropic extended-thinking budget_tokens (default 0 = disabled).",
    )
    ap.add_argument("--headed", action="store_true")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSONL results path (default: worlds/<world>/tasks/<task>/solution/bench-results.jsonl)",
    )
    ap.add_argument(
        "--episodes-dir",
        type=Path,
        default=None,
        help="Directory for per-trial artifacts (default: .../solution/episodes)",
    )
    ap.add_argument(
        "--skip-apply",
        action="store_true",
        help="Do not reset/apply (debug only; not a fair trial)",
    )
    args = ap.parse_args()
    args.world = require_world(args.world, root=ROOT)
    provider = infer_provider(args.model, args.provider)
    api_key = resolve_api_key(provider, args.api_key)

    if not api_key:
        need = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        print(f"missing API key: set {need} in .env or pass --api-key", file=sys.stderr)
        sys.exit(2)

    task_dir = ROOT / "worlds" / args.world / "tasks" / args.task
    instruction_path = task_dir / "instruction.md"
    if not instruction_path.is_file():
        print(f"missing {instruction_path}", file=sys.stderr)
        sys.exit(2)
    instruction = instruction_path.read_text(encoding="utf-8")

    out_path = args.out or (task_dir / "solution" / "bench-results.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    episodes_root = args.episodes_dir or (task_dir / "solution" / "episodes")

    scores: list[float] = []
    print(
        f"bench world={args.world} task={args.task} provider={provider} "
        f"model={args.model} trials={args.trials} max_steps={args.max_steps}",
        flush=True,
    )

    for i in range(1, args.trials + 1):
        print(f"\n== trial {i}/{args.trials}", flush=True)
        t0 = time.time()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        episode_dir = episodes_root / f"{stamp}-{args.model.replace('/', '_')}-t{i}"
        episode_dir.mkdir(parents=True, exist_ok=True)
        print(f"episode_dir={episode_dir}", flush=True)

        if not args.skip_apply:
            run_apply(args.task, args.world)
        agent = run_agent(
            instruction=instruction,
            model=args.model,
            api_key=api_key,
            base_url=args.base_url,
            max_steps=args.max_steps,
            headed=args.headed,
            provider=provider,
            artifact_dir=episode_dir,
            thinking_budget=args.thinking_budget if provider == "anthropic" else 0,
        )
        grade = run_grade(args.task, args.world)
        score = float(grade.get("score") or 0.0)
        scores.append(score)
        row = {
            "trial": i,
            "world": args.world,
            "task": args.task,
            "model": args.model,
            "provider": provider,
            "score": score,
            "passed": bool(grade.get("passed")),
            "grade": grade,
            "agent": {
                "done": agent.done,
                "reason": agent.reason,
                "steps": agent.steps,
                "error": agent.error,
                "stop_reason": agent.stop_reason,
                "tokens": {
                    "input": agent.input_tokens,
                    "output": agent.output_tokens,
                    "cache_write": agent.cache_write_tokens,
                    "cache_read": agent.cache_read_tokens,
                },
                "video_path": agent.video_path,
                "playwright_trace_path": agent.playwright_trace_path,
                "episode_dir": str(episode_dir),
                "trace_summary": [
                    {
                        "step": t.get("step"),
                        "tool": t.get("tool"),
                        "args": t.get("args"),
                        "out_len": t.get("out_len"),
                        "is_error": t.get("is_error"),
                    }
                    for t in agent.trace
                ],
            },
            "elapsed_sec": round(time.time() - t0, 2),
        }
        write_episode_artifacts(episode_dir, agent, model=args.model, grade=grade, row=row)
        with out_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        print(
            json.dumps(
                {
                    "trial": i,
                    "score": score,
                    "passed": row["passed"],
                    "agent_steps": agent.steps,
                    "agent_error": agent.error,
                    "agent_done": agent.done,
                    "thinking_turns": len(agent.thinking_log),
                    "video": agent.video_path,
                    "episode_dir": str(episode_dir),
                    "elapsed_sec": row["elapsed_sec"],
                }
            ),
            flush=True,
        )

    mean = sum(scores) / len(scores) if scores else 0.0
    summary = {
        "task": args.task,
        "model": args.model,
        "provider": provider,
        "trials": len(scores),
        "mean_score": mean,
        "scores": scores,
        "results": str(out_path),
        "episodes": str(episodes_root),
    }
    print("\n== summary", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    sys.exit(0 if mean > 0 else 1)


if __name__ == "__main__":
    main()
