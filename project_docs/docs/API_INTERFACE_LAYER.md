# API Interface Layer

## Goal

The frontend previously had many module-local `fetch` implementations with inconsistent error handling, JSON parsing, and query-string construction.

The repository now has a shared HTTP interface layer:

- `frontend/src/core/api/http.ts`

## What It Provides

- shared backend URL construction
- query-string building
- consistent JSON request encoding
- consistent JSON response parsing
- consistent HTTP error extraction
- typed helpers for:
  - `getJSON`
  - `postJSON`
  - `putJSON`
  - `deleteJSON`
  - lower-level `apiRequest`

## Why It Matters

This is the start of a real cross-module interface layer for the frontend.

Without it:

- each module invents its own error shape
- multipart and JSON behavior drift apart
- future auth headers, tracing headers, retries, or request logging must be copied everywhere

With it:

- module APIs stay thin
- transport policy can evolve in one place
- all core modules can converge on the same contract surface

## Current Adoption

Refactored modules in this pass:

- `frontend/src/core/brain/api.ts`
- `frontend/src/core/bootstrap/api.ts`
- `frontend/src/core/memory/api.ts`
- `frontend/src/core/agents/api.ts`
- `frontend/src/core/mcp/api.ts`
- `frontend/src/core/models/api.ts`
- `frontend/src/core/runtime/api.ts`
- `frontend/src/core/skills/api.ts`
- `frontend/src/core/uploads/api.ts`

## Recommended Next Step

Keep transport concerns in `core/api`, and keep business semantics in feature modules.

Suggested structure:

1. `core/api/http.ts`
   raw request helpers
2. `core/api/errors.ts`
   normalized API error shapes
3. `core/api/query.ts`
   shared React Query key factories
4. feature modules under `core/*/api.ts`
   business-facing wrappers only

This preserves a clean split between transport, cache policy, and business modules.
