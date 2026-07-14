# Projects

Projects are persistent execution contexts, not workflow containers. A project owns one validated working directory and the defaults applied to Agent runs started from that project.

## What the WebUI entry is for

The left-side **Projects** entry is the place to create and maintain durable
work contexts. It is useful when several conversations should operate on the
same repository or document tree with the same rules, model preference, and
permission ceiling. It does not create an automated workflow and it does not
run anything by itself.

A typical user flow is:

1. Open **Projects**, choose **New project**, and provide a display name plus an
   existing server-side working directory.
2. Add project instructions such as build commands, coding conventions,
   protected paths, output requirements, or review rules.
3. Optionally choose a default model, set the maximum permission mode, record a
   compact project memory summary, and pin frequently relevant file paths.
4. Use **New task** from the project detail page. The resulting conversation is
   bound to the project and inherits its effective context.
5. Return to the project page to reopen all conversations associated with that
   project, inspect their update times, or change the defaults for future runs.

Examples include keeping all maintenance tasks for one code repository under a
single context, separating client workspaces with different safety rules, or
giving research tasks a stable corpus directory and persistent research notes.

Creating a project does not clone a Git repository or create the directory. The
path must already exist on the OctoAgent server. Archiving hides the project
from the active list and prevents new runs, while preserving its existing
conversation references.

## Effective context

The backend is the source of truth. Clients submit only `project_id` plus explicit per-run choices. Before the Agent is built, the backend resolves:

- project root path;
- project instructions and memory summary;
- pinned file references;
- model selection, using per-run choice, then project default, then system default;
- permission mode, using the lower of the requested mode and the project ceiling.

The resolved root becomes `/mnt/user-data/workspace`. Thread uploads and outputs remain in their thread-specific directories. `project_id` is stored in `ThreadState`, so project task grouping remains stable after reload and restart.

Changing project defaults affects subsequent runs. Explicit choices made for a
run still participate in backend resolution: a per-run model can override the
project default, but a per-run permission request can never exceed the project
ceiling.

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
