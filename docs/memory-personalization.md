# Long-Term Memory And Personalization

## Goal

OctoAgent should become more accurate as a user keeps using it without turning
every message into permanent profile data. Durable preferences, corrections,
environment facts, and working conventions must be retained; transient tasks,
secrets, guesses, and rediscoverable output must not be promoted automatically.

## Hermes Agent Comparison

The comparison target is NousResearch Hermes Agent. Its official memory guide
documents two compact editable files under `~/.hermes/memories`: `MEMORY.md`
for agent notes and `USER.md` for the user profile. A frozen snapshot is
injected once at session start, preserving prompt-prefix stability. The agent
can add, replace, and remove entries; duplicate text is rejected, content is
kept within fixed character budgets, and injected memory is scanned for prompt
injection and exfiltration patterns.

Hermes also keeps exact conversation messages in SQLite with FTS5 search and
runs an optional post-turn learning review. That separates two concerns:
compact always-visible preferences versus searchable historical evidence.
Memory writes can require approval, and external memory providers can coexist
with the built-in store.

Official references:

- [Hermes Agent memory guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
- [Hermes Agent memory source documentation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/memory.md)
- [Hermes Agent repository](https://github.com/nousresearch/hermes-agent)

## OctoAgent's Current Architecture

OctoAgent already has a broader three-layer design:

1. Structured profile memory (`memory.json`) stores work context, personal
   context, top-of-mind items, history, and facts.
2. Global operator memory stores explicit system-wide instructions.
3. Semantic system memory stores summarized/vectorized material for retrieval.

The lead-agent prompt receives the structured profile, and the memory
middleware performs asynchronous post-turn updates. This is stronger than a
single note file for typed data and semantic recall, but the previous fast-turn
filter could skip short corrections. Preference-specific configuration also
existed without affecting injection order, and exact duplicate facts could be
re-added.

## Implemented Personalization Policy

The runtime now treats explicit durable signals—such as “remember”, “from now
on”, “always”, “never”, `记住`, `纠正`, `以后`, `不要`, and `必须`—as mandatory
memory-review candidates even on fast direct-answer routes.

The update prompt now enforces these rules:

- Prefer user corrections and durable instructions over inferred details.
- Learn user facts only from user-authored messages.
- Replace or remove contradicted facts instead of accumulating both versions.
- Normalize and reject exact duplicate structured facts.
- Rank preference facts into a dedicated `User Preferences` prompt section,
  bounded by `max_preference_facts`, before generic facts.
- When the compact profile reaches its fact budget, retain durable preferences
  and user context before generic historical detail; break ties by confidence
  and then recency so corrected information displaces stale information.

This produces the intended loop:

```text
user correction/preference
  -> asynchronous evidence review
  -> deduplicated structured profile
  -> preference-first prompt injection
  -> more precise future execution
```

## Operational Boundaries

The system must not silently store API keys, passwords, one-time task content,
or unsupported personal inferences. Global memory remains operator-controlled.
Semantic recall complements the compact profile but does not override explicit
current instructions. When current instructions conflict with stored memory,
the current request wins and the contradiction is submitted for profile
replacement.

Exact raw-message full-text search and per-write approval are useful Hermes
patterns, but they should be introduced as separate audited capabilities rather
than coupled to the profile updater. OctoAgent's PostgreSQL checkpoints already
preserve conversation state; exposing cross-session raw search requires an
explicit retention/privacy policy and a user-visible delete/export lifecycle.
