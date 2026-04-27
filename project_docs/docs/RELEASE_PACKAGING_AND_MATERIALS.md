# Release Packaging And Materials

This document defines the current packaging surface and release-material checklist for OctoAgent.

## Current Packaging Reality

OctoAgent currently ships in two practical forms:

1. Repository/web stack release
2. Desktop shell release

The desktop app is a thin Electron shell around the shared WebUI. It does not bundle LangGraph, the gateway API, or the frontend build output into one offline desktop binary.

## 1. Repository/Web Stack Release

This is still the primary release form.

Baseline validation before any release tag:

```bash
cd /home/sieve-pub/public-workspace/octoagent
make release-precheck
cd backend && .venv/bin/python -m pytest tests -q
cd ../frontend && pnpm lint && pnpm typecheck && pnpm build
```

Required evidence to keep with the release:

- `make release-precheck` passed
- backend full regression passed
- frontend lint/typecheck/build passed
- current version metadata aligned across backend, frontend, and desktop

## 2. Desktop Shell Release

The desktop shell now has minimum packaging scripts in [desktop/package.json](../../desktop/package.json):

```bash
cd /home/sieve-pub/public-workspace/octoagent/desktop
npm install
npm run pack
npm run dist:linux
```

Expected outputs:

- unpacked directory under `desktop/dist/`
- Linux `AppImage`
- Linux `tar.gz`

Runtime assumption:

- the packaged desktop app still expects a reachable WebUI origin, defaulting to `http://127.0.0.1:19880`
- override with `OCTOPUSAGENT_WEBUI_URL` when packaging or launching against a non-default endpoint

## Recommended Release Materials

Prepare these artifacts for each release candidate:

1. GitHub release notes
2. validation summary
3. operator upgrade notes
4. desktop packaging notes

### GitHub Release Notes Template

```md
## OctoAgent <version>

### Highlights
- <2-5 user-visible items>

### Operator Notes
- <config, migration, or environment notes>

### Validation
- make release-precheck: passed
- backend full regression: passed
- frontend lint/typecheck/build: passed

### Desktop Packaging
- Linux AppImage: built / not built
- Linux tar.gz: built / not built
```

### Validation Summary Template

```md
Release candidate: <version>
Commit: <sha>

Checks:
- release-precheck: pass/fail
- backend full regression: pass/fail
- frontend lint: pass/fail
- frontend typecheck: pass/fail
- frontend build: pass/fail

Known non-blockers:
- <items like optional bootstrap guide generation not observed because model not installed>
```

### Operator Upgrade Notes Template

```md
Upgrade notes:
- required config changes: none / <details>
- new dependencies: <details>
- local model/runtime changes: <details>
- route or UI compatibility notes: <details>
```

## What Is Not Yet Shipped

These remain outside the current packaging baseline:

- one-click all-in-one offline desktop distribution with embedded backend/frontend stack
- packaged bootstrap GGUF inside the desktop release
- auto-generated notarized/macOS or signed/Windows installers

If those become required, they should be treated as a dedicated packaging project rather than assumed to exist already.