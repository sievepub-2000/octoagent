---
name: tokenspeed-benchmark
description: TokenSpeed benchmark planning skill for LLM inference experiments.
license: MIT
---
# tokenspeed-benchmark

Define model, hardware, prompts, batch/concurrency, latency, throughput, correctness checks, and baseline comparison before installing engines.

## OctoAgent usage

1. Confirm the user goal and constraints.
2. Load any matching plugin command with `get_plugin_command`.
3. Run `integrated_workflow_run` when a workflow ID is available.
4. Produce artifacts and review them against the quality gates before side effects.
