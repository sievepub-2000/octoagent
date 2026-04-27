# Path Examples

This document records common path patterns used across OctopusAgent.

## Common path families

### Thread data

- `backend/.octopusagent/threads/{thread_id}/...`

### User-data virtual mount

- `/mnt/user-data/uploads/...`
- `/mnt/user-data/workspace/...`
- `/mnt/user-data/outputs/...`

### Artifact routes

- `/api/threads/{thread_id}/artifacts/...`

## Guidance

When documenting or implementing path handling, always distinguish between:

- actual host filesystem paths
- sandbox-visible virtual paths
- front-end HTTP artifact paths
