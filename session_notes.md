# Session Notes — goal-agent (EAGV3 Session 6)

Date: 2026-05-23

---

## Project Overview

Four-layer goal-directed AI agent for EAGV3 Session 6 assignment.

**Working directory:** `D:\sjk\eagv3\006_session`
**Python:** `C:\apps\python313\python.exe` (3.13.5) — uv's managed 3.12.11 has a broken ssl build on this machine.

---

## Architecture

| File | Role |
|---|---|
| `schema.py` | Pydantic v2 contracts: MemoryItem, Artifact, Goal, Observation, ToolCall, DecisionOutput |
| `memory.py` | Durable store → `state/memory.json`; LLM-classified writes, keyword-overlap reads |
| `perception.py` | Decomposes query into 2–4 goals (first run); updates done flags each iteration |
| `decision.py` | Selects next tool call or produces final answer |
| `action.py` | Executes MCP tool calls; auto-stores fetch_url results as artifacts |
| `agent6.py` | Main loop (max 12 iterations), wires all four layers |
| `mcp_server.py` | MCP stdio server — 9 tools |
| `mcp_client.py` | Starts mcp_server.py as subprocess; exposes mcp_session() async context |
| `artifact_store.py` | Content-addressable store under `state/artifacts/` |
| `run_agent.py` | CLI entry point: `python run_agent.py A/B/C1/C2/D` |
| `llm_gateway/` | LLM Gateway V3 — FastAPI server on port 8101 |

---

## How to Run

**Terminal 1 — LLM Gateway (must be running first):**
```powershell
cd D:\sjk\eagv3\006_session\llm_gateway
uv run uvicorn main:app --port 8101
```

**Terminal 2 — Agent queries:**
```powershell
cd D:\sjk\eagv3\006_session

uv run python run_agent.py A     # Claude Shannon Wikipedia
uv run python run_agent.py B     # Tokyo activities + weather
uv run python run_agent.py C1    # Store mom's birthday
uv run python run_agent.py C2    # Recall mom's birthday
uv run python run_agent.py D     # asyncio best practices
```

**Clean state between runs:**
```powershell
Remove-Item -Recurse -Force D:\sjk\eagv3\006_session\state
```

> The MCP server (`mcp_server.py`) starts and stops automatically — never run it manually.

---

## Issues Found and Fixed This Session

### 1. Project rename
- `pyproject.toml` name changed from `eagv3-session6` → `goal-agent`

### 2. Files created
- `.gitignore` — excludes `state/`, `.venv/`, `__pycache__/`, `.env`, `usage.json`, `llm_gateway/*.db`, `sandbox/`
- `README.md` — setup, run instructions, architecture, prompt documentation

### 3. venv rebuild — wrong Python
- uv's managed CPython 3.12.11 has a broken ssl build on this machine (`ssl.create_default_context()` crashes with `OPENSSL_Uplink: no OPENSSL_Applink`)
- Fix: rebuilt venv using system Python 3.13.5 at `C:\apps\python313\python.exe`
```powershell
uv venv --python "C:\apps\python313\python.exe"
uv sync --native-tls
```

### 4. aiohttp 3.13.5 OpenSSL conflict
- `aiohttp 3.13.5` ships a Windows DLL with an incompatible OpenSSL build → crashes on import
- Fix: downgrade to `aiohttp==3.9.5`
```powershell
uv pip install "aiohttp==3.9.5" --native-tls
```

### 5. crawl4ai / Rich LegacyWindowsTerm crash (`mcp_server.py`)
- **Root cause:** On Windows, Rich detects a legacy console and uses `LegacyWindowsTerm` (Win32 `WriteConsoleW` API). This bypasses fd-level redirects and crashes with `UnicodeEncodeError` on non-ASCII characters (arrows `→`, `↓`, etc.) that crawl4ai logs emit.
- **Old fix (broken):** fd-level redirect of stdout to `os.devnull` — doesn't intercept Win32 console API calls.
- **New fix:** Give crawl4ai a silent `AsyncLogger` whose Rich `Console` writes to `io.StringIO()` (in-memory buffer) — no Win32 API involved, no encoding issues.

```python
# mcp_server.py — _crawl4ai_fetch()
import io
import rich.console as _rc
from crawl4ai.async_logger import AsyncLogger

silent = AsyncLogger(verbose=False)
silent.console = _rc.Console(file=io.StringIO(), quiet=True)

async with AsyncWebCrawler(logger=silent) as crawler:
    r = await crawler.arun(url=url)
```

---

## Current State

| Query | Status |
|---|---|
| A — Claude Shannon Wikipedia | Passed in previous session (4 iterations) |
| C1 — Store mom's birthday | Passed in previous session (5 iterations) |
| C2 — Recall mom's birthday | Passed in previous session (2 iterations) |
| B — Tokyo activities + weather | Not yet run with fixed stack |
| D — asyncio best practices | Not yet run with fixed stack |

**Next steps:**
1. Verify `fetch_url` MCP tool works end-to-end (in-progress background test)
2. Run clean Query A to capture terminal output for README
3. Run Queries B and D
4. Capture all four query outputs and paste into README
5. Record YouTube demo

---

## Key Architecture Decisions

### Five loop invariants (agent6.py)
1. **Durable-memory** — `memory.remember(query)` called before loop; persists facts across runs
2. **Consultation** — `memory.read(query, history)` at top of every iteration
3. **Goal stability** — `prior_goals` threaded through every `perception.observe()` call; IDs never change
4. **Silent defense** — artifact attachment gated on `artifacts.exists(id)` before loading bytes
5. **Goal separation** — only Perception marks goals done; Decision only produces tool calls or answers

### Perception provider cascade
Gemini (native structured output) → Anthropic (prompted JSON, no response_format) → auto_route

### Decision routing
- Content > 32 KB → `provider="g"` (bypasses HUGE guard, Gemini 1M token context)
- Content ≤ 32 KB → `auto_route="decision"`
- 503 error → retry with Gemini + tighter 20K truncation

### Force-attach safety net
If first unfinished goal contains a synthesis keyword (`extract`, `summarize`, `recommend`, etc.) and an artifact is available but the LLM didn't attach one, Perception auto-attaches the most recent artifact to prevent re-fetch loops.
