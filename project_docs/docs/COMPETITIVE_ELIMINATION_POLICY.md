# Competitive Elimination Policy

## Purpose

Define strict discard rules so that OctoAgent only keeps changes that improve functional completeness or performance without weakening reliability.

## Comparison Standard

This policy uses the repository's existing competitor framing around OpenAkita and Hermes and treats repository-local proof as mandatory before any superiority claim is allowed.

## Elimination Rules

| Rule ID | Eliminate the slice if... | Threshold |
| --- | --- | --- |
| E-001 | Overall scorecard regresses | total_score decreases from previous verified baseline |
| E-002 | Release safety regresses | release_gate != pass |
| E-003 | Real operator path regresses | make smoke-real fails on 19880 |
| E-004 | Runtime truth regresses | M-002 decreases or introduces a second workflow truth source |
| E-005 | Governance regresses | capability governance score decreases or the unification suite fails |
| E-006 | Performance regresses | runtime latency benchmark p95 worsens by more than 20% without functional gain justification |
| E-007 | Functional completeness regresses | any previously verified lifecycle path or governed surface disappears |
| E-008 | Evidence quality regresses | superiority claim has no repository-local proof source |

## Keep Rules

A slice is eligible to keep only if all of the following are true:

1. No elimination rule is triggered.
2. At least one quantified target improves or one blocking gap is removed.
3. The change does not widen the blast radius beyond the declared module scope.

## Superior Module Standard

For a module to be recorded as better than its counterpart in a similar project, OctoAgent must show:

1. At least equivalent functional surface.
2. Equal or lower measured latency on the same class of path.
3. Stronger governed verification within this repository.

## Current Assessment Against The Policy

- Reliability rules E-001 through E-003 currently pass on the verified 96-point baseline.
- Governance proof now reaches the 14-point target after adding the behavioral governance depth suite.
- Functional superiority can be claimed only for dimensions already backed by the scorecard, competitive matrix, and imported peer-source extracts; a blanket product-wide superiority claim is still not justified.