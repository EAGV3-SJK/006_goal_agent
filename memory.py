"""
memory.py — File-backed durable memory for the agent.

State lives in state/memory.json. The store has two sections:
  - facts:    durable user facts, loaded into Perception's context on every run.
  - episodes: per-run audit trail, never shown to the LLM.

Query C proves cross-process durability: run 1 calls append_fact() and exits;
run 2 starts a brand-new Python process, calls load_memory(), and reads it back.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Final

from schema import MemoryRecord, MemoryStore


MEMORY_PATH: Final[Path] = Path(__file__).parent / "state" / "memory.json"


def load_memory() -> MemoryStore:
    """Read state/memory.json, or return an empty store if missing/corrupt."""
    if not MEMORY_PATH.exists():
        return MemoryStore()
    try:
        raw = MEMORY_PATH.read_text(encoding="utf-8")
        return MemoryStore.model_validate_json(raw)
    except (json.JSONDecodeError, ValueError):
        return MemoryStore()


def save_memory(store: MemoryStore) -> None:
    """Atomically write the store via .tmp + os.replace so a mid-write kill
    cannot corrupt the file."""
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MEMORY_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(store.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp_path, MEMORY_PATH)


def append_fact(store: MemoryStore, record: MemoryRecord) -> MemoryStore:
    """Add or replace a fact in place (dedup by id).

    Re-running Query C1 overwrites the existing fact rather than accumulating
    duplicates. Returns the same store for fluent chaining."""
    if record.kind != "fact":
        raise ValueError(f"append_fact got kind={record.kind!r}, expected 'fact'.")
    store.facts = [f for f in store.facts if f.id != record.id]
    store.facts.append(record)
    return store


def append_episode(store: MemoryStore, record: MemoryRecord) -> MemoryStore:
    """Append an episode (audit-only). Not deduplicated."""
    if record.kind != "episode":
        raise ValueError(f"append_episode got kind={record.kind!r}, expected 'episode'.")
    store.episodes.append(record)
    return store


def wipe_memory() -> None:
    """Delete state/memory.json. Used between assignment attempts for a clean slate."""
    if MEMORY_PATH.exists():
        MEMORY_PATH.unlink()


def render_facts_for_prompt(store: MemoryStore) -> str:
    """Format the facts section for inclusion in Perception / Decision prompts."""
    if not store.facts:
        return "(none)"
    lines: list[str] = []
    for f in store.facts:
        lines.append(f"- {f.id}: {json.dumps(f.content, sort_keys=True)}")
    return "\n".join(lines)


def _cli() -> int:
    args = sys.argv[1:]
    if not args or args[0] in {"show", "dump"}:
        print(load_memory().model_dump_json(indent=2))
        return 0
    if args[0] == "wipe":
        wipe_memory()
        print(f"Wiped {MEMORY_PATH}")
        return 0
    if args[0] == "facts":
        print(render_facts_for_prompt(load_memory()))
        return 0
    print("usage: python memory.py [show|facts|wipe]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
