"""
schema.py — Pydantic contracts for the Session 6 agent.

Every boundary between the four cognitive layers (Perception, Memory, Decision,
Action) is validated by one of the models defined here. No layer ever passes a
free-form dict to another layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# ════════════════════════════════════════════════════════════════════════════
#  1. PERCEPTION — what Perception hands to Decision after reading the query
# ════════════════════════════════════════════════════════════════════════════

QueryType = Literal[
    "fact_lookup",    # Query A — one web fetch + extraction
    "synthesis",      # Queries B, D — multi-source research
    "memory_write",   # Query C1 — store a durable user fact
    "memory_recall",  # Query C2 — use a previously stored fact
]

ExpectedAnswerSchema = Literal[
    "BiographyAnswer",
    "ActivityRecommendation",
    "MemoryWriteAck",
    "BirthdayRecallAnswer",
    "AsyncioBestPractices",
]


class PerceptionOutput(BaseModel):
    """One-shot reading of the user's request. Produced once at the start of a run."""

    user_query: str = Field(..., description="The original raw user input, verbatim.")
    intent: str = Field(..., description="One-line plain-English restatement of what the user wants.")
    entities: list[str] = Field(
        default_factory=list,
        description="Named things mentioned in the query (people, places, libraries, versions, …).",
    )
    query_type: QueryType
    expected_answer_schema: ExpectedAnswerSchema
    memory_relevant: bool = Field(
        ...,
        description="True if Perception spotted facts in memory that should inform the answer.",
    )


# ════════════════════════════════════════════════════════════════════════════
#  2. MEMORY — the notebook on disk (state/memory.json)
# ════════════════════════════════════════════════════════════════════════════

class MemoryRecord(BaseModel):
    """One entry in the notebook."""

    id: str = Field(..., description="Short unique key, e.g. 'moms_birthday'.")
    kind: Literal["fact", "episode"] = Field(
        ...,
        description="'fact' is loaded into context on every run; 'episode' is for audit only.",
    )
    content: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(default="agent_inference")


class MemoryStore(BaseModel):
    """The full notebook. Serialises to one file: state/memory.json."""

    facts: list[MemoryRecord] = Field(default_factory=list)
    episodes: list[MemoryRecord] = Field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════
#  3. FINAL-ANSWER MODELS — one per query type
# ════════════════════════════════════════════════════════════════════════════

class BiographyAnswer(BaseModel):
    """Query A — Claude Shannon biography: birth date, death date, contributions."""
    birth_date: str = Field(..., description="e.g. 'April 30, 1916'")
    death_date: str = Field(..., description="e.g. 'February 24, 2001'")
    contributions: list[str] = Field(
        ...,
        description="Three key contributions to information theory.",
        min_length=3,
    )
    source_url: str


class ActivityRecommendation(BaseModel):
    """Query B — Tokyo family activities + weather recommendation."""
    activities: list[str] = Field(
        ...,
        description="Three family-friendly activities in Tokyo.",
        min_length=3,
    )
    weather_summary: str = Field(..., description="Saturday weather forecast for Tokyo.")
    recommendation: str = Field(..., description="The most appropriate activity given the weather.")
    reasoning: str = Field(..., description="One sentence explaining why this activity fits the weather.")


class MemoryWriteAck(BaseModel):
    """Query C1 — acknowledgement that a durable fact was stored."""
    written_id: str = Field(..., description="The id of the MemoryRecord that was persisted.")
    note: str = Field(..., description="Short human-readable confirmation, including reminder dates.")


class BirthdayRecallAnswer(BaseModel):
    """Query C2 — recall mom's birthday from durable memory."""
    birthday: str = Field(..., description="The stored birthday date, e.g. '15 May 2026'")
    note: str = Field(..., description="A brief human-readable note about the birthday.")


class AsyncioBestPractices(BaseModel):
    """Query D — agreed asyncio best practices synthesised from multiple sources."""
    tips: list[str] = Field(
        ...,
        description="Numbered list of agreed best practices (at least 3).",
        min_length=3,
    )
    pages_read: list[str] = Field(
        ...,
        description=(
            "URLs of pages fully fetched via the fetch_url tool during this run. "
            "Workflow: (1) web_search returns candidate URLs, "
            "(2) call fetch_url on each candidate — one per iteration, "
            "(3) record each fetched URL here. "
            "Each entry must match the `url` arg of a successful fetch_url call "
            "in the scratchpad. Requires at least 3 fetch_url successes."
        ),
        min_length=3,
    )
    sources: list[str] = Field(default_factory=list, description="URLs consulted.", min_length=1)


# Lookup table: agent6.py uses perception.expected_answer_schema to pick the
# right model for post-parse validation of FinalAnswerDecision.answer.
ANSWER_MODELS: dict[str, type[BaseModel]] = {
    "BiographyAnswer":        BiographyAnswer,
    "ActivityRecommendation": ActivityRecommendation,
    "MemoryWriteAck":         MemoryWriteAck,
    "BirthdayRecallAnswer":   BirthdayRecallAnswer,
    "AsyncioBestPractices":   AsyncioBestPractices,
}


# ════════════════════════════════════════════════════════════════════════════
#  4. DECISION — exactly one of three branches per iteration
# ════════════════════════════════════════════════════════════════════════════

class CallToolDecision(BaseModel):
    """'Pick up the phone and call a tool.'"""
    action: Literal["CALL_TOOL"]
    tool_name: str = Field(..., description="MCP tool, e.g. 'web_search' or 'fetch_url'.")
    tool_args: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = Field(..., description="Why this call, in one sentence.")


class WriteMemoryDecision(BaseModel):
    """'Write a durable fact in the notebook.'"""
    action: Literal["WRITE_MEMORY"]
    record: MemoryRecord
    reasoning: str


class FinalAnswerDecision(BaseModel):
    """'I'm done. Here is the final answer.'"""
    action: Literal["FINAL_ANSWER"]
    answer: dict[str, Any]
    reasoning: str


# Discriminated union used internally for typed dispatch (isinstance checks
# in action.py / agent6.py). NOT sent directly to the LLM — use RawDecision
# for the wire format instead.
DecisionOutput = Annotated[
    Union[CallToolDecision, WriteMemoryDecision, FinalAnswerDecision],
    Field(discriminator="action"),
]


class RawDecision(BaseModel):
    """Flat decision shape used at the LLM-wire boundary.

    Every branch-specific field is optional so the JSON Schema we send the
    provider is plain OpenAPI 3.0 (no oneOf, no discriminator). Decision.py
    validates which fields are actually required given the action value, then
    constructs the correct concrete class."""
    action: Literal["CALL_TOOL", "WRITE_MEMORY", "FINAL_ANSWER"]
    reasoning: str
    # CALL_TOOL fields
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    # WRITE_MEMORY fields
    record: MemoryRecord | None = None
    # FINAL_ANSWER fields
    answer: dict[str, Any] | None = None


# ════════════════════════════════════════════════════════════════════════════
#  5. ACTION — the result of doing what Decision said
# ════════════════════════════════════════════════════════════════════════════

class ActionResult(BaseModel):
    action_type: Literal["CALL_TOOL", "WRITE_MEMORY", "FINAL_ANSWER"]
    success: bool
    data: Any = None
    error: str | None = None


# ════════════════════════════════════════════════════════════════════════════
#  6. AGENT STATE — what the loop carries between iterations
# ════════════════════════════════════════════════════════════════════════════

class ScratchpadEntry(BaseModel):
    """One row of 'what I have already tried this run'."""
    iteration: int
    decision_action: Literal["CALL_TOOL", "WRITE_MEMORY", "FINAL_ANSWER"]
    decision_summary: str = Field(..., description="Short text rendering of the decision.")
    result_success: bool
    result_excerpt: str = Field(default="", description="Truncated result, prompt-safe.")


class AgentState(BaseModel):
    """In-memory snapshot during one run. Not persisted to disk."""
    perception: PerceptionOutput
    scratchpad: list[ScratchpadEntry] = Field(default_factory=list)
    memory_facts: list[MemoryRecord] = Field(default_factory=list)
    iteration: int = Field(default=1)
    max_iters: int = Field(default=10)
