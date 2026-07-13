# Projects

Projects are persistent execution contexts, not workflow containers. A project owns one validated working directory and the defaults applied to Agent runs started from that project.

## Effective context

The backend is the source of truth. Clients submit only `project_id` plus explicit per-run choices. Before the Agent is built, the backend resolves:

- project root path;
- project instructions and memory summary;
- pinned file references;
- model selection, using per-run choice, then project default, then system default;
- permission mode, using the lower of the requested mode and the project ceiling.

The resolved root becomes `/mnt/user-data/workspace`. Thread uploads and outputs remain in their thread-specific directories. `project_id` is stored in `ThreadState`, so project task grouping remains stable after reload and restart.

## Storage

Project definitions live in `workspace/projects/projects.sqlite3`. On first startup, an existing `workspace/projects/projects.json` is imported automatically when the database is empty. Runtime databases are ignored by Git.

Project memory is the `memory_summary` field in the same project record. The older separate project-memory JSON module and duplicate memory endpoints were removed.

## Lifecycle and safety

- Project roots must exist and resolve under `/home`, `/opt`, `/srv`, `/tmp`, or `/var/lib`.
- Archived projects cannot start new Agent runs.
- Projects are archived instead of hard-deleted so existing thread references are never orphaned.
- A project permission ceiling can restrict a run but cannot elevate client permissions.

## HTTP interface

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PUT /api/projects/{project_id}`
- `GET /api/projects/{project_id}/context`

The context endpoint returns the effective project defaults used by the Web UI status panel. Runtime model or permission overrides are still resolved again by the backend for each run.
