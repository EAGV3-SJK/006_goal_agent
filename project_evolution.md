# Project Evolution — goal-agent (EAGV3 Session 6)

Date: 2026-05-23

---

## Starting Point

The project began as a working but rough first implementation of a four-layer cognitive agent. The working directory was `D:\sjk\eagv3\006_session` and the project was named `eagv3-session6` in `pyproject.toml`.

**Initial architecture:**
- `agent6.py` — iteration loop wiring all four layers
- `memory.py` — LLM-classified memory with keyword-overlap search
- `perception.py` — iterative goal decomposition (runs every loop iteration)
- `decision.py` — LLM-based next-step selection with basic rules
- `action.py` — MCP tool execution with artifact store
- `schema.py` — basic Pydantic types (Goal, Observation, ToolCall, DecisionOutput)
- `mcp_server.py` — 9 MCP tools over stdio
- `llm_gateway/` — LLM Gateway V3 (FastAPI, multi-provider routing)

**Known problems at start:**
- `ssl.create_default_context()` crashed on Windows with `OPENSSL_Uplink: no OPENSSL_Applink` (uv's managed CPython 3.12.11)
- `aiohttp 3.13.5` shipped an incompatible OpenSSL DLL → import crash
- `crawl4ai` emitted non-ASCII characters via Rich's `LegacyWindowsTerm` (Win32 console API), crashing with `UnicodeEncodeError` on Windows
- No `.gitignore`, no `README.md`
- Free-form dicts crossing layer boundaries (Pydantic contracts incomplete)
- Run commands used manual venv path `.\.venv\Scripts\python.exe`

---

## Phase 1 — Environment Fixes

### Python interpreter

`uv`'s managed CPython 3.12.11 had a broken `ssl` build on this machine. Rebuilt the venv using the system Python 3.13.5:

```powershell
uv venv --python "C:\apps\python313\python.exe"
uv sync
```

`pyproject.toml` updated to `requires-python = ">=3.13"` to pin the working interpreter.

### aiohttp downgrade

`aiohttp 3.13.5` ships a Windows DLL with an incompatible OpenSSL build. Fixed by pinning:

```toml
"aiohttp>=3.9.5,<3.10"
```

Verified: `import aiohttp; aiohttp.__version__` → `3.9.5`.

### crawl4ai silence on Windows

Rich's `LegacyWindowsTerm` uses the Win32 `WriteConsoleW` API, which bypasses fd-level redirects. `verbose=False` alone did not suppress all log paths. Fix: pass a silent `AsyncLogger` whose Rich `Console` writes to `io.StringIO()`:

```python
# mcp_server.py — _crawl4ai_fetch()
silent = AsyncLogger(verbose=False)
silent.console = rich.console.Console(file=io.StringIO(), quiet=True)
async with AsyncWebCrawler(logger=silent) as crawler:
    r = await crawler.arun(url=url)
```

---

## Phase 2 — Project Housekeeping

### Rename

`pyproject.toml` name changed from `eagv3-session6` → `goal-agent`. Description updated to reflect the four-layer architecture.

### Files created

**`.gitignore`** — excludes `state/` (durable memory and artifacts), `.venv/`, `__pycache__/`, `.env`, `usage.json`, `llm_gateway/*.db`, `sandbox/`.

**`README.md`** — setup instructions, run commands, architecture table, placeholder sections for terminal output, architectural contracts documentation (five loop invariants, perception prompts, decision routing).

**`session_notes.md`** — full session documentation: all issues, fixes, run status, architectural decisions.

---

## Phase 3 — uv Enforcement

The assignment required `uv` for all Python execution — no manual virtualenv activation.

- All run commands updated from `.\.venv\Scripts\python.exe run_agent.py A` → `uv run python run_agent.py A`
- LLM Gateway startup updated from `C:\apps\python313\python.exe -m uvicorn main:app --port 8101` → `uv run uvicorn main:app --port 8101`
- `pyproject.toml` pins `requires-python = ">=3.13"` and `aiohttp>=3.9.5,<3.10` so `uv run` never tries to reinstall incompatible packages at runtime

---

## Phase 4 — Pydantic Contract Audit

**Assignment requirement:** *"The four cognitive layers must each be backed by typed Pydantic contracts on their inputs and outputs. No free-form dict passing between roles. No regex on LLM output."*

### Contracts added to `schema.py`

| Type | Purpose |
|---|---|
| `HistoryEntry` | Typed action/answer record replacing `dict` in history list |
| `ActionResult` | Typed action output replacing raw `(str, Optional[str])` tuple |
| `ToolDef` | Typed tool definition replacing raw dicts passed to gateway |

### Layer updates

| File | Change |
|---|---|
| `agent6.py` | `history: list[HistoryEntry]`, `tools: list[ToolDef]`, typed attribute access |
| `action.py` | `execute()` returns `ActionResult` instead of tuple |
| `decision.py` | `next_step(history: List[HistoryEntry], tools: List[ToolDef])`, `[t.model_dump() for t in tools]` at LLM boundary only |
| `perception.py` | `observe(history: List[HistoryEntry], ...)` typed parameter |
| `memory.py` | `read(history: Union[str, List[HistoryEntry]])` typed parameter |
| `utils.py` | All helpers typed to `list[HistoryEntry]`, dict `.get()` replaced with attribute access |

---

## Phase 5 — Free-First Provider Routing

Changed `llm_gateway/main.py` to try free providers before paid ones:

**Before:** Anthropic → Gemini → others  
**After:**

```python
DEFAULT_ORDER = [
    "lmstudio", "ollama",                          # local (free)
    "cerebras", "groq", "nvidia",                  # free-tier cloud
    "openrouter", "github",                         # free-tier aggregators
    "anthropic", "gemini",                          # paid
]
```

Tier routing (`TINY` / `LARGE`) also updated to match this order.

---

## Phase 6 — Architecture Refactor

Following a prompt-driven design review, the architecture was refactored to address four high-priority weaknesses identified in the implementation:

1. Perception was classifying query intent anew on every iteration rather than once at the start — causing inconsistency and wasted LLM calls
2. Decision had no query-type awareness or per-query answer schema, so the LLM emitted generic `answer: {}` instead of typed, grounded fields
3. The decision prompt lacked explicit heuristics, iteration budget visibility, and a grounding enforcement rule
4. Memory writes were implicit side-effects rather than a first-class decision action visible to the LLM

### Architecture shift

The previous architecture was **goal-based**: Perception decomposed the query into 2–4 sub-goals and ran every iteration to update done-flags. Decision selected the next tool call or answer per goal.

The new architecture is **state-based**: Perception classifies the query once, Decision uses a growing scratchpad of past iterations, and the final-answer schema is selected per query type.

| Aspect | Before (goal-based) | After (state-based) |
|---|---|---|
| Perception runs | Every iteration | Once at start |
| Perception output | `Observation(goals=[...])` | `PerceptionOutput` (typed classification) |
| Decision input | Current goal + memory hits + attached artifacts | `AgentState` (perception + scratchpad + memory_facts + iteration) |
| Decision output | `DecisionOutput(answer or tool_call)` | `CallToolDecision | WriteMemoryDecision | FinalAnswerDecision` |
| Memory write | Implicit (memory.remember at start + after tool results) | Explicit `WRITE_MEMORY` action decided by LLM |
| Answer schema | Generic text | Per-query typed Pydantic model |
| Iteration tracking | `HistoryEntry` list | `ScratchpadEntry` list (6 000-char excerpt per iter) |
| Tool dispatch | Single `action.execute(session, ToolCall)` | Three-branch `execute(decision, mcp, store)` |

### `schema.py` — complete rewrite

Removed: `HistoryEntry`, `Goal`, `Observation`, `ToolCall`, `ToolDef`, old `ActionResult`, `MemoryItem`, `Artifact`.

Added:

| Contract | Description |
|---|---|
| `QueryType` | Literal enum: `fact_lookup / synthesis / memory_write / memory_recall` |
| `ExpectedAnswerSchema` | Literal enum naming the target final-answer model |
| `PerceptionOutput` | user_query, intent, entities, query_type, expected_answer_schema, memory_relevant |
| `MemoryRecord` | id, kind (fact/episode), content, created_at, source |
| `MemoryStore` | facts[], episodes[] |
| `BiographyAnswer` | Query A — birth_date, death_date, contributions[], source_url |
| `ActivityRecommendation` | Query B — activities[], weather_summary, recommendation, reasoning |
| `MemoryWriteAck` | Query C1 — written_id, note |
| `BirthdayRecallAnswer` | Query C2 — birthday, note |
| `AsyncioBestPractices` | Query D — tips[], sources[] |
| `ANSWER_MODELS` | `dict[str, type[BaseModel]]` for runtime lookup |
| `CallToolDecision` | action="CALL_TOOL", tool_name, tool_args, reasoning |
| `WriteMemoryDecision` | action="WRITE_MEMORY", record, reasoning |
| `FinalAnswerDecision` | action="FINAL_ANSWER", answer (dict), reasoning |
| `DecisionOutput` | Discriminated union of the three decision types |
| `RawDecision` | Flat wire format (no oneOf) — what the LLM actually emits |
| `ActionResult` | action_type, success, data, error |
| `ScratchpadEntry` | iteration, decision_action, decision_summary, result_success, result_excerpt |
| `AgentState` | perception, scratchpad[], memory_facts[], iteration, max_iters |

### `memory.py` — complete rewrite

Replaced `Memory` class (with LLM-based extraction, keyword search, relevance scoring) with simple file-backed functions:

| Function | Description |
|---|---|
| `load_memory()` | Read `state/memory.json`; return empty store if missing/corrupt |
| `save_memory(store)` | Atomic write via `.tmp` + `os.replace()` |
| `append_fact(store, record)` | Dedup-by-id so re-runs overwrite rather than accumulate |
| `append_episode(store, record)` | Append-only audit trail |
| `wipe_memory()` | Delete the file |
| `render_facts_for_prompt(store)` | Format facts for Perception / Decision prompts |
| `python memory.py [show\|facts\|wipe]` | CLI for development inspection |

### `perception.py` — complete rewrite

Single `perceive(user_query, memory)` function. One LLM call at run start. Returns `PerceptionOutput`. System prompt has five worked examples mapping the current project's queries to their schemas. `temperature=0.0` (classification is deterministic).

### `decision.py` — complete rewrite

`decide(state: AgentState)` function. Key additions:

- **`_build_per_query_raw_decision(answer_model)`** — constructs a `RawDecision`-style model with `answer` typed as the specific per-query model. This forces the LLM to emit populated fields (e.g. `contributions: [...]`) instead of `answer: {}`.
- **14 heuristics** in system prompt: direct-URL shortcut, memory-first for `memory_recall`, `WRITE_MEMORY` first for `memory_write`, grounding rule (values must appear verbatim in scratchpad), commit rule, near-cap rule, fix empty tool_args, never invent URLs, cite/prove signal, etc.
- **Iteration budget**: prompt shows `"You are on iteration {n} of {max_iters}"`.
- **Belt-and-braces validation**: after LLM responds with `FINAL_ANSWER`, the answer dict is re-validated against the per-query Pydantic model; a failure raises `ValueError` so the loop records it as a failed iteration and retries.
- `temperature=1.0`, `max_tokens=3000`.

### `action.py` — complete rewrite

`MCPClient` class (was in `mcp_client.py`) embedded directly. Sets `PYTHONIOENCODING=utf-8` for the subprocess env on Windows. Three-branch `execute()`:

- `CallToolDecision` → `mcp.call_tool()`, surface errors as `success=False`
- `WriteMemoryDecision` → `append_fact(store, record); save_memory(store)`
- `FinalAnswerDecision` → wrap `decision.answer` in `ActionResult(action_type="FINAL_ANSWER", ...)`

### `agent6.py` — complete rewrite

`run_agent(query, max_iters=10)` function. Key behaviours:

- `SCRATCHPAD_RESULT_CHARS = 6000` — how much of each tool result is kept for the next Decision call
- Up to 3 consecutive `decide()` failures before giving up (gives the LLM a chance to correct its own bad emissions)
- After a successful `WRITE_MEMORY`, immediately reflects the new fact into `state.memory_facts` so the next Decision iteration sees it
- On `FINAL_ANSWER`: re-validates answer against the typed model, prints formatted JSON, returns exit code 0
- On iteration cap: prints warning, returns exit code 1

### `run_agent.py` — updated

Entry point updated to call `run_agent()` (from the new `agent6.py`) and return its exit code.

---

## Phase 7 — fetch_url Hang Fix + SSL Certificate Fix

### Problem: fetch_url hung on static pages

`fetch_url` called crawl4ai (headless Chromium) unconditionally for every URL. Pages like `discuss.python.org/t/asyncio-best-practices/12576` are static HTML — the browser waits for JS signals that never come and the call hangs indefinitely.

### Underlying blocker: SSL certificate verification failure

Before httpx could be used as a faster alternative, all httpx requests (both sync and async) failed with:

```
httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED]
certificate verify failed: unable to get local issuer certificate
```

**Root cause:** The network uses a corporate TLS inspection proxy whose CA certificate is trusted by the Windows system certificate store but is not present in `certifi`'s bundled CA store, which is what httpx uses by default.

### Fix 1 — `truststore` (Windows system CA store)

Installed `truststore` and called `truststore.inject_into_ssl()` once at module load in `mcp_server.py`. This patches Python's `ssl` module to load CAs from the Windows certificate store, making all subsequent httpx connections (and `currency_convert`'s sync httpx client) trust the corporate proxy CA.

```python
import truststore
truststore.inject_into_ssl()   # patches ssl module at startup
```

Added `"truststore>=0.10"` to `pyproject.toml` dependencies.

### Fix 2 — httpx-first with crawl4ai fallback

Added two helpers to `mcp_server.py`:

**`_html_to_text(html)`** — stdlib `html.parser`-based HTML stripper. Preserves block-level line breaks, drops `<script>`/`<style>`, collapses inline whitespace. No extra dependencies.

**`_httpx_fetch(url, timeout)`** — async httpx with `User-Agent` header and the `timeout` parameter actually honoured (the crawl4ai path previously ignored `timeout`).

Updated `fetch_url` tool:

```
Before:  always → _crawl4ai_fetch (headless browser, hangs on static pages)
After:   try _httpx_fetch first (returns in <1 s for static pages)
         → on failure, fall back to _crawl4ai_fetch (JS-rendered pages)
         → if crawl4ai also fails, re-raise the original httpx error
```

This means static pages (Wikipedia, Python docs, discuss.python.org, PyPI) are fetched almost instantly. The headless browser is only spun up for sites that genuinely require JavaScript execution.

---

## Phase 8 — Query D Schema Fix and Loop Robustness

### Root cause: schema underspecification (Query D early convergence)

Query D (`AsyncioBestPractices`) converged in 2 iterations instead of the expected ~5. After a single `web_search` call, the LLM could ground both `tips` (from search snippets) and `sources` (from search result URLs), satisfying the commit rule without fetching any full pages.

**Fix — `pages_read` field (Option 1 of two identified):**

Added `pages_read: list[str]` (`min_length=3`) to `AsyncioBestPractices` in `schema.py`. Field description specifies a 3-step workflow: (1) get URLs from `web_search`, (2) call `fetch_url` on each, (3) record the fetched URLs here. This field can only be grounded from `fetch_url` scratchpad entries, forcing at least 3 `fetch_url` iterations before the commit rule can fire.

### Secondary bug: repeated web_search loop after 2 fetch_url calls

After the schema fix, a new failure appeared: after 2 successful `fetch_url` calls the LLM fell into a loop repeating the same `web_search` query on iterations 5–10, hitting the cap.

**Three-layer fix:**

| Layer | Change |
|---|---|
| `schema.py` | Rewrote `pages_read` description with explicit 3-step workflow; removed the ambiguous "Do NOT populate from web_search snippet URLs" phrase |
| `decision.py` | Replaced vague "fetch multiple sources" bullet with an explicit **SYNTHESIS WORKFLOW** (search once → fetch each URL → FINAL_ANSWER after ≥ 3 fetch_url calls). Added **DUPLICATE-CALL GUARD** heuristic. Added `_scratchpad_dedup_key()` helper; `_render_scratchpad()` now appends `⚠ DUPLICATE — identical to iteration N` after any repeated OK CALL_TOOL entry |
| `agent6.py` | Added `_call_dedup_key()` (keys `web_search` by query, `fetch_url` by URL) and `successful_calls: set[str]`. When a repeated call is attempted, guard blocks `execute()` and injects a `DUPLICATE BLOCKED` ERR entry with explicit recovery instruction: "call fetch_url on the next unvisited URL, or emit FINAL_ANSWER if ≥ 3 fetch_url entries exist" |

### `router.py` — anthropic added to fallback ring

`DEFAULT_ROUTER_ORDER` in `llm_gateway/router.py` extended with `"anthropic"` as the last fallback provider for router LLM calls.

### Result of third run (current state)

The dedup guard correctly blocks repeated `web_search` calls (iterations 4–9 each show `DUPLICATE BLOCKED`). The near-cap rule at iteration 9 fires, and iteration 10 emits `FINAL_ANSWER` — the run exits 0 and the answer validates as `AsyncioBestPractices`.

**Remaining weakness:** the LLM does not pivot from "blocked web_search" to "fetch the 3rd unvisited URL". It keeps choosing `web_search` until the near-cap forces `FINAL_ANSWER`. The 3rd entry in `pages_read` (`shanechang.com`) is taken from the search result snippets — it was never actually fetched — violating the grounding rule. The run succeeds but for the wrong reason.

**Next step:** inject the 3rd unvisited URL explicitly into the scratchpad error message (`DUPLICATE BLOCKED: fetch 'https://...' next`) so the LLM has an immediately actionable URL to pick.

---

## Files Superseded (kept for reference)

| File | Superseded by |
|---|---|
| `mcp_client.py` | `MCPClient` class in `action.py` |
| `artifact_store.py` | Not used in new architecture |
| `utils.py` | `_summarize_*` helpers in `agent6.py` |

---

## Current State

All six core modules (`schema.py`, `memory.py`, `perception.py`, `decision.py`, `action.py`, `agent6.py`) import cleanly under `uv run python`. The architecture fully complies with the assignment's Pydantic contract requirement and `uv` execution requirement.

Queries A, B, C1, C2 converge correctly. Query D exits 0 and validates, but uses the near-cap escape rather than proactively fetching the 3rd source — a grounding weakness.

**Pending:**
- Strengthen the Query D recovery path: when a `web_search` duplicate is blocked, surface the specific next unvisited URL in the error message so Decision has a concrete `fetch_url` target
- Record YouTube demo
