# ADR 0001: One manifest seam for managed tools and artifacts

Status: accepted — 2026-07-15

## Decision

Standalone operator-installed tools live only at
`runtime/system_tools/<tool>/`. `manifest.json` is the authoritative lifecycle
record shared by installation, Tools Hub listing, invocation guidance, and
uninstallation. Generated files use the sibling `artifacts/` directory.

Bundled application capabilities remain Skills and locked backend dependencies;
they are not copied into a second plugin registry. Conversation deliverables
remain under the current thread's `outputs/` directory.

## Consequences

- A directory without a valid matching manifest is never removed by the managed
  tool uninstaller.
- Install/uninstall tools are visible only in system permission mode and still
  require explicit confirmation in their invocation contract.
- Tools Hub lists lazy built-ins and managed tools from their live sources.
- One artifact-governance policy replaces divergent cleanup shell scripts.
- Retention defaults cover temporary files, tool artifacts, and runtime logs;
  user outputs and durable runtime state are protected.
