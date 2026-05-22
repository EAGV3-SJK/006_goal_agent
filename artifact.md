When a tool produces a payload larger than a few kilobytes, the bytes are written to a separate content-addressable store. Memory holds only the handle.

The distinction is load-bearing. A typical fetched web page is 100 KB or more (though lesser after the cleanup that we have already applied). If those bytes lived inside MemoryItem.value, every subsequent Memory.read would either return them (bloating Decision's context window) or excerpt them (forcing the loop to maintain a second piece of state about which excerpt to use). The artifact store sidesteps the choice by holding the bytes separately and giving Memory a handle.

class ArtifactStore:
    def put(self, blob: bytes, *,
            content_type: str, source: str, descriptor: str) -> str: ...
    def get_bytes(self, artifact_id: str) -> bytes: ...
    def get_meta(self, artifact_id: str) -> Artifact: ...
    def exists(self, artifact_id: str) -> bool: ...
Handles are short strings of the form art:<sha256-prefix>. Storage is two files per artifact under state/artifacts/: a .bin with the raw bytes and a .json with the metadata. The store is content-addressable; identical fetches deduplicate. The store has no eviction policy in S6.

The architectural boundary around artifacts is strict.

            ┌──────────────────────────────────────────────────────┐
            │                                                      │
  Memory ◄──┤ holds the handle string ("art:abc...") inside        │
            │ MemoryItem.artifact_id                               │
            │                                                      │
  Perception ◄ sees the handle in MEMORY HITS, never the bytes     │
            │                                                      │
  Decision ◄  sees the bytes only when Perception attaches them    │
            │ to the prompt for the current goal                   │
            │                                                      │
  Action  ◄── produces bytes (writes them via ArtifactStore.put)   │
            │                                                      │
            └──────────────────────────────────────────────────────┘
The boundary is enforced by the agent6 loop. Perception's output includes an optional attach_artifact_id field on each goal. When the next unfinished goal carries such a field, the loop calls ArtifactStore.get_bytes(...) and passes the result into Decision's prompt under an ATTACHED ARTIFACTS: section. Decision sees the section as part of its context window. The reason this matters is cost: a Decision call against a 4 KB context costs a fraction of one against a 200 KB context, and Decision should only pay the larger cost when the work it is doing on this turn requires the bytes.