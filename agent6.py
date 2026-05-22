"""
agent6.py — The conductor.

Wires the four cognitive layers (perception, memory, decision, action) into
the agent loop:

  1. Load durable memory from disk.
  2. Run Perception ONCE to get a typed PerceptionOutput.
  3. Open a single MCP subprocess for the whole run.
  4. Loop:
       decide(state) → DecisionOutput
       execute(decision, mcp, store) → ActionResult
       record into scratchpad
       break on FINAL_ANSWER (exit 0)
       break on iteration cap (exit 1)
  5. Re-validate and print the final answer.

Usage:
    uv run python agent6.py "your query here"
    uv run python agent6.py "your query" --max-iters 8
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path

# Force UTF-8 on Windows so banner characters (═, ─) never crash cp1252 stdout.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from action import MCPClient, execute       # noqa: E402
from decision import decide                 # noqa: E402
from memory import load_memory              # noqa: E402
from perception import perceive             # noqa: E402
from schema import (                        # noqa: E402
    ANSWER_MODELS,
    ActionResult,
    AgentState,
    CallToolDecision,
    DecisionOutput,
    FinalAnswerDecision,
    ScratchpadEntry,
    WriteMemoryDecision,
)


DEFAULT_MAX_ITERS = 10

# How much of a tool result to keep in the scratchpad for the next Decision
# call. 6000 chars covers ~5 KB of page text per iteration — enough for the
# assignment queries. At 800 chars the LLM only saw nav garbage and had to
# hallucinate fields like min_python.
SCRATCHPAD_RESULT_CHARS = 6000

TRACE_RESULT_CHARS = 400


# ════════════════════════════════════════════════════════════════════════════
#  Rendering helpers
# ════════════════════════════════════════════════════════════════════════════

def _call_dedup_key(decision: DecisionOutput) -> str | None:
    """Return a dedup key for CALL_TOOL decisions; None for other actions.
    Uses only the semantically meaningful arg so that e.g. max_results
    differences don't prevent duplicate detection."""
    if not isinstance(decision, CallToolDecision):
        return None
    if decision.tool_name == "web_search":
        q = decision.tool_args.get("query", "").strip().lower()
        return f"web_search::{q}"
    if decision.tool_name == "fetch_url":
        u = decision.tool_args.get("url", "").strip()
        return f"fetch_url::{u}"
    return None


def _summarize_decision(decision: DecisionOutput) -> str:
    if isinstance(decision, CallToolDecision):
        args = json.dumps(decision.tool_args, sort_keys=True, default=str)
        return f"call {decision.tool_name}({args})"
    if isinstance(decision, WriteMemoryDecision):
        content = json.dumps(decision.record.content, sort_keys=True, default=str)
        return f"write memory id={decision.record.id} content={content}"
    if isinstance(decision, FinalAnswerDecision):
        return "produce final answer"
    return f"unknown({type(decision).__name__})"


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."


def _summarize_result(result: ActionResult, limit: int) -> str:
    if not result.success:
        return _truncate(f"ERROR: {result.error}", limit)
    if result.data is None:
        return "(no data)"
    try:
        payload = json.dumps(result.data, default=str)
    except (TypeError, ValueError):
        payload = str(result.data)
    return _truncate(payload, limit)


def _print_banner(text: str) -> None:
    bar = "═" * max(40, len(text))
    print(f"\n{bar}\n{text}\n{bar}")


def _print_iteration(
    iteration: int,
    decision: DecisionOutput,
    result: ActionResult,
) -> None:
    print(f"\n── Iteration {iteration} ───────────────────────────────────────────")
    print(f"  DECISION  : {decision.action}")
    print(f"  REASONING : {decision.reasoning}")
    print(f"  DETAILS   : {_summarize_decision(decision)}")
    print(f"  RESULT    : {'OK' if result.success else 'ERROR'}")
    print(f"  DATA      : {_summarize_result(result, TRACE_RESULT_CHARS)}")


# ════════════════════════════════════════════════════════════════════════════
#  The agent loop
# ════════════════════════════════════════════════════════════════════════════

async def run_agent(query: str, max_iters: int = DEFAULT_MAX_ITERS) -> int:
    """Run one full agent loop on `query`. Returns process exit code (0=success)."""

    _print_banner(f"AGENT6  ::  {query}")

    # Stamp the PoP capture file so each run is clearly separated.
    from datetime import datetime, timezone as _tz
    _pop_path = Path(__file__).parent / "state" / "pop_capture.md"
    _pop_path.parent.mkdir(parents=True, exist_ok=True)
    with _pop_path.open("a", encoding="utf-8") as _f:
        _f.write(
            f"\n\n{'#'*72}\n"
            f"# RUN — {datetime.now(_tz.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"# Query: {query}\n"
            f"{'#'*72}\n"
        )

    # 1. Load durable memory.
    store = load_memory()
    print(
        f"\n[memory]   loaded {len(store.facts)} fact(s), "
        f"{len(store.episodes)} episode(s) from state/memory.json"
    )

    # 2. Perception — runs exactly once.
    print("[perceive] running…")
    perception = perceive(query, store)
    print(f"[perceive] intent         : {perception.intent}")
    print(f"[perceive] query_type     : {perception.query_type}")
    print(f"[perceive] entities       : {perception.entities}")
    print(f"[perceive] answer_schema  : {perception.expected_answer_schema}")
    print(f"[perceive] memory_relevant: {perception.memory_relevant}")

    state = AgentState(
        perception=perception,
        scratchpad=[],
        memory_facts=list(store.facts),
        iteration=1,
        max_iters=max_iters,
    )

    # 3. + 4. Open MCP and run the loop.
    decide_failures = 0
    DECIDE_FAILURE_LIMIT = 3
    successful_calls: set[str] = set()  # dedup keys of already-succeeded CALL_TOOLs
    print("[mcp]      starting subprocess…", flush=True)
    async with MCPClient() as mcp:
        print("[mcp]      subprocess ready", flush=True)
        for i in range(1, max_iters + 1):
            state.iteration = i

            try:
                decision = decide(state)
                decide_failures = 0
            except Exception as e:
                decide_failures += 1
                msg = f"{type(e).__name__}: {e}"
                print(
                    f"\n── Iteration {i} ───────────────────────────────────────────\n"
                    f"  DECISION  : (decide() failed)\n"
                    f"  ERROR     : {msg}"
                )
                state.scratchpad.append(
                    ScratchpadEntry(
                        iteration=i,
                        decision_action="CALL_TOOL",
                        decision_summary=f"decide() validation failed: {msg}",
                        result_success=False,
                        result_excerpt=_truncate(msg, SCRATCHPAD_RESULT_CHARS),
                    )
                )
                if decide_failures >= DECIDE_FAILURE_LIMIT:
                    print(
                        f"\n[loop]     {DECIDE_FAILURE_LIMIT} consecutive "
                        "decide() failures — giving up."
                    )
                    return 1
                continue

            # Dedup guard: block repeated identical CALL_TOOL calls.
            dup_key = _call_dedup_key(decision)
            if dup_key and dup_key in successful_calls:
                tool_name = decision.tool_name if isinstance(decision, CallToolDecision) else "?"
                key_arg = "query" if tool_name == "web_search" else "url"
                # Next unvisited URL hint for synthesis loops
                if tool_name == "web_search":
                    next_hint = (
                        "Call fetch_url on the next unvisited URL from the "
                        "web_search results already in the scratchpad."
                    )
                else:
                    next_hint = (
                        "If the scratchpad contains enough data to fill every "
                        "field in the answer schema, emit FINAL_ANSWER now. "
                        "Otherwise call fetch_url on a different unvisited URL."
                    )
                block_msg = (
                    f"DUPLICATE BLOCKED: '{tool_name}' with this {key_arg} already "
                    f"succeeded — do not repeat it. {next_hint}"
                )
                print(
                    f"[execute]  → BLOCKED DUPLICATE :: {_summarize_decision(decision)[:120]}",
                    flush=True,
                )
                result = ActionResult(
                    action_type="CALL_TOOL",
                    success=False,
                    error=block_msg,
                )
                print("[execute]  ← BLOCKED", flush=True)
            else:
                print(
                    f"[execute]  → {decision.action} :: {_summarize_decision(decision)[:160]}",
                    flush=True,
                )
                result = await execute(decision, mcp=mcp, store=store)
                print(f"[execute]  ← {'OK' if result.success else 'ERROR'}", flush=True)
                if result.success and dup_key:
                    successful_calls.add(dup_key)

            _print_iteration(i, decision, result)

            state.scratchpad.append(
                ScratchpadEntry(
                    iteration=i,
                    decision_action=decision.action,
                    decision_summary=_summarize_decision(decision),
                    result_success=result.success,
                    result_excerpt=_summarize_result(result, SCRATCHPAD_RESULT_CHARS),
                )
            )

            # Reflect a successful WRITE_MEMORY back into the visible facts so
            # the next Decision iteration sees the freshly stored fact.
            if isinstance(decision, WriteMemoryDecision) and result.success:
                state.memory_facts = list(store.facts)

            # 5. Termination — FINAL_ANSWER, validate and print.
            if isinstance(decision, FinalAnswerDecision) and result.success:
                expected_cls = ANSWER_MODELS[perception.expected_answer_schema]
                typed = expected_cls.model_validate(decision.answer)
                _print_banner(f"FINAL ANSWER (validated as {expected_cls.__name__})")
                print(typed.model_dump_json(indent=2))
                print(f"\nConverged in {i} iteration(s).")
                return 0

        print(f"\n[loop]     Iteration cap ({max_iters}) reached without FINAL_ANSWER.")
        return 1


# ════════════════════════════════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Session 6 cognitive agent — four roles over MCP."
    )
    parser.add_argument("query", help="The user query to answer.")
    parser.add_argument(
        "--max-iters",
        type=int,
        default=DEFAULT_MAX_ITERS,
        help=f"Iteration cap (default {DEFAULT_MAX_ITERS}).",
    )
    args = parser.parse_args()
    return asyncio.run(run_agent(args.query, args.max_iters))


if __name__ == "__main__":
    sys.exit(main())
