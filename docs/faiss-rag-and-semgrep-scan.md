# Local FAISS RAG And Semgrep Scan Workflow

This note documents the repository paths and operator workflow for local vector retrieval and security scanning.

## Paths

- Active repository: `/home/sieve-pub/public-workspace/octoagent`
- Backend runtime: `/home/sieve-pub/public-workspace/octoagent/backend/.venv/bin/python`
- Unified RAG facade: `backend/src/rag/facade.py`
- Unified RAG store: `backend/src/rag/unified_store.py`
- Optional FAISS adapter: `backend/src/rag/faiss_backend.py`
- Skill root: `skills/`
- Semgrep skill: `skills/public/semgrep-scan/SKILL.md`

## Local Vector Retrieval

`UnifiedRAGStore.search_table()` now prefers the in-process FAISS path for `system_memories` and `bootstrap_vectors` when both `faiss` and `numpy` are importable. The FAISS adapter builds a normalized `IndexFlatIP` over the local DuckDB embeddings for the requested table and namespace, searches it locally, and marks returned match metadata with `vector_backend: faiss`.

Fallback order is intentionally conservative:

1. FAISS local index over DuckDB embeddings.
2. DuckDB native `array_cosine_similarity`.
3. Python cosine similarity.

If FAISS is not installed or a FAISS call fails, the existing DuckDB/Python paths continue to serve results. This keeps `deep-research`, custom RAG workflows, lesson injection, and bootstrap retrieval local-first without making FAISS a hard runtime dependency.

Quick check:

```bash
cd /home/sieve-pub/public-workspace/octoagent/backend
.venv/bin/python -m pytest tests/rag/test_faiss_backend.py
```

FAISS is now a reproducible OctoAgent backend dependency. It is tracked in `backend/pyproject.toml`, `backend/uv.lock`, and `backend/requirements.txt`; `scripts/bootstrap.sh` installs it into `backend/.venv` through `uv sync` or the pip fallback.

Do not create host-level or tool-local virtual environments for FAISS. The FAISS adapter is imported by the LangGraph/Gateway backend process, so the package must live in the active OctoAgent backend runtime environment: `backend/.venv`. Future materialized FAISS artifacts, if any, should be placed under `runtime/system_tools/faiss-rag/`, but the Python package itself belongs to `backend/.venv`.

## Semgrep Scan Skill

Use the `semgrep:scan` skill for security-sensitive code changes, dependency or configuration edits, and before finalizing workflows that touch auth, network, shell execution, file handling, serialization, or secrets.

Recommended command from the repository root:

```bash
semgrep scan --config auto --error --json --output runtime/reports/semgrep-scan.json .
```

If `semgrep` is not installed globally, use a temporary runner instead of creating a project venv:

```bash
uvx semgrep scan --config auto --error --json --output runtime/reports/semgrep-scan.json .
```

The scan report path should stay under `runtime/reports/`, which is local runtime output rather than source code. Summaries should include command, target, report path, finding count by severity, and whether any blocking high or critical findings remain.
