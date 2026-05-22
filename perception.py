"""
perception.py — The Perception layer.

Runs ONCE at the start of each agent run. Reads the raw user query plus the
current notebook (facts only) and returns a typed PerceptionOutput that the
Decision layer leans on for every iteration.

A misclassified query_type or expected_answer_schema here sends Decision down
the wrong path for the whole run, so this prompt is the most carefully
constrained one in the agent.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from llm_gateway.client import LLM
from memory import render_facts_for_prompt
from schema import MemoryStore, PerceptionOutput

_POP_PATH = Path(__file__).parent / "state" / "pop_capture.md"


def _pop_append(text: str) -> None:
    _POP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _POP_PATH.open("a", encoding="utf-8") as f:
        f.write(text)


PERCEPTION_SYSTEM_PROMPT = """\
You are the PERCEPTION layer of a four-role cognitive agent.

Your job: read the user's query ONCE and return a structured analysis that
DECISION will read on every iteration. You will NOT see the query again,
so be thorough.

You MUST return JSON conforming to the PerceptionOutput schema.

# query_type — pick exactly one
- "fact_lookup"   : a single fresh fact requiring one or two web lookups.
                    e.g. "Fetch a Wikipedia page and extract birth date, death date, contributions."
- "synthesis"     : multi-source research requiring fetching and combining 2+ sources.
                    e.g. "Search multiple sources, read them, and synthesize a list."
- "memory_write"  : the user is telling you to remember something durable.
                    Usually starts with "Remember that…" or "My X is Y." or "Note that…"
- "memory_recall" : the user's question can ONLY be answered using a previously stored fact.
                    e.g. "When is mom's birthday?" (requires stored fact to answer)

# expected_answer_schema — name the Pydantic model that FINAL_ANSWER must fill
- "BiographyAnswer"          biography: birth/death dates + 3 key contributions + source URL
- "ActivityRecommendation"   3 activities + weather summary + recommendation + reasoning
- "MemoryWriteAck"           acknowledgement of a stored fact + confirmation note
- "BirthdayRecallAnswer"     birthday date recalled from memory + brief note
- "AsyncioBestPractices"     numbered list of ≥3 agreed tips + source URLs

# Other rules
- intent: one short English sentence, under 25 words, restating the user's request.
- entities: extract proper nouns, names, places, libraries. Flat list of strings.
- memory_relevant: TRUE only if at least one stored fact would meaningfully change
  the answer. FALSE for fresh lookups and memory_write requests.

# Examples
User: "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, \
death date, and three key contributions to information theory."
→ query_type=fact_lookup, expected_answer_schema=BiographyAnswer,
  entities=["Claude Shannon", "Wikipedia"], memory_relevant=false.

User: "Find 3 family-friendly things to do in Tokyo this weekend. Check Saturday's weather \
forecast there and tell me which one is most appropriate."
→ query_type=synthesis, expected_answer_schema=ActivityRecommendation,
  entities=["Tokyo"], memory_relevant=false.

User: "My mom's birthday is 15 May 2026. Remember that and give me a calendar reminder \
for two weeks before and on the day."
→ query_type=memory_write, expected_answer_schema=MemoryWriteAck,
  entities=[], memory_relevant=false.

User: "When is mom's birthday?"
→ query_type=memory_recall, expected_answer_schema=BirthdayRecallAnswer,
  entities=[], memory_relevant=true.

User: "Search for 'Python asyncio best practices', read the top 3 results, and give me a \
short numbered list of the advice they agree on."
→ query_type=synthesis, expected_answer_schema=AsyncioBestPractices,
  entities=["Python", "asyncio"], memory_relevant=false.

# Stored facts (current contents of the agent's notebook):
{facts}
"""


def perceive(
    user_query: str,
    memory: MemoryStore,
    *,
    llm: LLM | None = None,
) -> PerceptionOutput:
    """Run one Perception LLM call. Returns a typed PerceptionOutput.

    Args:
        user_query: raw text from the user.
        memory:     current MemoryStore (we render its facts into the prompt).
        llm:        optional LLM client override (for tests).
    """
    client = llm or LLM()
    system_text = PERCEPTION_SYSTEM_PROMPT.format(
        facts=render_facts_for_prompt(memory),
    )
    response_format = {
        "type": "json_schema",
        "schema": PerceptionOutput.model_json_schema(),
        "name": "PerceptionOutput",
        "strict": True,
    }
    resp = client.chat(
        prompt=user_query,
        system=system_text,
        response_format=response_format,
        auto_route="perception",
        temperature=0.0,   # classification → deterministic
        max_tokens=600,
    )
    parsed = resp.get("parsed")
    if parsed is None:
        result = PerceptionOutput.model_validate_json(resp["text"])
    else:
        result = PerceptionOutput.model_validate(parsed)

    _pop_append(
        f"\n\n{'═'*72}\n"
        f"## PERCEPTION — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"{'═'*72}\n\n"
        f"### System Prompt (rendered)\n\n"
        f"```\n{system_text}\n```\n\n"
        f"### User Query\n\n"
        f"```\n{user_query}\n```\n\n"
        f"### Parsed PerceptionOutput\n\n"
        f"```json\n{result.model_dump_json(indent=2)}\n```\n"
    )
    return result


if __name__ == "__main__":
    import sys
    from memory import load_memory

    if len(sys.argv) < 2:
        print('usage: python perception.py "<query>"', file=sys.stderr)
        raise SystemExit(2)
    out = perceive(sys.argv[1], load_memory())
    print(out.model_dump_json(indent=2))
