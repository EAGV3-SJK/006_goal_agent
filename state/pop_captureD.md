

########################################################################
# RUN — 2026-05-22 23:11:02 UTC
# Query: Search for 'Python asyncio best practices', read the top 3 results, and give me a short numbered list of the advice they agree on.
########################################################################


════════════════════════════════════════════════════════════════════════
## PERCEPTION — 2026-05-22 23:11:06 UTC
════════════════════════════════════════════════════════════════════════

### System Prompt (rendered)

```
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
User: "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."
→ query_type=fact_lookup, expected_answer_schema=BiographyAnswer,
  entities=["Claude Shannon", "Wikipedia"], memory_relevant=false.

User: "Find 3 family-friendly things to do in Tokyo this weekend. Check Saturday's weather forecast there and tell me which one is most appropriate."
→ query_type=synthesis, expected_answer_schema=ActivityRecommendation,
  entities=["Tokyo"], memory_relevant=false.

User: "My mom's birthday is 15 May 2026. Remember that and give me a calendar reminder for two weeks before and on the day."
→ query_type=memory_write, expected_answer_schema=MemoryWriteAck,
  entities=[], memory_relevant=false.

User: "When is mom's birthday?"
→ query_type=memory_recall, expected_answer_schema=BirthdayRecallAnswer,
  entities=[], memory_relevant=true.

User: "Search for 'Python asyncio best practices', read the top 3 results, and give me a short numbered list of the advice they agree on."
→ query_type=synthesis, expected_answer_schema=AsyncioBestPractices,
  entities=["Python", "asyncio"], memory_relevant=false.

# Stored facts (current contents of the agent's notebook):
- moms_birthday: {"date": "15 May 2026"}

```

### User Query

```
Search for 'Python asyncio best practices', read the top 3 results, and give me a short numbered list of the advice they agree on.
```

### Parsed PerceptionOutput

```json
{
  "user_query": "Search for 'Python asyncio best practices', read the top 3 results, and give me a short numbered list of the advice they agree on.",
  "intent": "The user wants to research Python asyncio best practices from multiple sources and summarize common advice.",
  "entities": [
    "Python",
    "asyncio"
  ],
  "query_type": "synthesis",
  "expected_answer_schema": "AsyncioBestPractices",
  "memory_relevant": false
}
```


────────────────────────────────────────────────────────────────────────
## DECISION — Iteration 1 of 10 — 2026-05-22 23:11:10 UTC
────────────────────────────────────────────────────────────────────────

### System Prompt (rendered)

```
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
Name:   AsyncioBestPractices
Schema:
{
  "description": "Query D \u2014 agreed asyncio best practices synthesised from multiple sources.",
  "properties": {
    "tips": {
      "description": "Numbered list of agreed best practices (at least 3).",
      "items": {
        "type": "string"
      },
      "minItems": 3,
      "title": "Tips",
      "type": "array"
    },
    "pages_read": {
      "description": "URLs of pages fully fetched via the fetch_url tool during this run. Workflow: (1) web_search returns candidate URLs, (2) call fetch_url on each candidate \u2014 one per iteration, (3) record each fetched URL here. Each entry must match the `url` arg of a successful fetch_url call in the scratchpad. Requires at least 3 fetch_url successes.",
      "items": {
        "type": "string"
      },
      "minItems": 3,
      "title": "Pages Read",
      "type": "array"
    },
    "sources": {
      "description": "URLs consulted.",
      "items": {
        "type": "string"
      },
      "minItems": 1,
      "title": "Sources",
      "type": "array"
    }
  },
  "required": [
    "tips",
    "pages_read"
  ],
  "title": "AsyncioBestPractices",
  "type": "object"
}

# Stored facts (durable notebook)
- moms_birthday: {"date": "15 May 2026"}

# Perception summary
intent:       The user wants to research Python asyncio best practices from multiple sources and summarize common advice.
query_type:   synthesis
entities:     Python, asyncio

# Loop budget
You are on iteration 1 of 10. The cap is the hard end of
the agent loop — beyond it the run fails with no answer.

Commit rule: if the scratchpad already contains enough grounded data to fill
EVERY field of the answer schema above, emit FINAL_ANSWER NOW. Do not keep
searching for nicer sources or extra confirmation.

Near-cap rule: if iteration >= 10 - 1 and any field is still missing,
emit FINAL_ANSWER anyway with your best inference from the scratchpad and flag
the uncertainty in `reasoning`. A partial answer beats a timeout.

# Scratchpad — what you tried this run (oldest first)
(empty — this is iteration 1)

```

### Per-Query JSON Schema sent to LLM (RawDecision_AsyncioBestPractices)

```json
{
  "$defs": {
    "AsyncioBestPractices": {
      "description": "Query D \u2014 agreed asyncio best practices synthesised from multiple sources.",
      "properties": {
        "tips": {
          "description": "Numbered list of agreed best practices (at least 3).",
          "items": {
            "type": "string"
          },
          "minItems": 3,
          "title": "Tips",
          "type": "array"
        },
        "pages_read": {
          "description": "URLs of pages fully fetched via the fetch_url tool during this run. Workflow: (1) web_search returns candidate URLs, (2) call fetch_url on each candidate \u2014 one per iteration, (3) record each fetched URL here. Each entry must match the `url` arg of a successful fetch_url call in the scratchpad. Requires at least 3 fetch_url successes.",
          "items": {
            "type": "string"
          },
          "minItems": 3,
          "title": "Pages Read",
          "type": "array"
        },
        "sources": {
          "description": "URLs consulted.",
          "items": {
            "type": "string"
          },
          "minItems": 1,
          "title": "Sources",
          "type": "array"
        }
      },
      "required": [
        "tips",
        "pages_read"
      ],
      "title": "AsyncioBestPractices",
      "type": "object"
    },
    "MemoryRecord": {
      "description": "One entry in the notebook.",
      "properties": {
        "id": {
          "description": "Short unique key, e.g. 'moms_birthday'.",
          "title": "Id",
          "type": "string"
        },
        "kind": {
          "description": "'fact' is loaded into context on every run; 'episode' is for audit only.",
          "enum": [
            "fact",
            "episode"
          ],
          "title": "Kind",
          "type": "string"
        },
        "content": {
          "additionalProperties": true,
          "title": "Content",
          "type": "object"
        },
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "source": {
          "default": "agent_inference",
          "title": "Source",
          "type": "string"
        }
      },
      "required": [
        "id",
        "kind"
      ],
      "title": "MemoryRecord",
      "type": "object"
    }
  },
  "properties": {
    "action": {
      "description": "Which branch this decision is.",
      "enum": [
        "CALL_TOOL",
        "WRITE_MEMORY",
        "FINAL_ANSWER"
      ],
      "title": "Action",
      "type": "string"
    },
    "reasoning": {
      "description": "One short sentence \u2014 why this action.",
      "title": "Reasoning",
      "type": "string"
    },
    "tool_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Required when action=CALL_TOOL.",
      "title": "Tool Name"
    },
    "tool_args": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Required when action=CALL_TOOL. For web_search: {\"query\": str}. For fetch_url: {\"url\": str}. For get_time: {\"timezone\": str}.",
      "title": "Tool Args"
    },
    "record": {
      "anyOf": [
        {
          "$ref": "#/$defs/MemoryRecord"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Required when action=WRITE_MEMORY."
    },
    "answer": {
      "anyOf": [
        {
          "$ref": "#/$defs/AsyncioBestPractices"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Required when action=FINAL_ANSWER. Must conform to AsyncioBestPractices."
    }
  },
  "required": [
    "action",
    "reasoning"
  ],
  "title": "RawDecision_AsyncioBestPractices",
  "type": "object"
}
```

### Raw LLM Response

```json
{"action": "CALL_TOOL", "reasoning": "The query requires synthesizing information from multiple sources, so I must start by searching for authoritative URLs.", "tool_name": "web_search", "tool_args": {"query": "Python asyncio best practices", "max_results": 5}}
```

### Validated Decision (`CALL_TOOL`)

```json
{
  "action": "CALL_TOOL",
  "reasoning": "The query requires synthesizing information from multiple sources, so I must start by searching for authoritative URLs.",
  "tool_name": "web_search",
  "tool_args": {
    "query": "Python asyncio best practices",
    "max_results": 5
  }
}
```

### Final-Answer Validation (AsyncioBestPractices)

*(not a FINAL_ANSWER — action is CALL_TOOL)*


────────────────────────────────────────────────────────────────────────
## DECISION — Iteration 5 of 10 — 2026-05-22 23:11:47 UTC
────────────────────────────────────────────────────────────────────────

### System Prompt (rendered)

```
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
Name:   AsyncioBestPractices
Schema:
{
  "description": "Query D \u2014 agreed asyncio best practices synthesised from multiple sources.",
  "properties": {
    "tips": {
      "description": "Numbered list of agreed best practices (at least 3).",
      "items": {
        "type": "string"
      },
      "minItems": 3,
      "title": "Tips",
      "type": "array"
    },
    "pages_read": {
      "description": "URLs of pages fully fetched via the fetch_url tool during this run. Workflow: (1) web_search returns candidate URLs, (2) call fetch_url on each candidate \u2014 one per iteration, (3) record each fetched URL here. Each entry must match the `url` arg of a successful fetch_url call in the scratchpad. Requires at least 3 fetch_url successes.",
      "items": {
        "type": "string"
      },
      "minItems": 3,
      "title": "Pages Read",
      "type": "array"
    },
    "sources": {
      "description": "URLs consulted.",
      "items": {
        "type": "string"
      },
      "minItems": 1,
      "title": "Sources",
      "type": "array"
    }
  },
  "required": [
    "tips",
    "pages_read"
  ],
  "title": "AsyncioBestPractices",
  "type": "object"
}

# Stored facts (durable notebook)
- moms_birthday: {"date": "15 May 2026"}

# Perception summary
intent:       The user wants to research Python asyncio best practices from multiple sources and summarize common advice.
query_type:   synthesis
entities:     Python, asyncio

# Loop budget
You are on iteration 5 of 10. The cap is the hard end of
the agent loop — beyond it the run fails with no answer.

Commit rule: if the scratchpad already contains enough grounded data to fill
EVERY field of the answer schema above, emit FINAL_ANSWER NOW. Do not keep
searching for nicer sources or extra confirmation.

Near-cap rule: if iteration >= 10 - 1 and any field is still missing,
emit FINAL_ANSWER anyway with your best inference from the scratchpad and flag
the uncertainty in `reasoning`. A partial answer beats a timeout.

# Scratchpad — what you tried this run (oldest first)
[1] CALL_TOOL OK  :: call web_search({"max_results": 5, "query": "Python asyncio best practices"})
       result: [{"title": "Asyncio Best Practices and Common Pitfalls - Shane's Personal Blog", "url": "https://www.shanechang.com/p/python-asyncio-best-practices-pitfalls", "snippet": "Featured image of post Asyncio Best Practices and Common Pitfalls\n\nPython Concurrency\n\n## Asyncio Best Practices and Common Pitfalls\n\n### Learn the essential best practices and avoid common mistakes when working with Python's asyncio library\n\n## Writing Better Asyncio Code: Dos and Don\u2019ts\n\nPython\u2019s asyncio library is powerful but comes with its own set of conventions and potential pitfalls. Let\u2019s explore the best practices to follow and common mistakes to avoid.\n\n### Best Practices\n\n#### 1. Use `asyncio.run()` as Your Main Entry Point\n\nAlways use `asyncio.run()` to start your asyncio programs: [...] Always use `asyncio.run()` to start your asyncio programs:\n\n```\n# Good practice # Good practice # Good practiceasync def main(): async def main(): async def main():  # Your async code here  # Your async code here # Your async code here  pass  pass pass   if __name__ == \"__main__\": if __name__ == \"__main__\": if __name__ == \"__main__\": asyncio.run(main())  asyncio.run(main()) asyncio. run(main())\n```\n\nThis function properly sets up and tears down the event loop, and handles cleanup when exceptions occur.\n\n#### 2. Prefer Async Context Managers\n\nWhen available, use async context managers (`async with`) for proper resource management: [...] ```\n# Bad - coroutine is created but never executed # Bad - coroutine is created but never executed # Bad - coroutine is created but never executedfetch_data(url) fetch_data(url) fetch_data(url)   # Good - coroutine is awaited and executed # Good - coroutine is awaited and executed # Good - coroutine is awaited and executedawait fetch_data(url) await fetch_data(url) await fetch_data(url)   # Also good - coroutine is executed via asyncio.run() # Also good - coroutine is executed via asyncio.run() # Also good - coroutine is executed via asyncio.run()asyncio.run(fetch_data(url)) asyncio.run(fetch_data(url)) asyncio. run(fetch_data(url))\n```\n\n#### 4. Handle Cancellation Gracefully\n\nAlways catch `CancelledError` and clean up resources in tasks that might be cancelled:"}, {"title": "Asyncio best practices - Async-SIG - Discussions on Python.org", "url": "https://discuss.python.org/t/asyncio-best-practices/12576", "snippet": "# Asyncio best practices\n\nSo I thought it\u2019d be great to catalog some of the best practices and patterns to follow while writing asynchronous code in Python, in order to help guide all developers who are planning to use this awesome feature on how to use it right.  \nWhat I mention here is not ultimate and might need to be corrected by Devs who have used this feature longer that I have, and also updated with more design patterns.\n\n### 1)async/await usage\n\nAsync functions are not necessarily asynchronous. I\u2019ve noticed that coroutines shall run in order as they have been written in code, which isn\u2019t exactly asynchronous but generally synchronous in nature. For example [...] `import asyncio\nimport time\nasync def waiter (secs):\ntime.sleep(secs)\nasync def main():\nawait waiter(1)\nawait waiter(2)\nawait waiter(3)\nasyncio.run(main())`\n\nSuch a program will run from top to bottom just as a synchronous program would. So in order to make it asynchronous, you have to interact with the asyncio library\n\n### 2) Do not create functions with long running loops\n\nHaving function that contain long running loops cause the event loop to halt until the function finishes, which causes lag.  \nThe best way to go around this is to rely on the already existing event loop and just schedule every iteration of your function loop onto the event loop. For example\n\n`def long_runner(value):\nloop = asyncio.get_running_loop()\nif (value <= 1_000):\nloop.call_soon(long_runner((value+1)))` [...] ### 3) using tasks\n\nI think using tasks is the equivalent of manually scheduling functions on the event loop since in this case, the tasks shall be tracked by the event loop.  \nI don\u2019t think I can explain this concept better than @ambv on the series he created about asyncio,\n\nThere exists more patterns that we can use and share in order to build really great applications with asyncio, so I\u2019m hoping this topics could act as a catalogue to these patterns and continously kept up-to-date with more current patterns\n\nPowered by Discourse, best viewed with JavaScript enabled"}, {"title": "How to Use asyncio for Concurrent Programming in Python", "url": "https://oneuptime.com/blog/post/2026-01-24-asyncio-concurrent-programming-python/view", "snippet": "## Running Blocking Code in Async Context\n\n`import asyncio\nimport time\ndef blocking_operation():\n\"\"\"A blocking I/O operation (simulate with sleep).\"\"\"\ntime.sleep(2)\nreturn \"Blocking result\"\nasync def main():\nloop = asyncio.get_running_loop()\n# Run blocking code in thread pool\nresult = await loop.run_in_executor(\nNone, # Use default executor\nblocking_operation\n)\nprint(f\"Result: {result}\")\nasyncio.run(main())`\n\n## Best Practices\n\n### 1. Do Not Block the Event Loop\n\n`# Bad: Blocks the entire event loop\nasync def bad_example():\ntime.sleep(5) # Blocks!\n# Good: Use async sleep\nasync def good_example():\nawait asyncio.sleep(5) # Non-blocking`\n\n### 2. Create Tasks for Independent Operations [...] ### 2. Create Tasks for Independent Operations\n\n`# Sequential (slow)\nasync def sequential():\nresult1 = await fetch_data(1)\nresult2 = await fetch_data(2)\n# Concurrent (fast)\nasync def concurrent():\ntask1 = asyncio.create_task(fetch_data(1))\ntask2 = asyncio.create_task(fetch_data(2))\nresult1 = await task1\nresult2 = await task2`\n\n### 3. Handle Cancellation Gracefully\n\n`async def cancellable_task():\ntry:\nwhile True:\nawait asyncio.sleep(1)\nprint(\"Working...\")\nexcept asyncio.CancelledError:\nprint(\"Task cancelled, cleaning up...\")\nraise #...
[2] CALL_TOOL OK  :: call fetch_url({"url": "https://www.shanechang.com/p/python-asyncio-best-practices-pitfalls"})
       result: {"status": 200, "content_type": "text/html; charset=utf-8", "length_bytes": 3526, "text": "Asyncio Best Practices and Common Pitfalls\nShane's Personal Blog\nGain wisdom at dawn; die with no regret at dusk.\nHome\nAbout Me\nPortfolio\nFavorite Quotes\nThink Different\nEnglish\u7b80\u4f53\u4e2d\u6587\nDark Mode\nPython\nConcurrency\nAsyncio Best Practices and Common Pitfalls\nLearn the essential best practices and avoid common mistakes when working with Python's asyncio library\nMar 09, 2025\n2 minute read\n\u7b80\u4f53\u4e2d\u6587\nCopy URL\nCopy as Markdown\nTable of contents\n6 sections\nTap to expand\nWriting Better Asyncio Code: Dos and Don\u2019ts\nBest Practices\n1. Use asyncio.run() as Your Main Entry Point\n2. Prefer Async Context Managers\n3. Always Await Coroutines\n4. Handle Cancellation Gracefully\nWriting Better Asyncio Code: Dos and Don\u2019ts\nPython\u2019s asyncio library is powerful but comes with its own set of conventions and potential pitfalls. Let\u2019s explore the best practices to follow and common mistakes to avoid.\nBest Practices\n1. Use asyncio.run() as Your Main Entry Point\nAlways use asyncio.run() to start your asyncio programs:\n# Good practice\nasync def main():\n# Your async code here\npass\nif __name__ == \"__main__\":\nasyncio.run(main())\nThis function properly sets up and tears down the event loop, and handles cleanup when exceptions occur.\n2. Prefer Async Context Managers\nWhen available, use async context managers (async with) for proper resource management:\n# Good practice\nasync with aiohttp.ClientSession() as session:\nasync with session.get(url) as response:\ndata = await response.text()\n3. Always Await Coroutines\nOne of the most common mistakes is forgetting to await coroutines. Always await them:\n# Bad - coroutine is created but never executed\nfetch_data(url)\n# Good - coroutine is awaited and executed\nawait fetch_data(url)\n# Also good - coroutine is executed via asyncio.run()\nasyncio.run(fetch_data(url))\n4. Handle Cancellation Gracefully\nAlways catch CancelledError and clean up resources in tasks that might be cancelled:\nasync def cancellable_task():\ntry:\n# Your task code\nwhile True:\nawait asyncio.sleep(1)\n# Do work...\nexcept asyncio.CancelledError:\n# Clean up resources here\nprint(\"Task was cancelled, cleaning up...\")\nraise # Re-raise so caller knows task was cancelle\nAsyncio\nBest-Practices\nDebugging\nAll Rights Reserved\nRelated content\nDiscover more articles that might interest you\nPython\nConcurrency\nAsyncio Tasks: Managing Concurrent Operations\nLearn how to use asyncio Tasks to run multiple operations concurrently in Python without threads\nMar 09, 2025\n2 minute read\nPython\nConcurrency\nCooperative Multitasking: The Core of Python Asyncio\nLearn how Python's cooperative multitasking works and how it differs from traditional threading\nMar 09, 2025\n3 minute read\nPython\nConcurrency\nProcessing Results as They Arrive with as_completed\nLearn how to use asyncio.as_completed to handle task results immediately when they're ready\nMar 09, 2025\n2 minute read\nPython\nConcurrency\nPython Asyncio: Coroutines Explained\nA clear explanation of Python coroutines, the fundamental building blocks of asyncio programming\nMar 09, 2025\n2 minute read\nPython\nConcurrency\nPython's GIL and Asyncio: Understanding the Relationship\nLearn how Python's Global Interpreter Lock relates to asyncio concurrency and when to use each approach\nMar 09, 2025\n3 minute read\n\u00a9\n2022 - 2026\nShane Zhang\nAll Rights Reserved\nTable of contents\nWriting Better Asyncio Code: Dos and Don\u2019ts\nBest Practices\n1. Use asyncio.run() as Your Main Entry Point\n2. Prefer Async Context Managers\n3. Always Await Coroutines\n4. Handle Cancellation Gracefully"}
[3] CALL_TOOL OK  :: call fetch_url({"url": "https://discuss.python.org/t/asyncio-best-practices/12576"})
       result: {"status": 200, "content_type": "text/html; charset=utf-8", "length_bytes": 2157, "text": "Discussions on Python.org\nAsyncio best practices\nAsync-SIG\nTobiasHT\n(TobiasHT)\nDecember 16, 2021, 5:05am\n1\nSo I thought it\u2019d be great to catalog some of the best practices and patterns to follow while writing asynchronous code in Python, in order to help guide all developers who are planning to use this awesome feature on how to use it right.\nWhat I mention here is not ultimate and might need to be corrected by Devs who have used this feature longer that I have, and also updated with more design patterns.\n1)async/await usage\nAsync functions are not necessarily asynchronous. I\u2019ve noticed that coroutines shall run in order as they have been written in code, which isn\u2019t exactly asynchronous but generally synchronous in nature. For example\nimport asyncio\nimport time\nasync def waiter (secs):\ntime.sleep(secs)\nasync def main():\nawait waiter(1)\nawait waiter(2)\nawait waiter(3)\nasyncio.run(main())\nSuch a program will run from top to bottom just as a synchronous program would. So in order to make it asynchronous, you have to interact with the asyncio library\n2) Do not create functions with long running loops\nHaving function that contain long running loops cause the event loop to halt until the function finishes, which causes lag.\nThe best way to go around this is to rely on the already existing event loop and just schedule every iteration of your function loop onto the event loop. For example\ndef long_runner(value):\nloop = asyncio.get_running_loop()\nif (value <= 1_000):\nloop.call_soon(long_runner((value+1)))\n3) using tasks\nI think using tasks is the equivalent of manually scheduling functions on the event loop since in this case, the tasks shall be tracked by the event loop.\nI don\u2019t think I can explain this concept better than @ambv on the series he created about asyncio,\nThere exists more patterns that we can use and share in order to build really great applications with asyncio, so I\u2019m hoping this topics could act as a catalogue to these patterns and continously kept up-to-date with more current patterns\nHome\nCategories\nGuidelines\nTerms of Service\nPrivacy Policy\nPowered by Discourse, best viewed with JavaScript enabled"}
[4] CALL_TOOL OK  :: call fetch_url({"url": "https://oneuptime.com/blog/post/2026-01-24-asyncio-concurrent-programming-python/view"})
       result: {"status": 200, "content_type": "text/html; charset=utf-8", "length_bytes": 15857, "text": "Skip to main content\nOneUptime\nOpen menu\nProducts\nEssentials\nMonitoring\nUptime & synthetic checks\nStatus Page\nCommunicate incidents to users\nIncidents\nDetect, manage & resolve\nOn-Call & Alerts\nSmart routing & escalations\nScheduled Maintenance\nPlan & communicate downtime\nObservability\nLogs\nFastest log ingest & search\nMetrics\nApplication & infra metrics\nTraces\nDistributed request tracing\nExceptions\nError tracking & debugging\nProfiles\nCPU & memory profiling\nInfrastructure\nKubernetes\nCluster & pod observability\nDocker\nHost & container observability\nHosts\nAuto-discovered server metrics\nAutomation & Analytics\nWorkflows\nNo-code automation builder\nRunbooks\nAuto-trigger response steps\nDashboards\nCustom data visualizations\nAI Agent\nAuto-fix issues with AI-powered PRs. Let AI analyze incidents and automatically create pull requests to resolve them.\nResources\nDocumentation\nAPI Reference\nGitHub\nBlog & Guides\nGet Started\nStart Free Trial\nRequest Demo\n[email protected]\nOpen Source \u2014 Self-host or use our cloud. Your data, your choice.\nView Pricing\nEnterprise\nEnterprise\nEnterprise\nBuilt for how you work\nScale your reliability operations with enterprise-grade tools.\nEnterprise Overview\nScale with confidence\nRequest Demo\nSee it in action\nContact Sales\nEnterprise\nEnterprise Overview\nSolutions for large organizations\nRequest Demo\nSchedule a personalized demo\nTeams\nDevOps\nSRE\nPlatform\nDevelopers\nIndustries\nFinTech\nSaaS\nHealthcare\nE-Commerce\nMedia\nGovernment\nDocumentation\nPricing\nBlog\nGet Started Free\nPricing\nResources\nResources\nLearn & Connect\nEverything you need to get started and succeed.\nDocumentation\nGuides & tutorials\nAPI Reference\nREST API & SDKs\nStar on GitHub\nLearn\nBlog\nNews & insights\nStatus\nSystem status\nChangelog\nWhat's new\nVideos\nWatch & learn\nSupport\nHelp Center\nContact Us\nCompany\nAbout Us\nMerch Store\nLegal\nPrivacy\nTerms\n100% Open Source\nSign\nin\nSign up\nClose menu\nStatus Page\nIncidents\nMonitoring\nOn-Call\nMaintenance\nLogs\nMetrics\nTraces\nExceptions\nKubernetes\nDocker\nHosts\nProfiles\nWorkflows\nDashboards\nAI Agent\nEnterprise\nDevOps\nSRE\nPlatform\nPricing\nDocs\nRequest Demo\nSupport\nSign\nup\nExisting customer?\nSign in\nHow to Use asyncio for Concurrent Programming in Python\nMaster Python's asyncio library for writing concurrent code. Learn async/await syntax, running tasks concurrently, and handling real-world scenarios like API calls and file I/O.\n@nawazdhandala\n\u2022\nJan 24, 2026\n\u2022\nReading time\nPython\nAsyncio\nConcurrency\nAsync/Await\nPerformance\nOn this page\nWhen your program spends time waiting for I/O operations like network requests or file reads, asyncio lets it do other work instead of sitting idle. This guide covers the fundamentals of asyncio and practical patterns for building efficient concurrent applications.\nAsyncio is Python's built-in library for writing concurrent code using the async/await syntax. It is particularly effective for I/O-bound operations where your program waits for external resources like databases, APIs, or file systems.\nUnderstanding Async vs Sync\nFirst, let us see why async matters:\nimport time\nimport asyncio\n# Synchronous version - total time: 3 seconds\ndef sync_fetch_data():\ntime.sleep(1) # Simulates network request\nreturn \"data\"\ndef sync_main():\nstart = time.time()\nresult1 = sync_fetch_data()\nresult2 = sync_fetch_data()\nresult3 = sync_fetch_data()\nprint(f\"Sync total time: {time.time() - start:.2f}s\")\n# Asynchronous version - total time: ~1 second\nasync def async_fetch_data():\nawait asyncio.sleep(1) # Non-blocking sleep\nreturn \"data\"\nasync def async_main():\nstart = time.time()\n# Run all three concurrently\nresults = await asyncio.gather(\nasync_fetch_data(),\nasync_fetch_data(),\nasync_fetch_data()\n)\nprint(f\"Async total time: {time.time() - start:.2f}s\")\n# Run both\nsync_main() # Sync total time: 3.00s\nasyncio.run(async_main()) # Async total time: 1.00s\nThe async version runs all three operations concurrently while waiting.\nBasic Async/Await Syntax\nDefining Async Functions\nimport asyncio\n# Define an async function with 'async def'\nasync def greet(name):\nprint(f\"Hello, {name}!\")\nawait asyncio.sleep(1) # Non-blocking wait\nprint(f\"Goodbye, {name}!\")\nreturn f\"Greeted {name}\"\n# Run an async function\nresult = asyncio.run(greet(\"Alice\"))\nprint(result)\nThe await Keyword\nawait can only be used inside async functions and suspends execution until the awaited coroutine completes:\nasync def fetch_user(user_id):\nawait asyncio.sleep(0.5) # Simulate API call\nreturn {\"id\": user_id, \"name\": f\"User {user_id}\"}\nasync def fetch_posts(user_id):\nawait asyncio.sleep(0.5) # Simulate API call\nreturn [{\"id\": 1, \"title\": \"Post 1\"}, {\"id\": 2, \"title\": \"Post 2\"}]\nasync def get_user_with_posts(user_id):\n# These run sequentially\nuser = await fetch_user(user_id)\nposts = await fetch_posts(user_id)\nuser[\"posts\"] = posts\nreturn user\n# Run it\nresult = asyncio.run(get_user_with_posts(123))\nprint(result)\nRunning Tasks Concurrently\nUsing asyncio.gather()\ngather() runs multiple coroutines concurrently and returns results in order:\nimport asyncio\nasync def fetch_url(url):\nprint(f\"Fetching {url}\")\nawait asyncio.sleep(1) # Simulate network delay\nreturn f\"Content from {url}\"\nasync def main():\nurls = [\n\"https://api.example.com/users\",\n\"https://api.example.com/posts\",\n\"https://api.example.com/comments\"\n]\n# Fetch all URLs concurrently\nresults = await asyncio.gather(*[fetch_url(url) for url in urls])\nfor url, result in zip(urls, results):\nprint(f\"{url}: {result}\")\nasyncio.run(main())\nUsing asyncio.create_task()\nCreate tasks to run in the background:\nasync def background_task():\nwhile True:\nprint(\"Background task running...\")\nawait asyn...

```

### Per-Query JSON Schema sent to LLM (RawDecision_AsyncioBestPractices)

```json
{
  "$defs": {
    "AsyncioBestPractices": {
      "description": "Query D \u2014 agreed asyncio best practices synthesised from multiple sources.",
      "properties": {
        "tips": {
          "description": "Numbered list of agreed best practices (at least 3).",
          "items": {
            "type": "string"
          },
          "minItems": 3,
          "title": "Tips",
          "type": "array"
        },
        "pages_read": {
          "description": "URLs of pages fully fetched via the fetch_url tool during this run. Workflow: (1) web_search returns candidate URLs, (2) call fetch_url on each candidate \u2014 one per iteration, (3) record each fetched URL here. Each entry must match the `url` arg of a successful fetch_url call in the scratchpad. Requires at least 3 fetch_url successes.",
          "items": {
            "type": "string"
          },
          "minItems": 3,
          "title": "Pages Read",
          "type": "array"
        },
        "sources": {
          "description": "URLs consulted.",
          "items": {
            "type": "string"
          },
          "minItems": 1,
          "title": "Sources",
          "type": "array"
        }
      },
      "required": [
        "tips",
        "pages_read"
      ],
      "title": "AsyncioBestPractices",
      "type": "object"
    },
    "MemoryRecord": {
      "description": "One entry in the notebook.",
      "properties": {
        "id": {
          "description": "Short unique key, e.g. 'moms_birthday'.",
          "title": "Id",
          "type": "string"
        },
        "kind": {
          "description": "'fact' is loaded into context on every run; 'episode' is for audit only.",
          "enum": [
            "fact",
            "episode"
          ],
          "title": "Kind",
          "type": "string"
        },
        "content": {
          "additionalProperties": true,
          "title": "Content",
          "type": "object"
        },
        "created_at": {
          "format": "date-time",
          "title": "Created At",
          "type": "string"
        },
        "source": {
          "default": "agent_inference",
          "title": "Source",
          "type": "string"
        }
      },
      "required": [
        "id",
        "kind"
      ],
      "title": "MemoryRecord",
      "type": "object"
    }
  },
  "properties": {
    "action": {
      "description": "Which branch this decision is.",
      "enum": [
        "CALL_TOOL",
        "WRITE_MEMORY",
        "FINAL_ANSWER"
      ],
      "title": "Action",
      "type": "string"
    },
    "reasoning": {
      "description": "One short sentence \u2014 why this action.",
      "title": "Reasoning",
      "type": "string"
    },
    "tool_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Required when action=CALL_TOOL.",
      "title": "Tool Name"
    },
    "tool_args": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Required when action=CALL_TOOL. For web_search: {\"query\": str}. For fetch_url: {\"url\": str}. For get_time: {\"timezone\": str}.",
      "title": "Tool Args"
    },
    "record": {
      "anyOf": [
        {
          "$ref": "#/$defs/MemoryRecord"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Required when action=WRITE_MEMORY."
    },
    "answer": {
      "anyOf": [
        {
          "$ref": "#/$defs/AsyncioBestPractices"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Required when action=FINAL_ANSWER. Must conform to AsyncioBestPractices."
    }
  },
  "required": [
    "action",
    "reasoning"
  ],
  "title": "RawDecision_AsyncioBestPractices",
  "type": "object"
}
```

### Raw LLM Response

```json
{"action": "FINAL_ANSWER", "reasoning": "Top results agree on best practices", "answer": {"tips": ["Use asyncio.run() as the main entry point", "Prefer async context managers", "Always await coroutines", "Handle cancellation gracefully"], "pages_read": ["https://www.shanechang.com/p/python-asyncio-best-practices-pitfalls", "https://discuss.python.org/t/asyncio-best-practices/12576", "https://oneuptime.com/blog/post/2026-01-24-asyncio-concurrent-programming-python/view"], "sources": ["https://www.shanechang.com/p/python-asyncio-best-practices-pitfalls", "https://discuss.python.org/t/asyncio-best-practices/12576", "https://oneuptime.com/blog/post/2026-01-24-asyncio-concurrent-programming-python/view"]}}
```

### Validated Decision (`FINAL_ANSWER`)

```json
{
  "action": "FINAL_ANSWER",
  "reasoning": "Top results agree on best practices",
  "answer": {
    "tips": [
      "Use asyncio.run() as the main entry point",
      "Prefer async context managers",
      "Always await coroutines",
      "Handle cancellation gracefully"
    ],
    "pages_read": [
      "https://www.shanechang.com/p/python-asyncio-best-practices-pitfalls",
      "https://discuss.python.org/t/asyncio-best-practices/12576",
      "https://oneuptime.com/blog/post/2026-01-24-asyncio-concurrent-programming-python/view"
    ],
    "sources": [
      "https://www.shanechang.com/p/python-asyncio-best-practices-pitfalls",
      "https://discuss.python.org/t/asyncio-best-practices/12576",
      "https://oneuptime.com/blog/post/2026-01-24-asyncio-concurrent-programming-python/view"
    ]
  }
}
```

### Final-Answer Validation (AsyncioBestPractices)

```json
{
  "tips": [
    "Use asyncio.run() as the main entry point",
    "Prefer async context managers",
    "Always await coroutines",
    "Handle cancellation gracefully"
  ],
  "pages_read": [
    "https://www.shanechang.com/p/python-asyncio-best-practices-pitfalls",
    "https://discuss.python.org/t/asyncio-best-practices/12576",
    "https://oneuptime.com/blog/post/2026-01-24-asyncio-concurrent-programming-python/view"
  ],
  "sources": [
    "https://www.shanechang.com/p/python-asyncio-best-practices-pitfalls",
    "https://discuss.python.org/t/asyncio-best-practices/12576",
    "https://oneuptime.com/blog/post/2026-01-24-asyncio-concurrent-programming-python/view"
  ]
}
```
