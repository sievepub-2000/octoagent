# Harness

Harness is OctoAgent's single execution and capability boundary. Agent Runtime
decides what to do; Harness discovers and invokes built-in, container, host,
MCP and browser capabilities under the selected permission mode.

It also owns durable memory. Every completed conversation is written to an
original transcript Markdown file and a compact Markdown memory file. The
derived pgvector index is rebuilt from those files at startup. Legacy JSON and
DuckDB memories are imported idempotently and retained as migration sources.

Active parts:

- `dispatcher/`: routes execution to the appropriate adapter/worker.
- `memory.py`: Markdown source of truth and pgvector retrieval.
- `hooks.py` and `hook_core/`: dynamically registered lifecycle hooks.
- `reflection/`: import/class resolution used by plugins and model providers.
- `budget.py`: model-turn and wall-clock limits.
- `artifact_governance.py`: runtime artifact retention and cleanup.

There is no separate Tools Hub, Brain, QueryEngine, TaskWorkspace planner,
generic maintenance agent, Redis event bus, or second memory writer.
