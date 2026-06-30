---
name: semgrep:scan
description: Run Semgrep security scans before or during security-sensitive coding work, especially changes involving auth, secrets, network access, shell execution, file handling, deserialization, dependencies, or CI/CD workflows.
---

# Semgrep Scan

Use this skill when a task needs security scanning or when code changes touch risky surfaces such as authentication, authorization, secrets, subprocesses, network calls, file uploads, parsers, serialization, dependency manifests, or deployment scripts.

## Workflow

1. Identify the smallest useful scan target. Prefer the changed package or repository root over unrelated system directories.
2. Ensure the report directory exists under runtime output, not source code:

```bash
mkdir -p runtime/reports
```

3. Prefer an existing `semgrep` binary:

```bash
semgrep scan --config auto --error --json --output runtime/reports/semgrep-scan.json <target>
```

4. If `semgrep` is not installed, use a temporary runner and do not create a repository-local virtual environment:

```bash
uvx semgrep scan --config auto --error --json --output runtime/reports/semgrep-scan.json <target>
```

5. For focused scans, add relevant rulesets:

```bash
semgrep scan   --config p/owasp-top-ten   --config p/secrets   --config p/python   --error   --json   --output runtime/reports/semgrep-scan.json   <target>
```

## Result Handling

After the scan, read the JSON report and summarize:

- command and target
- report path
- total findings
- finding count by severity
- high or critical findings that must block completion
- ignored or accepted findings, with rationale

If Semgrep cannot run because neither `semgrep` nor `uvx` is available, report that explicitly and fall back to a manual review of the changed files. Do not claim automated security scanning succeeded.

## Guardrails

- Do not scan secrets from outside the workspace unless explicitly requested.
- Do not upload source code to a remote service for scanning.
- Do not install Semgrep into random virtual environments in the repository.
- Keep generated reports under `runtime/reports/`.
- Treat high and critical findings as blockers unless the user explicitly accepts the risk.
