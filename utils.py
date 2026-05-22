"""
utils.py — Shared utility helpers for the Session 6 agent loop.

All functions here are pure / side-effect-free so they can be unit-tested
without starting the gateway or any MCP server.
"""
from __future__ import annotations

from schema import HistoryEntry


def final_answer_from(history: list[HistoryEntry]) -> str:
    """Return the text of the most-recent 'answer' entry in history."""
    for entry in reversed(history):
        if entry.kind == "answer":
            text = (entry.text or "").strip()
            if text:
                return text
    return "No answer produced"


def last_tool_result(history: list[HistoryEntry], tool_name: str | None = None) -> str | None:
    """Return the result_descriptor of the most-recent action entry."""
    for entry in reversed(history):
        if entry.kind != "action":
            continue
        if tool_name and entry.tool != tool_name:
            continue
        return entry.result_descriptor
    return None


def artifact_ids_from_history(history: list[HistoryEntry]) -> list[str]:
    """Return all artifact IDs produced by action entries, oldest-first."""
    return [e.artifact_id for e in history if e.kind == "action" and e.artifact_id]


def answer_events(history: list[HistoryEntry]) -> list[HistoryEntry]:
    """Return all answer entries from history in chronological order."""
    return [e for e in history if e.kind == "answer"]
