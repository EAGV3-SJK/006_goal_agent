"""MCP client utilities — starts mcp_server.py as a stdio subprocess."""
import os
import sys
import contextlib
from pathlib import Path

SERVER_SCRIPT = str(Path(__file__).parent / "mcp_server.py")


@contextlib.asynccontextmanager
async def mcp_session():
    """Start the MCP server and yield a ClientSession (None if unavailable)."""
    try:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client, StdioServerParameters
    except ImportError as e:
        print(f"[mcp_client] mcp library not installed: {e}")
        yield None
        return

    # Force UTF-8 I/O in the MCP server subprocess so the JSON-RPC stream
    # never hits cp1252 encoding errors on Windows.
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER_SCRIPT],
        env=env,
    )
    _started = False
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _started = True
                yield session          # body exceptions propagate from here
    except BaseException as e:
        if _started:
            raise                      # re-raise body errors; don't yield again
        # Setup failed before yield — yield None so the agent continues without tools
        print(f"[mcp_client] server failed to start: {e}; running without tools")
        yield None


async def load_tools(session) -> list:
    """Return the list of MCP Tool objects from the session."""
    if session is None:
        return []
    try:
        result = await session.list_tools()
        return list(result.tools) if result and result.tools else []
    except Exception as e:
        print(f"[mcp_client] list_tools error: {e}")
        return []


def mcp_tools_for_decision(mcp_tools: list) -> list:
    """Convert MCP Tool objects to gateway ToolDef dicts: {name, description, input_schema}."""
    out = []
    for t in mcp_tools:
        raw_schema = getattr(t, "inputSchema", None)
        if raw_schema is None:
            schema = {}
        elif hasattr(raw_schema, "model_dump"):
            schema = raw_schema.model_dump()
        elif isinstance(raw_schema, dict):
            schema = raw_schema
        else:
            schema = {}
        out.append({
            "name": t.name,
            "description": t.description or "",
            "input_schema": schema,
        })
    return out
