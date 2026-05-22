Perception: the orchestrator
Perception is the only role that maintains state across iterations. It runs every iteration. Each iteration, Perception receives four inputs: the user's original query, the current memory hits, the run history accumulated so far, and the prior goal list (the Observation it returned on the last iteration). Perception emits a fresh Observation containing the current goal list with done flags and optional artifact attachments.

def observe(
    query: str,
    hits: list[MemoryItem],
    history: list[dict],
    prior_goals: list[Goal],
    run_id: str,
) -> Observation: ...
The decomposition into goals happens the first time Perception runs (when prior_goals is empty). On every later iteration, Perception preserves the goal list shape and updates only the done flags and the attach_artifact_id on the next unfinished goal. This preserves identity across iterations: each goal occupies a stable position in the list, and the loop can refer to a goal by position without relying on the LLM to preserve identifiers.

The contract that Perception fulfills can be stated as four obligations.

1. If the prior goal list is empty, decompose the query into one or more
   bounded goals, each a short imperative statement.

2. For each prior goal, examine the run history. Mark the goal `done: true`
   the moment the history contains an action that satisfies it. Once done,
   the goal remains done in every subsequent iteration.

3. For the first unfinished goal in the list, decide whether it needs raw
   bytes from a previously fetched artifact. If yes, set the goal's
   attach_artifact_id to one of the artifact handles in MEMORY HITS.

4. Preserve goal order. Do not reorder, do not insert in the middle, do
   not drop a goal.
The implementation pins Perception to Gemini through the gateway's provider="g" field. The reason is observed empirically: when Perception is allowed to route through the gateway's normal TINY-tier worker (gpt-4.1-mini at the time of writing), the model is too small to reliably follow the procedure above. It hallucinates attachment ids, drops goals, and produces inconsistent identity across iterations. With Gemini selected explicitly, the procedure executes correctly across the four target queries.

Two structural choices in the prompt prevent hallucination from causing damage.

The first is positional identity. The Perception output schema does not include a goal id field. Goals are identified by their position in the output list. The outer loop carries the prior goal ids and maps them to the new positions. The model has no string field where it could invent a stale identifier.

The second is indexed artifact references. Memory hits are presented to Perception with an integer index i on each entry that carries an artifact. The model emits artifact_index: <int> rather than a string handle. The outer loop maps the integer back to the actual art:... handle. A model that wants to attach an artifact must point at one of the indices it actually sees.

Perception also subsumes the role that the structured-output Verifier played in Session 5. There is no separate Verifier call. When Perception re-reads the history at the start of each iteration, it observes whether the last action produced a result that satisfies the open goal, and it sets done: true accordingly. The reasoning that the Session 5 Verifier did inside a typed Verdict model is now done inside Perception's typed Observation model on every iteration.