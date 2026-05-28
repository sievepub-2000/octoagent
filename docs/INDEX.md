# OctoAgent Documentation Index

This index is the single entry point for the project's documentation.
The project carries two documentation trees, each with a different
purpose:

| Tree | Audience | What lives there |
| --- | --- | --- |
| [`docs/`](./) | Operators, integrators, end users | How to install, run, deploy, configure, and use OctoAgent. |
| [`project_docs/`](../project_docs/) | Contributors, reviewers, auditors | Architecture decisions, refactor history, governance rationale, internal audits. |

If you are not sure where to start, follow the path that matches your
goal below.

## I want to …

### Use OctoAgent (operator / end user)

* **Get started** — [`README.md`](../README.md) (root). Quick-start,
  Docker compose, environment matrix.
* **Docker install and deployment** — [`docs/docker-install.md`](./docker-install.md).
  Linux, Windows, and macOS Docker profile, packaging, and verification.
* **Japanese quick guide** — [`docs/ja/README.md`](./ja/README.md).
  Project overview, installation, usage, and verification in Japanese.
* **Configure runtime** — [`docs/CONFIGURATION.md`](./CONFIGURATION.md)
  if present, otherwise [`config.example.yaml`](../config.example.yaml).
  Note: the active `config.yaml` now lives under
  [`runtime/config/`](../runtime/config/) (since 2026-05-27).
* **Deploy to production** —
  [`docs/DEPLOYMENT.md`](./DEPLOYMENT.md),
  [`deploy/`](../deploy/).
* **Licensing & commercial use** —
  [`docs/COMMERCIAL_LICENSE_FAQ.md`](./COMMERCIAL_LICENSE_FAQ.md),
  [`LICENSE`](../LICENSE), [`NOTICE.md`](../NOTICE.md).

### Contribute to OctoAgent

* **Contributor workflow & branch policy** —
  [`CONTRIBUTING.md`](../CONTRIBUTING.md). Notably: §5 mandates
  **no-squash** merges into `main` since 2026-05-27.
* **Module ownership map** —
  [`docs/MODULE_OWNERS.md`](./MODULE_OWNERS.md). Read this before
  proposing a domain merge or rename.
* **Architecture overview** —
  [`project_docs/ARCHITECTURE.md`](../project_docs/ARCHITECTURE.md) if
  present, plus the inventory under
  [`project_docs/`](../project_docs/).
* **Topology freeze rules** —
  [`.importlinter`](../.importlinter),
  [`scripts/check_topology_freeze.py`](../scripts/check_topology_freeze.py).

### Audit OctoAgent (security / governance reviewer)

* **Governance domain index** —
  [`backend/src/governance/`](../backend/src/governance/) plus
  [`docs/GOVERNANCE.md`](./GOVERNANCE.md) if present.
* **Audit log scheme** —
  [`backend/src/governance/audit/`](../backend/src/governance/audit/).
* **License compliance** —
  [`docs/COMMERCIAL_LICENSE_FAQ.md`](./COMMERCIAL_LICENSE_FAQ.md),
  [`NOTICE.md`](../NOTICE.md).
* **Change history** —
  [`CHANGELOG.md`](../CHANGELOG.md).

## Index policy

* Both `docs/` and `project_docs/` continue as separate trees — they
  serve different audiences and the split is intentional.
* New documents go into the tree matching their audience (operator vs
  contributor). Add a link from this index in the same PR.
* If a document moves between trees, leave a one-line stub at the old
  path pointing to the new location for at least one release.

Last reviewed: 2026-05-28.
