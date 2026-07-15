# OctoAgent Engineering Constraints

## Full-system audit acceptance criteria

A task described as a full, complete, or system-wide inspection is not complete until all applicable checks below have executable evidence:

1. Resolve the runtime source of truth from the live process environment, effective configuration, working directory, mounts, and service definition. Do not infer it from repository defaults.
2. Search for duplicate data roots, databases, configuration snapshots, caches, registries, and legacy workspaces. Compare ownership, permissions, timestamps, record counts, and the path actually opened by the running process.
3. Run checks as the production service identity as well as the administrative identity. Verify every writable runtime path is owned and writable by the production identity without broad world-write permissions.
4. Exercise the complete supported lifecycle of every mutable user-facing module: create/install, read/list, update/enable/disable, delete/uninstall, cache refresh, restart, and persistence after restart. Read-only and action-only modules must have their documented operations tested instead of fabricated CRUD claims.
5. Verify authorization at the server-side execution seam with real tools and every permission level. A visible UI control or unit test alone is insufficient.
6. Validate installation from a clean checkout and empty data volumes. Test first start, health convergence, restart, persisted state, upgrade, stop, and removal/rollback paths.
7. For cross-platform claims, run platform-native syntax/static tests for Windows PowerShell and POSIX shell, validate Docker Compose rendering, and execute the same container profile on at least one real Docker engine. Document any host-specific capability limitations.
8. Treat warnings, fallback backends, silent exception handlers, unexpected empty registries, root-owned runtime files, and multiple active data sources as failures until explained and regression-tested.
9. Preserve operator data and secrets. Use isolated temporary records for mutation tests and remove them after verification. Back up persistent stores before migrations.
10. Reports must distinguish verified facts, inferred conclusions, platform-only checks, and residual risks. Never use “all normal”, “fully working”, or equivalent language without the evidence above.

## Implementation defaults

- Read the live code and existing tests before editing.
- Prefer existing repository modules and standard platform features over new dependencies.
- Keep changes scoped, use `apply_patch` for source edits, and never discard unrelated worktree changes.
- Add the smallest regression test that exercises the real failing seam.
- Use `rg` for repository searches and non-interactive commands for automation.
