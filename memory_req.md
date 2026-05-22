Memory as a typed service
Memory in the Session 6 architecture is a service. Other roles invoke its read and write methods. The service sits beside the loop as an external store and is called when the loop or another role needs to consult it.

The V2 cohort's Memory layer was a list of strings with a recall(query) method that sent the entire list plus the query to an LLM. That implementation could not afford an LLM call per read and could not return more than one item at a time. Session 6's Memory implementation lifts both constraints. Reads are pure keyword search. Writes are typed.

Kinds. Memory items carry a kind discriminator with four legal values.

Kind	Carries	Example
fact	A durable observed truth.	"John's office is HSR Layout, Bangalore."
preference	A user-stated or inferred preference.	"User prefers morning meetings."
tool_outcome	The record of one MCP dispatch.	"fetch_url(https://...) → artifact art:09ff..."
scratchpad	A run-scoped working note.	Intermediate planner state during the current run.
The four kinds map onto the three-tier memory system that Session 7 introduces. The fact items become the Factual layer, the preference items become the REMME layer, and the tool_outcome items become the Episodic layer. The scratchpad is run-scoped and does not migrate. Session 6 keeps all four kinds in a single JSON file. Session 7 replaces the storage backend while preserving the read and write interfaces.

Reads. Three read methods cover the cases that arise in S6. Their cost profiles differ.

Method	What it does	LLM cost
memory.read(query, history, kinds=None, top_k=8)	Keyword overlap across keywords plus tokens of descriptor. Returns ranked top-k.	None. Pure Python.
memory.filter(kinds=..., goal_id=..., recent=N)	Structured filter by kind, goal, recency.	None.
memory.relevant(query, kinds=..., top_k=5)	LLM-scored relevance over a kind-filtered candidate pool. Used only when keyword recall is weak.	One gateway call routed auto_route="memory".
The keyword search uses a small stopword list and a simple lowercase-token intersection. It scales to hundreds of items and stays fast enough to run before every Perception call. The implementation is short. We should be able to read it and understand the algorithm.

Writes. Two write methods cover the cases. Their cost profiles differ in the same way.

Method	When	LLM cost
memory.remember(raw_text, source, run_id, goal_id)	Free-form ambiguous content (user input, observed statement).	One classification call (auto_route="memory", pinned to Gemini). Returns a typed item with kind, keywords, descriptor, and structured value extracted by the LLM.
memory.record_outcome(tool_call, result_text, artifact_id, ...)	An MCP dispatch returned a result.	None. Kind is tool_outcome by construction; keywords come from tool name and argument tokens.
The asymmetry matters. The LLM call at write time is what makes future reads cheap. When a user says "John's birthday is 15 May 2026," the classifier extracts the kind (fact), the canonical structure ({"entity": "John", "attribute": "birthday", "value": "2026-05-15"}), and a keyword list (["John", "birthday", "May", "2026"]). The keyword search at read time then finds this item with no LLM call. The Session 7 expansion will replace keyword search with hybrid retrieval (BM25 plus vector plus reciprocal rank fusion); the interface that Memory.read exposes to other layers does not change.

Persistence. All items live in a single JSON file at state/memory.json. The agent6 loop loads on first read and writes back after every mutation. Across runs, the same JSON file is reused, so preferences and facts persist. Clearing the file resets the agent.