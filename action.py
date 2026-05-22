"""
action.py — The Action layer.

Executes whatever Decision picked:
  CALL_TOOL    → invoke an MCP tool over stdio.
  WRITE_MEMORY → append fact via memory.py and persist the store.
  FINAL_ANSWER → wrap the answer dict in an ActionResult; agent6.py exits.

Owns the MCP server subprocess via the MCPClient async context manager.
A single subprocess is kept alive for the whole run — re-spawning per tool
call would mean restarting Python + MCP handshake on every iteration.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from memory import append_fact, save_memory
from schema import (
    ActionResult,
    CallToolDecision,
    DecisionOutput,
    FinalAnswerDecision,
    MemoryStore,
    WriteMemoryDecision,
)


MCP_SERVER_PATH = Path(__file__).parent / "mcp_server.py"


# ════════════════════════════════════════════════════════════════════════════
#  MCP stdio client — owns the subprocess and the JSON-RPC session
# ════════════════════════════════════════════════════════════════════════════

class MCPClient:
    """Single long-lived stdio connection to the MCP server.

    Usage:
        async with MCPClient() as mcp:
            result = await mcp.call_tool("web_search", {"query": "foo"})
    """

    def __init__(self, server_path: Path = MCP_SERVER_PATH):
        self.server_path = server_path
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None

    async def __aenter__(self) -> "MCPClient":
        self._stack = AsyncExitStack()
        # Force UTF-8 I/O in the subprocess so the JSON-RPC stream never hits
        # cp1252 encoding errors on Windows.
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(self.server_path)],
            env=env,
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(
            ClientSession(read, write)
        )
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self.session = None
        self._stack = None

    async def list_tools(self) -> list[str]:
        """Diagnostic — names of tools the server advertises."""
        if self.session is None:
            raise RuntimeError("MCPClient is not active.")
        result = await self.session.list_tools()
        return [t.name for t in result.tools]

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Call a tool and return its parsed result (dict, list, or str)."""
        if self.session is None:
            raise RuntimeError("MCPClient is not active; use inside `async with`.")
        result = await self.session.call_tool(name, args)

        # Surface server-side errors as Python exceptions so execute()
        # can wrap them into ActionResult(success=False).
        if getattr(result, "isError", False):
            msgs = [getattr(c, "text", str(c)) for c in (result.content or [])]
            raise RuntimeError(
                f"MCP tool {name!r} returned an error: {' | '.join(msgs) or 'unknown'}"
            )

        # FastMCP may emit one TextContent (json.dumps of the whole return value)
        # or multiple TextContent items (one per list element). Parse each part
        # independently — joining-then-parsing fails when multiple TextContents
        # each carry their own JSON object.
        parts: list[Any] = []
        for c in result.content or []:
            t = getattr(c, "text", None)
            if t is None:
                continue
            try:
                parts.append(json.loads(t))
            except json.JSONDecodeError:
                parts.append(t)
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return parts


# ════════════════════════════════════════════════════════════════════════════
#  Dispatcher — turn a Decision into an ActionResult
# ════════════════════════════════════════════════════════════════════════════

async def execute(
    decision: DecisionOutput,
    *,
    mcp: MCPClient,
    store: MemoryStore,
) -> ActionResult:
    """Execute one Decision. Always returns an ActionResult; never raises for
    tool errors — they are reported via success=False so Decision can see
    them on the next iteration's scratchpad."""

    if isinstance(decision, CallToolDecision):
        try:
            data = await mcp.call_tool(decision.tool_name, decision.tool_args)
            return ActionResult(
                action_type="CALL_TOOL",
                success=True,
                data=data,
            )
        except Exception as e:
            return ActionResult(
                action_type="CALL_TOOL",
                success=False,
                error=f"{type(e).__name__}: {e}",
            )

    if isinstance(decision, WriteMemoryDecision):
        try:
            append_fact(store, decision.record)
            save_memory(store)
            return ActionResult(
                action_type="WRITE_MEMORY",
                success=True,
                data={"written_id": decision.record.id},
            )
        except Exception as e:
            return ActionResult(
                action_type="WRITE_MEMORY",
                success=False,
                error=f"{type(e).__name__}: {e}",
            )

    if isinstance(decision, FinalAnswerDecision):
        return ActionResult(
            action_type="FINAL_ANSWER",
            success=True,
            data=decision.answer,
        )

    return ActionResult(
        action_type="CALL_TOOL",
        success=False,
        error=f"Unknown decision type: {type(decision).__name__}",
    )


if __name__ == "__main__":
    import asyncio

    async def _main() -> None:
        async with MCPClient() as mcp:
            tools = await mcp.list_tools()
            print("MCP tools advertised by server:")
            for t in tools:
                print(f"  - {t}")

    asyncio.run(_main())
