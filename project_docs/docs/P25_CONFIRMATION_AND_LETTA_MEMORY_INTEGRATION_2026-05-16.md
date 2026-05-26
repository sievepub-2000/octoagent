# P25 Confirmation And Letta Memory Integration (2026-05-16)

## Scope

This pass changes the OctoAgent capability model from "dangerous host abilities
are unavailable" to "dangerous host abilities are available behind explicit user
confirmation", and imports Letta's memory architecture into the existing
OctoAgent memory system.

## Dangerous Capability Policy

System-level tools are now allowed as first-class built-ins, but their metadata
marks them as confirmation-gated:

- `host_shell`
- `host_file_manage`
- `tcp_connect`
- `http_transfer`
- `python_package_install`
- `process_manage`
- `codex_cli`

`DangerousToolConfirmationMiddleware` intercepts those tools before execution.
If the latest user turn has not explicitly approved the requested operation, the
middleware emits an `ask_clarification` tool message and ends the current run.
The user can reply with an approval phrase such as "确认", "同意", "继续", or
"approve"; the model can then call the same capability again and the middleware
allows that confirmed operation.

This preserves operator control without permanently blocking system-level work.

## Letta-Inspired Memory Integration

The implementation is based on two Letta concepts:

- **core memory blocks**: always-visible structured memory sections with labels,
  descriptions, values, limits, and optional read-only status
- **archival memory**: semantically searchable long-term memory, retrieved on
  demand rather than always injected into the prompt

OctoAgent maps these to existing stores:

- core memory blocks live under `memory_blocks` in the existing `memory.json`
  schema and are injected by `format_memory_for_injection`
- archival memory is a new `archival_memory` namespace in the existing
  DuckDB-backed `system_rag_store`

No Letta sidecar service is required. OctoAgent keeps one memory stack and uses
Letta's stronger abstractions inside that stack.

## New Memory Tools

- `memory_block_upsert`: create or replace a core memory block
- `memory_block_list`: list current core memory blocks
- `archival_memory_insert`: store a durable archival memory fact
- `archival_memory_search`: retrieve archival memory by meaning

Read-only memory blocks cannot be overwritten unless internal code explicitly
uses an override path.

## Verification

- `tests/agents/test_dangerous_tool_confirmation_middleware.py`
- `tests/memory/test_letta_memory.py`
- full backend Ruff and pytest baseline

Validation result:

- `ruff format . --check`
- `ruff check .`
- `pytest -q -rs`
- `165 passed`

## Notes

Letta reference material used for this design:

- Letta memory blocks/core memory: https://docs.letta.com/guides/core-concepts/memory/memory-blocks
- Letta archival memory: https://docs.letta.com/guides/agents/archival-memory
- Letta memory overview: https://docs.letta.com/guides/agents/memory

