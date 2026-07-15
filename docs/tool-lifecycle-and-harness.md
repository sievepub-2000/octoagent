# Tool lifecycle and artifact harness

## Resolution order

For each specialized task, OctoAgent must query Tools Hub first. It tries
installed candidates in least-privilege order until one produces a verified
result. Only when no registered capability is suitable may it research an
established GitHub project and propose a pinned tag or branch, source URL,
commands, permissions, and target directory for approval.

## Permissions and lifecycle

| Operation | Tool | Required mode | Additional gate |
| --- | --- | --- | --- |
| List | `managed_tool_list` | approval/directory/system | none |
| Call | `managed_tool_execute` | system | registered safe entrypoint only |
| Install Python package | `python_package_install` | system | explicit confirmation |
| Install GitHub tool | `github_tool_install` | system | explicit source/ref/command confirmation |
| Uninstall | `managed_tool_uninstall` | system | exact-name confirmation and valid manifest |

Successful installs create `manifest.json`, `artifacts/`, `cache/`, and `logs/`
under `runtime/system_tools/<name>/`. Tools Hub and the generated agent guide
read that manifest immediately. Successful uninstall removes only that
manifest-owned directory and performs a post-delete visibility check.

Ad-hoc installation into the backend environment, a user site, the source tree,
or an unrelated virtual environment is forbidden. Bundled application features
are instead declared in `backend/pyproject.toml` and locked in `uv.lock`.

## Office generation

The bundled `office-generation` Skill creates real DOCX, XLSX, PPTX, PDF, and
Markdown files. It uses `python-docx`, `openpyxl`, `python-pptx`, ReportLab, and
the standard library. Its output must be written to the current thread's
`outputs/` directory, which is the source used by the right-side Files panel and
artifact download API.

## Artifact ownership and retention

The canonical implementation is `backend/src/harness/artifact_governance.py`.
The generic maintenance agent and all three compatibility cleanup scripts call
the same policy.

Default automatic retention:

- `tmp/`: 1 day;
- `runtime/system_tools/*/artifacts/`: 30 days;
- `runtime/logs/`: 14 days.

Environment variables `OCTO_ARTIFACT_TMP_DAYS`, `OCTO_ARTIFACT_TOOL_DAYS`, and
`OCTO_ARTIFACT_LOG_DAYS` override these values. Managed tool source,
environments, manifests, cache and tool-owned logs; runtime configuration and
secrets; databases, memories, checkpoints; and all user thread outputs are
protected. Use `artifact_governance_status` to inspect the policy and
`artifact_cleanup` in dry-run mode before an explicitly confirmed apply.
