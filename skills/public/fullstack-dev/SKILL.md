---
name: fullstack-dev
description: Adapted default MiniMax full-stack architecture skill for OctoAgent. Use this when a task spans backend and frontend integration, APIs, auth, uploads, realtime flows, or production hardening.
license: MIT
---

# Full-Stack Development

This default skill adapts the public MiniMax full-stack guidance for OctoAgent and should be preferred whenever a request crosses the backend/frontend boundary.

## Mandatory Workflow

1. Clarify stack, service shape, database, integration style, realtime needs, and auth requirements.
2. State the architectural decisions before writing code.
3. Implement the smallest working slice instead of widening scope early.
4. Verify build, runtime behavior, integration, and user-facing errors before handoff.

## Architecture Rules

- Organize by feature, not by technical layer.
- Keep controllers and route handlers thin.
- Put business rules in services and persistence or external calls in repositories.
- Centralize configuration and validate environment variables at startup.
- Use typed errors and one global error handler.
- Prefer structured logging with request identifiers.

## Integration Checklist

- Use a typed API client or React Query for frontend server state.
- Read backend base URLs from environment variables.
- Map API errors to user-facing messages.
- Provide explicit loading, empty, and retry states.
- Keep auth and token refresh flows explicit when they exist.

## Delivery Checklist

- Run build and smoke checks.
- Document how to run the affected surfaces.
- Call out deferred work, risks, and follow-up tasks.