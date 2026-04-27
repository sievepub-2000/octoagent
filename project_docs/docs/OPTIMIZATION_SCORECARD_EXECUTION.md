# Optimization Scorecard Execution

## Purpose

This document defines the only valid way to execute the optimization scorecard against the local OctoAgent stack.

## Metric Command

Use the scorecard script as the primary metric command:

```bash
backend/.venv/bin/python backend/scripts/run_optimization_scorecard.py --format json
```

## Release Precheck Command

Use the release precheck as the companion governance command for deploy and runtime readiness:

```bash
backend/.venv/bin/python backend/scripts/run_release_precheck.py
```

## Verification Semantics

The scorecard includes three gates:

1. Backend critical regression tests
2. Frontend build
3. Live WebUI smoke against the unified 19880 entrypoint

The release precheck expands this into a release-oriented sequence:

1. Backend compileall
2. Backend ruff lint
3. Backend critical regression subset
4. Frontend dependency lock verification
5. Frontend lint
6. Frontend build
7. Live WebUI smoke against the unified 19880 entrypoint

## Frontend Build Isolation

The frontend build gate must not overwrite the live `.next` directory used by the production daemon stack.

Use an isolated build output:

```bash
env NEXT_DIST_DIR=.next-scorecard pnpm -C frontend build
```

This preserves the running 19880 WebUI while still proving that the current frontend source compiles successfully.

## Baseline Interpretation

- `baseline_total` is the declared static program baseline.
- `total_score` is the real measured score from the current workspace.
- `baseline_aligned` is only true when the measured total equals the declared baseline.

## Governance Closure Rule

- Do not claim scorecard governance closure if `metrics.M-006` is null or missing.
- Do not claim backend critical gate closure if the scorecard backend regression suite fails, even if a narrower release precheck subset still passes.
- Do not claim release readiness unless both the scorecard gates and the release precheck command pass on the same workspace state.

## Acceptance Rule

No optimization experiment may be kept unless all required verification commands pass, the measured score does not regress, and the scorecard plus release precheck remain mutually consistent.
