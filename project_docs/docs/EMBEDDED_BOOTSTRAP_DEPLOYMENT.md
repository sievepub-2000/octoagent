# Embedded Bootstrap Deployment And Full Guide Verification

This document explains how to deploy the local embedded bootstrap model used by OctoAgent and how to fully verify guide generation.

## What This Feature Is

OctoAgent includes a tiny local bootstrap runtime implemented in [backend/src/bootstrap/runtime.py](../../backend/src/bootstrap/runtime.py).

It is used for:

- startup/onboarding guidance
- emergency local fallback when no configured chat model is available
- lightweight semantic retrieval through a local DuckDB-backed bootstrap store

Default model configuration comes from [backend/src/config/embedded_model_config.py](../../backend/src/config/embedded_model_config.py):

- repo: `lmstudio-community/gemma-3-270m-it-GGUF`
- file: `gemma-3-270m-it-Q4_K_M.gguf`
- default cache dir: `deploy/system/bootstrap/models`
- default vector store: `deploy/system/bootstrap/bootstrap_vectors.duckdb`

## Default Deployment Path

By default, the embedded bootstrap assets are project-managed and resolve under the repository root.

That means the default embedded model path is:

```text
/home/sieve-pub/public-workspace/octoagent/deploy/system/bootstrap/models/gemma-3-270m-it-Q4_K_M.gguf
```

And the default vector store path is:

```text
/home/sieve-pub/public-workspace/octoagent/deploy/system/bootstrap/bootstrap_vectors.duckdb
```

If `project_managed: false`, the effective base directory is resolved by [backend/src/config/paths.py](../../backend/src/config/paths.py) in this order:

1. `OCTO_AGENT_HOME`
2. workspace path persisted by setup state
3. fallback default: `~/octoagent-workspace`

## Current Local Reality On This Machine

As of the current audit:

- OctoAgent local stack is running on `19824`, `19830`, `19832`, `19880`
- a separate `llama-server` is running on `8000`
- user service `llama-api-proxy.service` is active
- the bootstrap GGUF file is present under the project system bootstrap path
- the bootstrap vector store is present under the project system bootstrap path

Guide generation can now be validated end to end against the installed local model.

## Deployment Steps

### Option A: Install through the OctoAgent API

Start the local stack, then call:

```bash
curl -X POST http://127.0.0.1:19880/api/bootstrap/install
```

Expected response shape:

```json
{
  "installed": true,
  "model_path": ".../deploy/system/bootstrap/models/gemma-3-270m-it-Q4_K_M.gguf"
}
```

### Option B: Install directly from Python

```bash
cd /home/sieve-pub/public-workspace/octoagent/backend
./.venv/bin/python - <<'PY'
from src.bootstrap.runtime import get_embedded_bootstrap_runtime

runtime = get_embedded_bootstrap_runtime()
path = runtime.ensure_installed()
print(path)
PY
```

This should download the GGUF into the configured bootstrap cache directory.

## Optional Config Overrides

If you want to switch back to user-workspace-managed storage, set `project_managed: false` and then set `OCTO_AGENT_HOME` before starting the gateway:

```bash
export OCTO_AGENT_HOME=/data/octoagent-runtime
```

You can also persist the setup workspace through the setup wizard, which changes the runtime base directory used by the path resolver when `project_managed: false`.

## Full Guide Generation Verification

To fully verify the bootstrap solution, do not stop at “the settings card rendered”. Verify the whole path below.

### Step 1: Confirm model file exists

```bash
find /home/sieve-pub/public-workspace/octoagent/deploy/system/bootstrap/models -maxdepth 1 -type f -name 'gemma-3-270m-it-Q4_K_M.gguf'
```

If `project_managed: false`, inspect the configured runtime root instead.

### Step 2: Confirm bootstrap status shows installed

```bash
curl http://127.0.0.1:19880/api/bootstrap/status
```

Expected fields:

- `installed: true`
- `model_path` points to the GGUF file
- `framework: llama_cpp`

### Step 3: Seed or sync semantic documents

The guide path is best verified with bootstrap retrieval data present.

Seed the default docs:

```bash
cd /home/sieve-pub/public-workspace/octoagent/backend
./.venv/bin/python - <<'PY'
from src.bootstrap.runtime import get_embedded_bootstrap_runtime

runtime = get_embedded_bootstrap_runtime()
print(runtime.seed_default_documents())
PY
```

Optionally sync local corpus docs as well:

```bash
cd /home/sieve-pub/public-workspace/octoagent/backend
./.venv/bin/python - <<'PY'
from src.bootstrap.runtime import get_embedded_bootstrap_runtime

runtime = get_embedded_bootstrap_runtime()
print(runtime.sync_local_corpus())
PY
```

### Step 4: Generate the guide through the API

```bash
curl -X POST http://127.0.0.1:19880/api/bootstrap/guide \
  -H 'Content-Type: application/json' \
  -d '{"user_goal":"我要完成本地首次部署并开始第一个任务"}'
```

Expected result:

- non-empty `message`
- populated `suggestions`
- optional `evidence` if retrieval matched seeded docs

### Step 5: Verify from the WebUI

Open settings in the WebUI and navigate to the bootstrap section.

You should see:

- installed state
- model path
- semantic store stats
- guide generation button completing without timeout or empty response

### Step 6: Re-run release smoke if desired

After the model is installed, re-run:

```bash
cd /home/sieve-pub/public-workspace/octoagent
make release-precheck
```

The smoke result should still pass, and the `guide_generated` field should now be able to flip from advisory false to true.

## Failure Modes To Expect

### 1. Model missing

Symptom:

- `FileNotFoundError`
- status shows `installed: false`
- guide generation not observed in smoke

Fix:

- run install step first

### 2. Download blocked or slow

Symptom:

- Hugging Face download stalls or fails

Fix:

- use a reachable mirror or pre-download the GGUF into the expected `deploy/system/bootstrap/models` directory
- verify file ownership and read permissions

### 3. llama.cpp import/runtime problem

Symptom:

- bootstrap install succeeds but generation fails during load

Fix:

- ensure backend venv has `llama-cpp-python`
- verify CPU-only deployment has enough RAM and thread settings are reasonable

### 4. Empty guide despite installed model

Symptom:

- guide returns low-value text or no useful evidence

Fix:

- seed default documents
- sync local corpus
- retry guide generation with a clearer `user_goal`

## Recommended Minimal Production Baseline

For a real local deployment, the minimal embedded-bootstrap-ready baseline is:

1. bootstrap GGUF installed
2. `api/bootstrap/status` returns `installed: true`
3. seeded onboarding documents exist in the local vector store
4. `api/bootstrap/guide` returns a non-empty message plus suggestions
5. WebUI bootstrap settings page shows installed model state and successful guide generation

Until all five are true, bootstrap guide generation should be treated as partially deployed rather than fully verified.