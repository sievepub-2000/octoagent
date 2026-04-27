# Brain Core

## Purpose

Brain Core is the structured planning and execution-contract layer that sits between raw user intent and real runtime execution.

It is designed to answer:

- what kind of workflow this task needs
- what evidence or constraints are missing
- what execution contract should gate the next step
- how multiple reasoning paths should be fused without hidden conflicts

## Code Map

- `backend/src/brain/contracts.py`
  Shared task, plan, analysis, decision, contract, and response schemas.
- `backend/src/brain/planner.py`
  Builds workflow plans and strategy-fusion graphs.
- `backend/src/brain/strategy_graph.py`
  Validates execution-order, causal-order, and arbitration guardrails.
- `backend/src/brain/service.py`
  Main facade that coordinates registered modules and policy output.
- `backend/src/brain/modules.py`
  Registry and descriptor surface for Brain analysis modules.
- `backend/src/brain/research.py`
  Baseline goal, evidence, and constraint framing.
- `backend/src/brain/evidence.py`
  Evidence sufficiency and routing readiness.
- `backend/src/brain/memory_reasoner.py`
  Memory-hint shaping for plan context.
- `backend/src/brain/quant.py`
  Quant scope and bounded execution readiness.
- `backend/src/brain/policy.py`
  Conservative recommendation layer.
- `backend/src/brain/execution_contracts.py`
  Converts analysis + decision into explicit workflow/runtime contracts.

## Runtime Surface

### API

- `POST /api/brain/plan`
  Returns the structured Brain response used by the workspace orchestrator.
- `GET /api/brain/capabilities`
  Returns the registered Brain modules and the current execution-backend surface.

### Frontend

- `frontend/src/core/brain/*`
  Client types, API, and hooks.
- `frontend/src/core/workflows/types.ts`
  `buildBrainPlanPayload(workflow)` adapts orchestrator state into Brain Core input.
- `frontend/src/components/workspace/orchestrator/workflow-builder.tsx`
  Displays execution-contract and missing-input guidance.
- `frontend/src/components/workspace/orchestrator/workflow-graph.tsx`
  Visualizes validated Brain strategy graphs.

## Current Behavior

Brain Core now runs as a module pipeline:

1. planner builds plan and graph
2. registered modules produce analysis slices
3. analysis slices are merged into a single view
4. policy produces a recommendation
5. execution-contract builder emits a runtime-safe contract

The current registered modules are:

- `research`
- `evidence_router`
- `memory_reasoner`
- `quant`

## What “Completed” Means Here

Brain Core is now complete enough to serve as:

- a stable planning facade
- a workflow recommendation engine
- an execution-readiness contract generator
- a graph-based strategy-fusion validator

It is **not** yet complete as:

- a direct execution engine
- a real backtest runner
- a live strategy allocator
- a policy enforcement daemon

That distinction matters. Brain Core currently decides and contracts. It does not yet execute the domain action itself.

## Next Extension Points

Recommended next modules:

1. `causal_reasoner`
2. `backtest_orchestrator`
3. `policy_gate_runtime`
4. `execution_adapter`

Those should be added through the same registry pattern rather than hard-wiring more logic into `BrainCoreService`.
