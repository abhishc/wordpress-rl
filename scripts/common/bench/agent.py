#!/usr/bin/env python3
"""Playwright tool agent for one task trial (OpenAI-compatible or Anthropic).

Harness-side only. The model sees instruction.md + browser tools — never
baker admin / inject tokens.

Observations follow BrowserGym: accessibility tree with `bid` ids
(`browsergym-core`). Actions return short confirmations (us-cons / WebArena
style); call `snapshot` to re-observe. Optional Anthropic extended thinking
is off by default. Video + trace under artifact_dir.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Go to a URL. Returns a short confirmation — call snapshot next.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "snapshot",
            "description": (
                "BrowserGym accessibility tree of the current page with [bid] "
                "ids for click/fill. Prefer this after navigate/click/fill."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click an element by bid from the latest snapshot.",
            "parameters": {
                "type": "object",
                "properties": {"bid": {"type": "string"}},
                "required": ["bid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill",
            "description": "Clear and type into an input/textarea by bid.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bid": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["bid", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type into the focused element or by bid without clearing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "bid": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press",
            "description": "Press a key (Enter, Tab, Control+A, Escape, …).",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait milliseconds for UI to settle.",
            "parameters": {
                "type": "object",
                "properties": {"ms": {"type": "integer"}},
                "required": ["ms"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Finish the trial when the task is complete (or you give up).",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]


def openai_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    out: list[dict] = []
    for t in tools:
        fn = t["function"]
        out.append(
            {
                "name": fn["name"],
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters")
                or {"type": "object", "properties": {}},
            }
        )
    return out


ANTHROPIC_TOOLS = openai_tools_to_anthropic(TOOLS)

SYSTEM = """You are a web browser agent solving one evaluation task.
Use only the credentials and URLs in the task instruction.
Never invent admin, API, or database access.
Observations are BrowserGym accessibility trees: elements look like [bid] role 'name'.
Use bid values with click/fill. After navigate/click/fill, call snapshot before the next bid action — bids from older snapshots are invalid.
Prefer snapshot → act → snapshot. When the goal is done (or impossible), call done.
WordPress block editor: title/body live inside iframe name=editor-canvas; after opening post-new.php, dismiss modals, snapshot, click Add title, type title, click the default block appender, type body paragraphs, then Publish twice if needed.
"""

USER_PREFIX = (
    "Solve this task end-to-end in the browser.\n\n"
    "{instruction}\n\n"
    "Start with snapshot or navigate to the mail URL."
)

# Safety cap on a single tool payload (axtree). Actions return short strings.
MAX_TOOL_CHARS = 20_000

@dataclass
class AgentResult:
    done: bool
    reason: str
    steps: int
    error: str | None = None
    trace: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    thinking_log: list[dict] = field(default_factory=list)
    video_path: str | None = None
    playwright_trace_path: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    stop_reason: str = ""
    provider: str = ""


class BrowserTools:
    """BrowserGym-style surface: AXTree snapshot + short action results."""

    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str) -> str:
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(400)
        return f"opened {self.page.url}"

    def snapshot(self) -> str:
        from browsergym.core.observation import (
            _pre_extract,
            extract_dom_extra_properties,
            extract_dom_snapshot,
            extract_merged_axtree,
        )
        from browsergym.utils.obs import flatten_axtree_to_str

        page = self.page
        try:
            _pre_extract(page, tags_to_mark="standard_html", lenient=True)
            dom = extract_dom_snapshot(page)
            axtree = extract_merged_axtree(page)
            extra = extract_dom_extra_properties(dom, scale_factor=1.0)
            tree = flatten_axtree_to_str(
                axtree,
                extra_properties=extra,
                filter_visible_only=True,
                remove_redundant_static_text=True,
            )
        except Exception as exc:
            return f"error: snapshot failed: {type(exc).__name__}: {exc}"
        return f"url {page.url}\ntitle {page.title()}\n{tree}"

    def _elem(self, bid: str):
        from browsergym.core.action.utils import get_elem_by_bid

        return get_elem_by_bid(self.page, str(bid), scroll_into_view=True)

    def click(self, bid: str) -> str:
        try:
            elem = self._elem(bid)
            elem.click(timeout=15000)
            self.page.wait_for_timeout(400)
            return f"clicked {bid} now {self.page.url}"
        except Exception as exc:
            return f"error: click {bid}: {type(exc).__name__}: {exc}"

    def fill(self, bid: str, text: str) -> str:
        try:
            elem = self._elem(bid)
            elem.click(timeout=10000)
            elem.fill(text, timeout=10000)
            self.page.wait_for_timeout(200)
            return f"filled {bid}"
        except Exception as exc:
            return f"error: fill {bid}: {type(exc).__name__}: {exc}"

    def type_text(self, text: str, bid: str | None = None) -> str:
        try:
            if bid:
                elem = self._elem(bid)
                elem.click(timeout=10000)
            self.page.keyboard.type(text, delay=20)
            self.page.wait_for_timeout(200)
            return f"typed into {bid or 'focused'}"
        except Exception as exc:
            return f"error: type_text: {type(exc).__name__}: {exc}"

    def press(self, key: str) -> str:
        self.page.keyboard.press(key)
        self.page.wait_for_timeout(200)
        return f"pressed {key}"

    def wait(self, ms: int) -> str:
        self.page.wait_for_timeout(max(0, min(ms, 15000)))
        return f"waited {ms}ms"


def _truncate(out: str) -> str:
    if len(out) > MAX_TOOL_CHARS:
        return out[:MAX_TOOL_CHARS] + "\n…[truncated]"
    return out


def _compact_anthropic_history(
    messages: list[dict],
    *,
    keep_last_user_turns: int = 5,
    max_old_chars: int = 3_500,
) -> None:
    """Shrink old tool_result payloads in-place so long episodes stay under context.

    Keeps recent turns intact. Does not touch assistant thinking / tool_use
    blocks (required by the API when thinking was enabled).
    """
    user_idxs = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_idxs) <= keep_last_user_turns:
        return
    protected = set(user_idxs[-keep_last_user_turns:])
    for i in user_idxs:
        if i in protected:
            continue
        content = messages[i].get("content")
        if not isinstance(content, list):
            continue
        new_blocks: list[dict] = []
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_result"
                and isinstance(block.get("content"), str)
                and len(block["content"]) > max_old_chars
            ):
                trimmed = dict(block)
                trimmed["content"] = (
                    block["content"][:max_old_chars] + "\n…[older tool output compacted]"
                )
                new_blocks.append(trimmed)
            else:
                new_blocks.append(block)
        messages[i]["content"] = new_blocks


def _dispatch(tools: BrowserTools, name: str, args: dict) -> str:
    if name == "navigate":
        return tools.navigate(str(args["url"]))
    if name == "snapshot":
        return tools.snapshot()
    if name == "click":
        bid = args.get("bid") or args.get("ref")
        return tools.click(str(bid))
    if name == "fill":
        bid = args.get("bid") or args.get("ref")
        return tools.fill(str(bid), str(args["text"]))
    if name == "type_text":
        bid = args.get("bid") or args.get("ref")
        return tools.type_text(str(args["text"]), bid)
    if name == "press":
        return tools.press(str(args["key"]))
    if name == "wait":
        return tools.wait(int(args.get("ms") or 1000))
    return f"error: unknown tool {name}"


def _open_browser(
    *,
    headed: bool,
    artifact_dir: Path | None,
):
    """Returns (playwright, browser, context, page). Caller must close."""
    from browsergym.core.constants import BROWSERGYM_ID_ATTRIBUTE

    pw = sync_playwright().start()
    # BrowserGym locates elements via get_by_test_id → attribute `bid`
    pw.selectors.set_test_id_attribute(BROWSERGYM_ID_ATTRIBUTE)
    browser = pw.chromium.launch(headless=not headed)
    ctx_kwargs: dict[str, Any] = {"viewport": {"width": 1280, "height": 900}}
    if artifact_dir is not None:
        video_dir = artifact_dir / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        ctx_kwargs["record_video_dir"] = str(video_dir)
        ctx_kwargs["record_video_size"] = {"width": 1280, "height": 900}
    context = browser.new_context(**ctx_kwargs)
    if artifact_dir is not None:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    page.goto("about:blank")
    return pw, browser, context, page


def _close_browser(
    *,
    pw,
    browser,
    context,
    page,
    artifact_dir: Path | None,
) -> tuple[str | None, str | None]:
    video_path: str | None = None
    trace_path: str | None = None
    if artifact_dir is not None and context is not None:
        trace_file = artifact_dir / "playwright.trace.zip"
        try:
            context.tracing.stop(path=str(trace_file))
            trace_path = str(trace_file)
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass
        try:
            if page is not None and page.video is not None:
                src = Path(page.video.path())
                dst = artifact_dir / "session.webm"
                if src.exists():
                    shutil.move(str(src), str(dst))
                    video_path = str(dst)
        except Exception:
            pass
        # Popups / extra pages leave additional webms — keep largest as session
        # if primary rename missed, and leave others as session-N.webm.
        try:
            videos_dir = artifact_dir / "videos"
            if videos_dir.is_dir():
                leftovers = sorted(
                    videos_dir.glob("*.webm"),
                    key=lambda p: p.stat().st_size,
                    reverse=True,
                )
                for i, src in enumerate(leftovers):
                    if video_path is None and i == 0:
                        dst = artifact_dir / "session.webm"
                        shutil.move(str(src), str(dst))
                        video_path = str(dst)
                    else:
                        dst = artifact_dir / f"session-{i + 1}.webm"
                        shutil.move(str(src), str(dst))
        except Exception:
            pass
    else:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
    if browser is not None:
        try:
            browser.close()
        except Exception:
            pass
    if pw is not None:
        try:
            pw.stop()
        except Exception:
            pass
    return video_path, trace_path


def _persist_partial(
    artifact_dir: Path | None,
    *,
    messages: list[dict],
    trace: list[dict],
    thinking_log: list[dict],
    meta: dict,
) -> None:
    if artifact_dir is None:
        return
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "model.partial.json").write_text(
        json.dumps(
            {"messages": messages, "trace": trace, "thinking_log": thinking_log, **meta},
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    with (artifact_dir / "thinking.jsonl").open("w", encoding="utf-8") as fh:
        for entry in thinking_log:
            fh.write(json.dumps(entry, default=str) + "\n")
    (artifact_dir / "detailed-trace.json").write_text(
        json.dumps(trace, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def run_agent_openai(
    *,
    instruction: str,
    model: str,
    api_key: str,
    base_url: str | None,
    max_steps: int = 40,
    headed: bool = False,
    artifact_dir: Path | None = None,
) -> AgentResult:
    from openai import OpenAI

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER_PREFIX.format(instruction=instruction)},
    ]
    trace: list[dict] = []
    tool_steps = 0
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)

    pw = browser = context = page = None
    try:
        pw, browser, context, page = _open_browser(
            headed=headed, artifact_dir=artifact_dir
        )
        tools = BrowserTools(page)

        for round_i in range(1, max_steps + 1):
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
            msg = resp.choices[0].message
            asst: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            if msg.tool_calls:
                asst["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(asst)

            if not msg.tool_calls:
                video_path, trace_path = _close_browser(
                    pw=pw,
                    browser=browser,
                    context=context,
                    page=page,
                    artifact_dir=artifact_dir,
                )
                return AgentResult(
                    done=False,
                    reason=msg.content or "no tool calls",
                    steps=tool_steps,
                    error="model stopped without done()",
                    trace=trace,
                    messages=messages,
                    video_path=video_path,
                    playwright_trace_path=trace_path,
                    provider="openai",
                )

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_steps += 1
                if name == "done":
                    reason = str(args.get("reason") or "done")
                    entry = {
                        "step": tool_steps,
                        "round": round_i,
                        "tool": name,
                        "args": args,
                    }
                    trace.append(entry)
                    video_path, trace_path = _close_browser(
                        pw=pw,
                        browser=browser,
                        context=context,
                        page=page,
                        artifact_dir=artifact_dir,
                    )
                    return AgentResult(
                        done=True,
                        reason=reason,
                        steps=tool_steps,
                        trace=trace,
                        messages=messages,
                        video_path=video_path,
                        playwright_trace_path=trace_path,
                        provider="openai",
                    )
                try:
                    out = _dispatch(tools, name, args)
                except Exception as exc:
                    out = f"error: {type(exc).__name__}: {exc}"
                out = _truncate(out)
                entry = {
                    "step": tool_steps,
                    "round": round_i,
                    "tool": name,
                    "args": args,
                    "out": out,
                    "out_len": len(out),
                }
                trace.append(entry)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": out,
                    }
                )
                if tool_steps >= max_steps:
                    video_path, trace_path = _close_browser(
                        pw=pw,
                        browser=browser,
                        context=context,
                        page=page,
                        artifact_dir=artifact_dir,
                    )
                    return AgentResult(
                        done=False,
                        reason="max_steps",
                        steps=tool_steps,
                        error="hit max_steps",
                        trace=trace,
                        messages=messages,
                        video_path=video_path,
                        playwright_trace_path=trace_path,
                        provider="openai",
                    )

        video_path, trace_path = _close_browser(
            pw=pw,
            browser=browser,
            context=context,
            page=page,
            artifact_dir=artifact_dir,
        )
        return AgentResult(
            done=False,
            reason="max_steps",
            steps=tool_steps,
            error="hit max_steps",
            trace=trace,
            messages=messages,
            video_path=video_path,
            playwright_trace_path=trace_path,
            provider="openai",
        )
    except Exception:
        _close_browser(
            pw=pw,
            browser=browser,
            context=context,
            page=page,
            artifact_dir=artifact_dir,
        )
        raise


def run_agent_anthropic(
    *,
    instruction: str,
    model: str,
    api_key: str,
    max_steps: int = 40,
    headed: bool = False,
    artifact_dir: Path | None = None,
    thinking_budget: int = 0,
    max_tokens: int = 16384,
) -> AgentResult:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    messages: list[dict] = [
        {"role": "user", "content": USER_PREFIX.format(instruction=instruction)}
    ]
    trace: list[dict] = []
    thinking_log: list[dict] = []
    tool_steps = 0
    input_tokens = output_tokens = cache_write = cache_read = 0
    stop_reason = ""
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)

    use_thinking = thinking_budget > 0
    if use_thinking and max_tokens <= thinking_budget:
        max_tokens = thinking_budget + 4096

    pw = browser = context = page = None
    try:
        pw, browser, context, page = _open_browser(
            headed=headed, artifact_dir=artifact_dir
        )
        tools = BrowserTools(page)

        while tool_steps < max_steps:
            _compact_anthropic_history(messages)
            create_kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "system": SYSTEM,
                "tools": ANTHROPIC_TOOLS,
                "messages": messages,
                # us-cons: cache breakpoint walks forward as the episode grows
                "cache_control": {"type": "ephemeral"},
            }
            if use_thinking:
                create_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                }
            try:
                reply = client.messages.create(**create_kwargs)
            except anthropic.BadRequestError as exc:
                err = str(exc)
                if "cache_control" in err.lower() or "extra" in err.lower():
                    create_kwargs.pop("cache_control", None)
                    try:
                        reply = client.messages.create(**create_kwargs)
                    except anthropic.BadRequestError as exc2:
                        video_path, trace_path = _close_browser(
                            pw=pw,
                            browser=browser,
                            context=context,
                            page=page,
                            artifact_dir=artifact_dir,
                        )
                        _persist_partial(
                            artifact_dir,
                            messages=messages,
                            trace=trace,
                            thinking_log=thinking_log,
                            meta={
                                "error": str(exc2),
                                "steps": tool_steps,
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                            },
                        )
                        return AgentResult(
                            done=False,
                            reason="api_error",
                            steps=tool_steps,
                            error=str(exc2),
                            trace=trace,
                            messages=messages,
                            thinking_log=thinking_log,
                            video_path=video_path,
                            playwright_trace_path=trace_path,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cache_write_tokens=cache_write,
                            cache_read_tokens=cache_read,
                            stop_reason="api_error",
                            provider="anthropic",
                        )
                else:
                    video_path, trace_path = _close_browser(
                        pw=pw,
                        browser=browser,
                        context=context,
                        page=page,
                        artifact_dir=artifact_dir,
                    )
                    _persist_partial(
                        artifact_dir,
                        messages=messages,
                        trace=trace,
                        thinking_log=thinking_log,
                        meta={
                            "error": err,
                            "steps": tool_steps,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                        },
                    )
                    return AgentResult(
                        done=False,
                        reason="context_or_api_error",
                        steps=tool_steps,
                        error=err,
                        trace=trace,
                        messages=messages,
                        thinking_log=thinking_log,
                        video_path=video_path,
                        playwright_trace_path=trace_path,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cache_write_tokens=cache_write,
                        cache_read_tokens=cache_read,
                        stop_reason="api_error",
                        provider="anthropic",
                    )

            usage = reply.usage
            input_tokens += usage.input_tokens or 0
            output_tokens += usage.output_tokens or 0
            cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
            stop_reason = reply.stop_reason or ""

            content_blocks = [b.model_dump() for b in reply.content]
            assistant_message = {"role": "assistant", "content": content_blocks}
            messages.append(assistant_message)

            thoughts = [
                b.get("thinking") or ""
                for b in content_blocks
                if b.get("type") == "thinking"
            ]
            text_bits = [
                b.get("text") or ""
                for b in content_blocks
                if b.get("type") == "text"
            ]
            if thoughts or text_bits:
                thinking_log.append(
                    {
                        "step": tool_steps,
                        "thinking": "\n\n".join(t for t in thoughts if t),
                        "text": "\n\n".join(t for t in text_bits if t),
                    }
                )

            tool_uses = [b for b in reply.content if b.type == "tool_use"]
            print(
                f"  anthropic turn tools={len(tool_uses)} "
                f"steps={tool_steps}/{max_steps} "
                f"in={usage.input_tokens} out={usage.output_tokens}",
                flush=True,
            )
            if not tool_uses:
                video_path, trace_path = _close_browser(
                    pw=pw,
                    browser=browser,
                    context=context,
                    page=page,
                    artifact_dir=artifact_dir,
                )
                return AgentResult(
                    done=False,
                    reason="\n".join(text_bits) or "no tool calls",
                    steps=tool_steps,
                    error="model stopped without done()",
                    trace=trace,
                    messages=messages,
                    thinking_log=thinking_log,
                    video_path=video_path,
                    playwright_trace_path=trace_path,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_write_tokens=cache_write,
                    cache_read_tokens=cache_read,
                    stop_reason=stop_reason,
                    provider="anthropic",
                )

            result_blocks: list[dict] = []
            finished: AgentResult | None = None
            for block in tool_uses:
                name = block.name
                args = dict(block.input or {})
                tool_steps += 1
                print(f"  tool[{tool_steps}] {name} {args}", flush=True)
                if name == "done":
                    reason = str(args.get("reason") or "done")
                    trace.append(
                        {
                            "step": tool_steps,
                            "tool": name,
                            "args": args,
                        }
                    )
                    result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "acknowledged",
                        }
                    )
                    messages.append({"role": "user", "content": result_blocks})
                    video_path, trace_path = _close_browser(
                        pw=pw,
                        browser=browser,
                        context=context,
                        page=page,
                        artifact_dir=artifact_dir,
                    )
                    finished = AgentResult(
                        done=True,
                        reason=reason,
                        steps=tool_steps,
                        trace=trace,
                        messages=messages,
                        thinking_log=thinking_log,
                        video_path=video_path,
                        playwright_trace_path=trace_path,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cache_write_tokens=cache_write,
                        cache_read_tokens=cache_read,
                        stop_reason=stop_reason,
                        provider="anthropic",
                    )
                    break
                try:
                    out = _dispatch(tools, name, args)
                except Exception as exc:
                    out = f"error: {type(exc).__name__}: {exc}"
                out = _truncate(out)
                is_error = out.startswith("error:")
                trace.append(
                    {
                        "step": tool_steps,
                        "tool": name,
                        "args": args,
                        "out": out,
                        "out_len": len(out),
                        "is_error": is_error,
                    }
                )
                block_out: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": out,
                }
                if is_error:
                    block_out["is_error"] = True
                result_blocks.append(block_out)
                if tool_steps >= max_steps:
                    break

            if finished is not None:
                return finished

            remaining = max_steps - tool_steps
            result_blocks.append(
                {
                    "type": "text",
                    "text": f"{remaining} tool call(s) remaining out of {max_steps}.",
                }
            )
            messages.append({"role": "user", "content": result_blocks})
            _persist_partial(
                artifact_dir,
                messages=messages,
                trace=trace,
                thinking_log=thinking_log,
                meta={
                    "steps": tool_steps,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read": cache_read,
                    "cache_write": cache_write,
                },
            )

            if tool_steps >= max_steps:
                break

        video_path, trace_path = _close_browser(
            pw=pw,
            browser=browser,
            context=context,
            page=page,
            artifact_dir=artifact_dir,
        )
        return AgentResult(
            done=False,
            reason="max_steps",
            steps=tool_steps,
            error="hit max_steps",
            trace=trace,
            messages=messages,
            thinking_log=thinking_log,
            video_path=video_path,
            playwright_trace_path=trace_path,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_write_tokens=cache_write,
            cache_read_tokens=cache_read,
            stop_reason=stop_reason or "max_steps",
            provider="anthropic",
        )
    except Exception as exc:
        video_path, trace_path = _close_browser(
            pw=pw,
            browser=browser,
            context=context,
            page=page,
            artifact_dir=artifact_dir,
        )
        _persist_partial(
            artifact_dir,
            messages=messages,
            trace=trace,
            thinking_log=thinking_log,
            meta={"error": f"{type(exc).__name__}: {exc}", "steps": tool_steps},
        )
        if video_path or trace or messages:
            return AgentResult(
                done=False,
                reason="exception",
                steps=tool_steps,
                error=f"{type(exc).__name__}: {exc}",
                trace=trace,
                messages=messages,
                thinking_log=thinking_log,
                video_path=video_path,
                playwright_trace_path=trace_path,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_write_tokens=cache_write,
                cache_read_tokens=cache_read,
                stop_reason="exception",
                provider="anthropic",
            )
        raise


def run_agent(
    *,
    instruction: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
    max_steps: int = 40,
    headed: bool = False,
    provider: str = "openai",
    artifact_dir: Path | str | None = None,
    thinking_budget: int = 0,
) -> AgentResult:
    art = Path(artifact_dir) if artifact_dir else None
    if provider == "anthropic":
        return run_agent_anthropic(
            instruction=instruction,
            model=model,
            api_key=api_key,
            max_steps=max_steps,
            headed=headed,
            artifact_dir=art,
            thinking_budget=thinking_budget,
        )
    return run_agent_openai(
        instruction=instruction,
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_steps=max_steps,
        headed=headed,
        artifact_dir=art,
    )
