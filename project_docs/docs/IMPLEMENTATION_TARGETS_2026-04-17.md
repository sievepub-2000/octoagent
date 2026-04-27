# Quantified Implementation Targets 2026-04-17

## Objective

Translate the remaining OctoAgent work into measurable engineering targets that can be consumed by bounded autoresearch slices.

## Global Targets

| Metric | Current verified value | Target value | Measurement source |
| --- | --- | --- | --- |
| M-001 overall scorecard | 96 | >= 95 | backend/scripts/run_optimization_scorecard.py --format json |
| M-002 runtime truth score | 19 | 19 | scorecard dimension output |
| M-003 governed capability score | 14 | 14 | scorecard dimension output |
| M-004 release gate | 100 | 100 | scorecard release_gate must stay pass |
| M-005 WebUI smoke | 100 | 100 | make smoke-real |
| M-006 runtime latency proof | present | present with rolling history | backend/scripts/run_runtime_latency_benchmark.py |
| M-007 workspace board complexity | 1812 | <= 1600 without feature loss | line count plus regression tests |
| M-008 frontend e2e coverage gap | one dedicated suite exists | >= 1 dedicated suite plus lifecycle assertions | frontend regression assets |

## Module Targets

| Module | Current condition | Target condition | Acceptance rule |
| --- | --- | --- | --- |
| task_workspaces execution | Shared controller exists, dedicated durability and recovery tests now exist | Sustain runtime truth at 19 without adding a second truth source | New suite passes, smoke stays green, and truth score stays at target |
| capability_core and hook_core | Governed surfaces exist, dedicated unification proof exists, and behavior-driven governance proof now exists | Sustain the full 14-point governance target without contract drift | New suite passes and governance score stays at target |
| gateway routers | Real smoke passes, some routes lack dedicated recovery proof | Recovery and registry contracts are pinned by tests | No route-level regression in scorecard or smoke |
| frontend workspace state | Build isolated, browser regression baseline now exists | Add lifecycle-aware workspace browser coverage beyond navigation | Frontend state score reaches target |
| optimization program docs | Core docs exist | Plan, targets, elimination policy, assessment stay aligned | Docs updated whenever scorecard truth changes |

## Superiority Targets

OctoAgent should outperform comparable systems only when all three conditions hold for a module:

1. Functional scope is equal or broader than the compared module.
2. The repository contains repeatable verification for the claim.
3. Runtime latency and regression safety are not worse than the current OctoAgent baseline.

## Autoresearch Slice Format

Every bounded slice should define:

- One primary scorecard metric to improve.
- One maximum blast radius measured by touched modules.
- One keep threshold and one discard threshold.
- One real verification command bundle.

## Keep And Discard Thresholds

- Keep a slice only if scorecard total does not decrease, release gate stays pass, and smoke remains green.
- Discard a slice if it introduces a red verification command, raises live WebUI instability, or increases runtime truth ambiguity.