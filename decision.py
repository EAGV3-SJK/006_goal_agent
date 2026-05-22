"""
decision.py — The Decision layer.

On every iteration of the agent loop, picks EXACTLY ONE of three actions:

  CALL_TOOL     — invoke an MCP tool (web_search, fetch_url, get_time).
  WRITE_MEMORY  — persist a durable fact in the notebook.
  FINAL_ANSWER  — produce the answer matching the expected schema; loop exits.

The prompt includes the Perception summary, durable facts, scratchpad of past
iterations, the JSON Schema of the expected final-answer model, and the
available MCP tool signatures.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, create_model

from llm_gateway.client import LLM

_POP_PATH = Path(__file__).parent / "state" / "pop_capture.md"


def _pop_append(text: str) -> None:
    _POP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _POP_PATH.open("a", encoding="utf-8") as f:
        f.write(text)
from schema import (
    ANSWER_MODELS,
    AgentState,
    CallToolDecision,
    DecisionOutput,
    FinalAnswerDecision,
    MemoryRecord,
    RawDecision,
    ScratchpadEntry,
    WriteMemoryDecision,
)


def _build_per_query_raw_decision(answer_model: type[BaseModel]) -> type[BaseModel]:
    """Construct a RawDecision-style model with `answer` typed as the specific
    per-query final-answer model. This makes the LLM emit populated answer
    fields instead of answer: {} — the schema now shows exactly which fields
    the final answer must contain."""
    import typing
    return create_model(  # type: ignore[call-overload]
        f"RawDecision_{answer_model.__name__}",
        __base__=BaseModel,
        action=(
            typing.Literal["CALL_TOOL", "WRITE_MEMORY", "FINAL_ANSWER"],
            Field(..., description="Which branch this decision is."),
        ),
        reasoning=(str, Field(..., description="One short sentence — why this action.")),
        tool_name=(str | None, Field(default=None, description="Required when action=CALL_TOOL.")),
        tool_args=(
            dict | None,
            Field(
                default=None,
                description=(
                    "Required when action=CALL_TOOL. "
                    "For web_search: {\"query\": str}. "
                    "For fetch_url: {\"url\": str}. "
                    "For get_time: {\"timezone\": str}."
                ),
            ),
        ),
        record=(MemoryRecord | None, Field(default=None, description="Required when action=WRITE_MEMORY.")),
        answer=(
            answer_model | None,
            Field(
                default=None,
                description=f"Required when action=FINAL_ANSWER. Must conform to {answer_model.__name__}.",
            ),
        ),
    )


# ════════════════════════════════════════════════════════════════════════════
#  Static prompt fragments
# ════════════════════════════════════════════════════════════════════════════

TOOL_CATALOG = """\
web_search
    tool_name : "web_search"
    tool_args : {"query": "<your search terms>", "max_results": 5}
    returns   : list of {title, url, snippet}.
    use when  : you need URLs of authoritative pages (Wikipedia, official docs,
                weather services, activity listings).

fetch_url
    tool_name : "fetch_url"
    tool_args : {"url": "<https://...>"}
    returns   : dict with {status, text}.
    use when  : you already have a URL (from a previous web_search or a
                well-known canonical path) and want its full content as markdown.

get_time
    tool_name : "get_time"
    tool_args : {"timezone": "<IANA name, e.g. Asia/Tokyo>"}
    returns   : dict with current ISO time, human time, UTC offset.
    use when  : the query explicitly asks about current time or date.

‼ tool_args MUST NEVER BE EMPTY for a CALL_TOOL action. If you are calling
  web_search, `query` is REQUIRED. If you are calling fetch_url, `url` is
  REQUIRED. Emitting tool_args: {{}} will fail validation and waste an iteration.
"""


DECISION_SYSTEM_PROMPT = """\
You are the DECISION layer of a four-role cognitive agent. On every iteration
you choose EXACTLY ONE of three actions:

  1. CALL_TOOL     — fetch fresh information from an MCP tool.
  2. WRITE_MEMORY  — persist a durable fact in the agent's notebook.
  3. FINAL_ANSWER  — produce the final answer; the agent loop then exits.

You MUST return JSON conforming to the schema below. Pick the `action` value
first, then fill ONLY the fields required by that action:

  • action="CALL_TOOL"     → fill `tool_name` and `tool_args`.
  • action="WRITE_MEMORY"  → fill `record` (id + kind="fact" + content).
  • action="FINAL_ANSWER"  → fill `answer` (must match the expected schema shown below).

`reasoning` is required for every action — ONE SHORT SENTENCE (under 25 words)
explaining why you picked this action. Leave the unused fields out (or null).

# Available tools
{tool_catalog}

# Heuristics — read these before the context below
- A typical multi-hop query goes: web_search → fetch_url → FINAL_ANSWER.
- For a direct URL in the query (e.g. a Wikipedia URL), call fetch_url FIRST
  without searching — skip web_search entirely.
- Do NOT keep calling tools after you have enough information. The agent loop
  has an iteration cap; wasted calls fail the task.
- For `memory_write` queries, your VERY FIRST iteration MUST be WRITE_MEMORY.
  Do not search for anything — the user has told you the fact directly.
  Pick a stable `record.id` such as "moms_birthday" so re-runs overwrite cleanly.
- For `memory_recall` queries, the stored facts are already in your prompt.
  Use them; do not search for facts the user has already given you.
- Never invent URLs. Use only URLs that appear verbatim in previous web_search
  results, or canonical well-known URLs (Wikipedia, pypi.org, etc.).
- Prefer authoritative sources: Wikipedia for biography, official docs for
  libraries, NVD/GitHub Security Advisories for CVEs.
- SYNTHESIS WORKFLOW — when query_type="synthesis":
    Step 1  Call web_search ONCE. You now have a list of URLs.
    Step 2  Call fetch_url on each URL from Step 1, ONE per iteration.
            Count successful fetch_url entries in the scratchpad. If
            pages_read requires ≥3 entries and you have fewer than 3
            successful fetch_url calls, pick the next unvisited URL from
            Step 1's results and call fetch_url on it NOW.
            DO NOT call web_search again — you already have the URLs.
    Step 3  After ≥3 successful fetch_url calls, emit FINAL_ANSWER.
- DUPLICATE-CALL GUARD — BEFORE choosing CALL_TOOL, read the scratchpad.
  If a ⚠ DUPLICATE warning appears for a call, or if an identical
  tool + args already has an "OK" entry, DO NOT repeat that call.
  Choose fetch_url on an unvisited URL, or FINAL_ANSWER instead.
- READ THE SCRATCHPAD. If a previous iteration shows your CALL_TOOL failed
  (ERR), look at the error and FIX what you missed — empty tool_args is the
  most common bug; fill in `query` or `url`.
- GROUNDING: Every field in your FINAL_ANSWER.answer (dates, names, URLs, lists)
  MUST appear verbatim somewhere in a prior iteration's `result:` excerpt in the
  scratchpad. If a value you need is NOT visible in the scratchpad, CALL_TOOL to
  fetch it — do not fill it from background knowledge.
- For `memory_recall` queries: the stored fact should be in the stored facts
  block above. Use it directly — no tool calls needed.
- CITE / PROVE verbs are strong signals: if the user query contains "cite",
  "prove", "show", or "documentation that says", you MUST fetch_url the
  supporting page before FINAL_ANSWER.

# Expected final-answer schema for this run
The FINAL_ANSWER's `answer` field MUST match this Pydantic model.
Name:   {expected_answer_schema}
Schema:
{answer_schema_json}

# Stored facts (durable notebook)
{facts}

# Perception summary
intent:       {intent}
query_type:   {query_type}
entities:     {entities}

# Loop budget
You are on iteration {iteration} of {max_iters}. The cap is the hard end of
the agent loop — beyond it the run fails with no answer.

Commit rule: if the scratchpad already contains enough grounded data to fill
EVERY field of the answer schema above, emit FINAL_ANSWER NOW. Do not keep
searching for nicer sources or extra confirmation.

Near-cap rule: if iteration >= {max_iters} - 1 and any field is still missing,
emit FINAL_ANSWER anyway with your best inference from the scratchpad and flag
the uncertainty in `reasoning`. A partial answer beats a timeout.

# Scratchpad — what you tried this run (oldest first)
{scratchpad}
"""


# ════════════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════════════

def _facts_block(facts: list[MemoryRecord]) -> str:
    if not facts:
        return "(none)"
    return "\n".join(
        f"- {f.id}: {json.dumps(f.content, sort_keys=True)}" for f in facts
    )


def _scratchpad_dedup_key(summary: str) -> str:
    """Normalize a decision_summary to a dedup key.
    Strips varying args (max_results) so same-query searches are recognised."""
    import re
    m = re.search(r'call web_search\(.*?"query":\s*"([^"]+)"', summary)
    if m:
        return f"web_search::{m.group(1).strip().lower()}"
    m = re.search(r'call fetch_url\(.*?"url":\s*"([^"]+)"', summary)
    if m:
        return f"fetch_url::{m.group(1).strip()}"
    return summary


def _render_scratchpad(scratchpad: list[ScratchpadEntry]) -> str:
    if not scratchpad:
        return "(empty — this is iteration 1)"
    lines: list[str] = []
    seen_ok: dict[str, int] = {}  # dedup_key -> first iteration that succeeded

    for s in scratchpad:
        status = "OK " if s.result_success else "ERR"
        lines.append(
            f"[{s.iteration}] {s.decision_action} {status} :: {s.decision_summary}"
        )
        if s.result_excerpt:
            lines.append(f"       result: {s.result_excerpt}")

        if s.decision_action == "CALL_TOOL" and s.result_success:
            key = _scratchpad_dedup_key(s.decision_summary)
            if key in seen_ok:
                lines.append(
                    f"  ⚠ DUPLICATE — identical to iteration {seen_ok[key]}. "
                    f"DO NOT call this tool with these args again."
                )
            else:
                seen_ok[key] = s.iteration

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
#  Public API
# ════════════════════════════════════════════════════════════════════════════

def decide(
    state: AgentState,
    *,
    llm: LLM | None = None,
) -> DecisionOutput:
    """Run one Decision LLM call. Returns one of:
        CallToolDecision | WriteMemoryDecision | FinalAnswerDecision.

    If the LLM picks FINAL_ANSWER, the answer dict is re-validated against
    the per-query Pydantic model selected by Perception. A validation failure
    raises ValueError so the agent loop records it and retries."""
    client = llm or LLM()

    expected_name = state.perception.expected_answer_schema
    expected_model = ANSWER_MODELS[expected_name]

    system_text = DECISION_SYSTEM_PROMPT.format(
        tool_catalog=TOOL_CATALOG,
        expected_answer_schema=expected_name,
        answer_schema_json=json.dumps(expected_model.model_json_schema(), indent=2),
        facts=_facts_block(state.memory_facts),
        intent=state.perception.intent,
        query_type=state.perception.query_type,
        entities=", ".join(state.perception.entities) or "(none)",
        iteration=state.iteration,
        max_iters=state.max_iters,
        scratchpad=_render_scratchpad(state.scratchpad),
    )

    # Build a per-query RawDecision so the `answer` field is fully typed.
    PerQueryRawDecision = _build_per_query_raw_decision(expected_model)

    response_format = {
        "type": "json_schema",
        "schema": PerQueryRawDecision.model_json_schema(),
        "name": PerQueryRawDecision.__name__,
        "strict": False,
    }
    print(f"[decide]   → gateway /v1/chat (system={len(system_text)} chars)", flush=True)
    try:
        resp = client.chat(
            prompt=state.perception.user_query,
            system=system_text,
            response_format=response_format,
            auto_route="decision",
            temperature=1.0,    # higher temp → more exploratory
            max_tokens=3000,    # headroom so the model doesn't truncate
        )
        print("[decide]   ← gateway returned", flush=True)
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.text[:2000]
        except Exception:
            detail = "(no body)"
        raise RuntimeError(
            f"Gateway {e.response.status_code} on /v1/chat:\n{detail}"
        ) from e

    parsed: Any = resp.get("parsed")
    if parsed is None:
        raw_obj = PerQueryRawDecision.model_validate_json(resp["text"])
    else:
        raw_obj = PerQueryRawDecision.model_validate(parsed)

    # Convert the per-query model's `answer` to a plain dict for the pipeline.
    answer_dict: dict[str, Any] | None
    if raw_obj.answer is None:
        answer_dict = None
    elif hasattr(raw_obj.answer, "model_dump"):
        answer_dict = raw_obj.answer.model_dump()
    else:
        answer_dict = dict(raw_obj.answer)

    raw = RawDecision(
        action=raw_obj.action,
        reasoning=raw_obj.reasoning,
        tool_name=raw_obj.tool_name,
        tool_args=raw_obj.tool_args,
        record=raw_obj.record,
        answer=answer_dict,
    )

    decision = _to_typed_decision(raw)

    if isinstance(decision, FinalAnswerDecision):
        try:
            validated_answer = expected_model.model_validate(decision.answer)
        except Exception as e:
            raise ValueError(
                f"FINAL_ANSWER.answer failed validation against {expected_name}: {e}"
            ) from e
    else:
        validated_answer = None

    # PoP capture: always write iteration 1; always write FINAL_ANSWER.
    if state.iteration == 1 or isinstance(decision, FinalAnswerDecision):
        raw_json = resp.get("text") or json.dumps(
            raw_obj.model_dump(exclude_none=True), indent=2
        )
        validated_block = (
            f"```json\n{validated_answer.model_dump_json(indent=2)}\n```"
            if validated_answer is not None
            else f"*(not a FINAL_ANSWER — action is {decision.action})*"
        )
        _pop_append(
            f"\n\n{'─'*72}\n"
            f"## DECISION — Iteration {state.iteration} of {state.max_iters}"
            f" — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"{'─'*72}\n\n"
            f"### System Prompt (rendered)\n\n"
            f"```\n{system_text}\n```\n\n"
            f"### Per-Query JSON Schema sent to LLM ({PerQueryRawDecision.__name__})\n\n"
            f"```json\n{json.dumps(PerQueryRawDecision.model_json_schema(), indent=2)}\n```\n\n"
            f"### Raw LLM Response\n\n"
            f"```json\n{raw_json}\n```\n\n"
            f"### Validated Decision (`{decision.action}`)\n\n"
            f"```json\n{json.dumps(raw.model_dump(exclude_none=True), indent=2)}\n```\n\n"
            f"### Final-Answer Validation ({expected_name})\n\n"
            f"{validated_block}\n"
        )

    return decision


_ARGS_TO_TOOL: dict[str, str] = {
    "url":      "fetch_url",
    "query":    "web_search",
    "timezone": "get_time",
}


def _to_typed_decision(raw: RawDecision) -> DecisionOutput:
    """Convert the flat LLM-wire shape into the discriminated-union branch."""
    if raw.action == "CALL_TOOL":
        if not raw.tool_name:
            # Infer tool_name from the args the LLM did provide before giving up.
            args = raw.tool_args or {}
            inferred = next(
                (_ARGS_TO_TOOL[k] for k in _ARGS_TO_TOOL if args.get(k)),
                None,
            )
            if inferred:
                raw = raw.model_copy(update={"tool_name": inferred})
            else:
                raise ValueError("CALL_TOOL decision requires `tool_name`.")
        args = raw.tool_args or {}
        required: dict[str, list[str]] = {
            "web_search": ["query"],
            "fetch_url":  ["url"],
            "get_time":   ["timezone"],
        }
        missing = [k for k in required.get(raw.tool_name, []) if not args.get(k)]
        if missing:
            raise ValueError(
                f"CALL_TOOL for {raw.tool_name!r} is missing required "
                f"tool_args field(s): {missing}. Emit non-empty tool_args."
            )
        return CallToolDecision(
            action="CALL_TOOL",
            tool_name=raw.tool_name,
            tool_args=args,
            reasoning=raw.reasoning,
        )
    if raw.action == "WRITE_MEMORY":
        if raw.record is None:
            raise ValueError("WRITE_MEMORY decision requires `record`.")
        return WriteMemoryDecision(
            action="WRITE_MEMORY",
            record=raw.record,
            reasoning=raw.reasoning,
        )
    # action == "FINAL_ANSWER"
    if raw.answer is None:
        raise ValueError("FINAL_ANSWER decision requires `answer`.")
    return FinalAnswerDecision(
        action="FINAL_ANSWER",
        answer=raw.answer,
        reasoning=raw.reasoning,
    )


if __name__ == "__main__":
    print(json.dumps(RawDecision.model_json_schema(), indent=2))
