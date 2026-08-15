# ADR 0002: Integrate patterns, not runtimes

Status: accepted (2026-08-15)

## Context

DeepSeek Harness offers strong plugin lifecycle and tool-protocol contracts,
but its package/plugin surface is much larger than OctoAgent. Prime Agent
offers robust long-running sessions and provider message repair, but adds a
Node/Python daemon-worker topology, IPython kernels, and ZeroMQ. Deploying
either runtime inside OctoAgent would duplicate LangGraph, Harness, storage,
tool discovery, and process supervision.

## Decision

OctoAgent keeps two public modules: Agent Runtime and Harness. We borrow only
four small ideas: a canonical model/tool contract, adapter-owned execution
boundaries, fixed read-back probes for privileged execution, and artifact-
backed continuation. Existing LangGraph checkpoints, Markdown memory,
pgvector recall, and Harness dynamic scanning remain authoritative.

The root System Executor remains physically separate because it owns the
Docker socket. It is an adapter behind Harness, not another application module.
The WebUI may request a permission mode, but the server filters capabilities
and proves the selected boundary before execution.

## Consequences

- No second event bus, plugin framework, database, worker daemon, kernel, or
  JavaScript backend runtime.
- Provider compatibility remains centralized in the model semantic translator.
- MCP follows the latest official LangChain adapter's supported SDK range;
  OctoAgent will not carry a private MCP SDK fork merely to claim a version.
- Office and multimedia support reuse existing backend libraries and browser
  primitives, so the feature adds no production dependency.
