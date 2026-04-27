# Workflow Graph Redesign — Architecture Analysis

## Status: Design Phase (P2)

## Current Architecture

OctoAgent's workflow system spans 3 modules:

| Module | Lines | Role |
|--------|-------|------|
| `workflow_core/` | ~2000 | Core contracts, runtime, builder transactions, service facade |
| `task_workspaces/` | ~2600 | Execution engine, planner, message executor, store |
| `studio_runtime/` | ~800 | Builder UI, visual editor contracts |

### Current Execution Flow
```
TaskWorkspace → WorkflowCoreService → runtime.safe_auto_execute_workspace()
    → TaskWorkspaceExecutionController.auto_execute_workspace()
        → TaskWorkspaceMessageExecutor.execute()
            → invoke_agent_runtime() → LangGraph
```

### Strengths
- Builder-transaction based workspace editing (atomic, undoable)
- LangGraph-only runtime truth with legacy provider compatibility normalization
- Card-graph model for flexible task decomposition
- Inflight task deduplication

### Limitations
- No visual graph editor (studio_runtime is contract-only)
- Linear execution (no parallel node execution)
- No conditional branching at graph level
- No loop/retry primitives in the execution graph

---

## Reference Architecture Analysis

### 1. OpenHarness Pattern
**Approach**: Pipeline-as-graph with typed edges
- Nodes are typed processors (transform, filter, aggregate)
- Edges carry typed data contracts
- Execution engine validates edge compatibility before running
- Built-in retry/skip/fallback per node

**Applicable Ideas**:
- Typed edge contracts between card-graph nodes
- Per-node retry policy (already partially in execution.py)
- Validation phase before execution dispatch

### 2. OpenAkita Pattern
**Approach**: Event-driven workflow with state machines
- Each node is a state machine (idle → running → completed/failed)
- Transitions trigger downstream nodes
- Supports parallel execution with join/barrier nodes
- Event bus for cross-workflow communication

**Applicable Ideas**:
- State machine for each AgentHandle (maps to existing status field)
- Join/barrier for parallel agent execution in "group" mode
- Event bus already exists (HookCore)

### 3. LangGraph-Oriented Agent Runtime Pattern
**Approach**: agent orchestration remains task-scoped, but runtime execution is centralized on LangGraph.

**Applicable Ideas**:
- Preserve handoff/session semantics through `agent_core`
- Keep guardrails on agent transitions (skill constraints)
- `TaskWorkspaceExecutionController` remains the task-scoped runner façade over LangGraph execution

---

## Proposed Redesign: Hybrid Graph Model

### Phase 1: Typed Card-Graph Edges (Low Risk)
Add edge contracts to the existing card-graph model:

```python
class CardGraphEdge(BaseModel):
    source_card_id: str
    target_card_id: str
    edge_type: Literal["dependency", "handoff", "data_flow", "conditional"]
    condition: str | None = None  # For conditional edges
    retry_policy: RetryPolicy | None = None
```

### Phase 2: Parallel Execution Support
Extend `auto_execute_workspace()` to detect independent nodes and run them concurrently using `asyncio.gather()`.

### Phase 3: Visual Graph Editor Contracts
Extend `studio_runtime` with node position, edge routing, and viewport contracts for a future React Flow-based editor.

---

## Implementation Priority
1. **Edge contracts** — Add to `task_workspaces/contracts.py` (1 day)
2. **Parallel detection** — Add to `execution.py` (2 days)
3. **Visual contracts** — Extend `studio_runtime` (1 day, contracts only)
4. **React Flow integration** — Frontend work (future sprint)
