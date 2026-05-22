"""
Tests for fetch_url MCP tool — verifies the fix for the crawl4ai stdout
corruption bug (fd-level redirect via os.dup/os.dup2).

Run:  uv run pytest tests/test_fetch_url.py -v
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── helpers ──────────────────────────────────────────────────────────────────

async def _call(tool_name: str, args: dict) -> dict:
    """Open a fresh MCPClient, call one tool, return the result."""
    from action import MCPClient
    async with MCPClient() as mcp:
        return await mcp.call_tool(tool_name, args)


# ── fetch_url via httpx (static page) ────────────────────────────────────────

def test_fetch_url_wikipedia():
    """fetch_url returns 200 and non-empty text for a static Wikipedia page."""
    result = asyncio.run(
        _call("fetch_url", {"url": "https://en.wikipedia.org/wiki/Claude_Shannon"})
    )
    assert result["status"] == 200
    assert result["length_bytes"] > 0
    assert "Shannon" in result["text"]


def test_fetch_url_pypi():
    """fetch_url works for PyPI (another static HTTPS page)."""
    result = asyncio.run(
        _call("fetch_url", {"url": "https://pypi.org/project/httpx/"})
    )
    assert result["status"] == 200
    assert result["length_bytes"] > 0


# ── fetch_url does not corrupt the MCP stdio stream ──────────────────────────

def test_fetch_url_followed_by_second_call():
    """Two sequential fetch_url calls succeed — stream is not corrupted between them."""
    async def _two_calls():
        from action import MCPClient
        async with MCPClient() as mcp:
            r1 = await mcp.call_tool(
                "fetch_url", {"url": "https://en.wikipedia.org/wiki/Claude_Shannon"}
            )
            r2 = await mcp.call_tool(
                "fetch_url", {"url": "https://pypi.org/project/httpx/"}
            )
            return r1, r2

    r1, r2 = asyncio.run(_two_calls())
    assert r1["status"] == 200
    assert r2["status"] == 200


# ── web_search still works after fetch_url ────────────────────────────────────

def test_web_search_after_fetch_url():
    """MCP session stays healthy after a fetch_url call."""
    async def _mixed():
        from action import MCPClient
        async with MCPClient() as mcp:
            await mcp.call_tool(
                "fetch_url", {"url": "https://en.wikipedia.org/wiki/Claude_Shannon"}
            )
            return await mcp.call_tool("web_search", {"query": "Claude Shannon information theory", "max_results": 2})

    results = asyncio.run(_mixed())
    assert isinstance(results, list)
    assert len(results) >= 1
