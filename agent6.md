Five observations.
First, the very first thing the loop does after starting is call memory.remember(query, ...). This is the durable-memory contract. When a user types "My mom's birthday is 15 May 2026," the query carries a fact that should survive into future runs. The classification call extracts that fact and persists it. Subsequent runs find it via the keyword search.

Second, the loop reads memory at the top of every iteration. Memory is consulted as a service.

Third, Perception is given the prior_goals list along with the new memory hits and the history. This is what gives goals stable identity across iterations.

Fourth, attachment of artifact bytes is gated on artifacts.exists(...). If Perception emits an attachment handle that does not correspond to a real artifact (a hallucination), the loop silently drops it. The defence is in addition to the position-based artifact_index scheme that prevents most hallucinations at the Perception layer.

Fifth, when Decision returns an answer, the loop appends an answer event to history and continues. Perception, on the next iteration, sees the answer in history and decides whether it satisfies the current goal. Marking goals done is a Perception responsibility. Decision selects actions; it does not declare goals satisfied.