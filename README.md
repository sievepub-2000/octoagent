> **OctoAgent — a white-box AI agent for business operations, system
> administration, research, and office automation.** Every reasoning
> step, every tool call, every artifact is visible, auditable, and
> reproducible. No "black box" — the opposite of OpenClaw-style closed
> agents.
>
> **License:** Dual-licensed under **SSPL v1** + commercial alternatives.
> The Bytedance-derived portion remains under **MIT** (see [`NOTICE.md`](NOTICE.md)).
> Full terms: [`LICENSE`](LICENSE) · contribution policy: [`CONTRIBUTING.md`](CONTRIBUTING.md).
>
> **Contact / 商务联系 / お問い合わせ:** **zillafan80@gmail.com**
>
> **Commercial License FAQ:** [`docs/COMMERCIAL_LICENSE_FAQ.md`](docs/COMMERCIAL_LICENSE_FAQ.md)
> — TL;DR: free **only** for personal non-commercial use; every
> other use (SaaS, internal enterprise, OEM, redistribution) requires
> a commercial license.
>
> **Docs index:** [`docs/INDEX.md`](docs/INDEX.md) ·
> **Module ownership map:** [`docs/MODULE_OWNERS.md`](docs/MODULE_OWNERS.md)

<p align="center">
  <a href="https://github.com/sievepub-2000/octoagent/actions/workflows/ci.yml"><img alt="ci" src="https://img.shields.io/badge/ci-passing-brightgreen"></a>
  <a href="https://github.com/sievepub-2000/octoagent/actions/workflows/license-check.yml"><img alt="license-check" src="https://img.shields.io/badge/licenses-scanned-blue"></a>
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-SSPLv1%20%2B%20commercial-orange"></a>
  <a href="#"><img alt="python" src="https://img.shields.io/badge/python-3.12%2B-blue"></a>
  <a href="#"><img alt="node" src="https://img.shields.io/badge/node-22%2B-blue"></a>
</p>

---

## Table of contents

- [English — Getting started](#english--getting-started)
- [Docker installation](#docker-installation-default)
- [日本語 — はじめに](#日本語--はじめに)
- [Project facts (canonical)](#project-facts-canonical)

---

## Writing and Publishing Workflows

OctoAgent includes an optional managed writing and publishing suite for articles, novels, papers, and web serials. It wraps browser-use/browser-use, microsoft/playwright, wp-cli/wp-cli, microsoft/presidio, jgm/pandoc, textlint/textlint, and vale-cli/vale behind guarded tools for project storage, drafting, review, export, human approval, browser/WordPress publishing, and publication audit. See [docs/writing-publishing-tools.md](docs/writing-publishing-tools.md).

## English — Getting started

### What OctoAgent does

OctoAgent is a **task-centric multi-agent platform** that runs locally
(or on your own server) and turns a single English / Chinese / Japanese
instruction into:

- a sequence of inspectable tool calls (web search, file I/O, code
  execution in a sandbox, browser automation, database queries, …),
- a streaming chain-of-action visible in the WebUI,
- a final artifact (a Markdown report, an Excel spreadsheet, a PPT, a
  rewritten Word file, a refactored codebase, an audit report, …).

Typical verticals shipped today:

| Vertical | Example task |
|----------|--------------|
| Business research | "Compare top-10 EV charging vendors in Germany on price, network coverage, and 2025 funding." |
| Academic research | "Survey 30 papers on retrieval-augmented generation since 2024; produce a literature review with citations." |
| Office automation | "Take this PDF, extract every table, write me an Excel with consolidated KPIs and a 1-page PPT summary." |
| System operations | "SSH into host3, audit `/etc/systemd/system/*.service`, find units missing `Restart=on-failure`, propose a patch." |
| Web data scraping | "Crawl 200 product pages on this site, normalize to JSON, store in the local RAG, and answer questions about the catalog." |
| Code work | "Refactor `backend/src/agents/middlewares/` for clarity; add tests; keep all imports passing import-linter." |

Architecture (high level):

```
Next.js WebUI  ──HTTP──▶  FastAPI gateway  ──▶  LangGraph runtime
                                              │
                                              ├── Subagent orchestration
                                              ├── Tool-budget middleware
                                              ├── RAG store (FAISS)
                                              ├── System-execution guard
                                              └── Model-auth (multi-tenant)
```

### Prerequisites

The default installation path is now **Docker Compose** on all supported desktop/server platforms:

- Linux with Docker Engine 24+ and Compose v2.
- Windows 11 with Docker Desktop using Linux containers.
- macOS with Docker Desktop, OrbStack, or another Docker-compatible engine.
- Git is needed only when the installer has to clone the repository.

You do **not** need host Python, Node.js, pnpm, nginx, PostgreSQL, or Redis for the Docker profile. They are packaged as containers or image dependencies.

### Docker Installation (default)

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.sh | bash
```

Windows PowerShell:

```powershell
iwr https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.ps1 -UseBasicParsing | iex
```

From an existing checkout:

```bash
git clone https://github.com/sievepub-2000/octoagent.git
cd octoagent
./scripts/install-docker.sh --prefix "$PWD"
```

Open the WebUI after the health check passes:

```text
http://127.0.0.1:19800
```

The Docker profile starts nginx, the production WebUI, the FastAPI gateway, LangGraph, PostgreSQL, Redis, and the packaged MCP tool dependencies. See [docs/docker-install.md](docs/docker-install.md) for operations, configuration, packaging, and verification.

### Host Installation (advanced)

The legacy host installer remains available for Linux service deployments that intentionally manage Python, Node.js, nginx, and systemd on the host:

```bash
git clone https://github.com/sievepub-2000/octoagent.git
cd octoagent
./scripts/install-octoagent.sh
```

### First-run configuration (default models)

OctoAgent ships preconfigured for **OpenRouter free tier**:

| Slot | Default model | Use |
|------|---------------|-----|
| Flash dialogue | `openrouter/openai/gpt-oss-20b:free` | WebUI typeahead, quick replies |
| Long-context reasoning | `openrouter/qwen/qwen3-next-free` | Subagent planning, RAG synthesis |
| Code | `openrouter/openai/gpt-oss-120b:free` | Code generation / refactor |

To use the defaults:

```bash
./scripts/octoagent configure
# Paste your free OpenRouter API key when prompted.
```

The CLI writes it to `runtime/config/model_auth.env` (mode 0600, also
gitignored). You can edit the file manually:

```bash
OCTOAGENT_MODEL_AUTH_OPENROUTER=sk-or-v1-...
# Optional — replace any slot with your own provider key:
OCTOAGENT_MODEL_AUTH_OPENAI=sk-...
OCTOAGENT_MODEL_AUTH_ANTHROPIC=sk-ant-...
OCTOAGENT_MODEL_AUTH_DEEPSEEK=...

# Optional OpenRouter app attribution. Usage accounting is enabled by default.
OCTOAGENT_OPENROUTER_APP_URL=https://github.com/sievepub-2000/octoagent
OCTOAGENT_OPENROUTER_APP_TITLE=OctoAgent
OCTOAGENT_OPENROUTER_USAGE_INCLUDE=true
```

To **change the default model assignments**, edit
`runtime/config/models.yaml` (a starter copy is generated on first
configure) — the schema mirrors `backend/src/governance/model_auth/`.

#### Unified System-Level Model Configuration (v2026.7.4+)

Starting from v2026.7.4, OctoAgent uses a **single entry point** for system-level model configuration:

- **`runtime/config/config.yaml`** — the canonical source for `system.default_model`
- All backend services read default model from this file via `load_setup_state()` in `backend/src/runtime/config/paths.py`
- Priority: `config.yaml` > `setup_state.json` (fallback)

This eliminates configuration drift between multiple config files. The workspace-level setup (`workspace/env/setup.json`) remains independent for per-project overrides.

```yaml
# runtime/config/config.yaml
system:
  default_model: "ornith-1.0-35b-nvfp4"  # Single source of truth

models:
- name: ornith-1.0-35b-nvfp4
  priority: 120
  ...
```

### Start the service

Foreground (development):

```bash
make dev                      # backend + frontend, hot reload
# WebUI: http://127.0.0.1:19800
```

Background (systemd, production-style):

```bash
sudo cp deploy/system/octoagent-local.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now octoagent-local
journalctl -u octoagent-local -f
```

### Verifying the install

```bash
make smoke-chat-regression    # browser-level smoke (Playwright)
make release-readiness        # full evidence gate
```

A green `release-readiness` run means: compile + lint + build pass,
doctor / API contract smoke pass, real-browser smoke pass, system-
execution guard pass, RAG live-validation pass.

### The About panel (in-product contact)

Open the WebUI → **Settings (top-right gear) → About**. The panel leads
with the **license summary** (SSPL v1 default + commercial alternatives;
the Bytedance-derived portion remains under MIT — see
[`NOTICE.md`](NOTICE.md)), immediately followed by the **contact email**.
Both blocks are **hard-coded** in `backend/src/governance/about.py` and
protected by a SHA-256 integrity fingerprint. Editing them without
resealing breaks startup; even with resealing, the email is the HKDF
salt for every internal credential, so changing it requires re-keying
all internal databases. This is intentional (see LICENSE Addendum A).

### Updating

```bash
git pull
./scripts/install-octoagent.sh    # idempotent — updates deps in place
sudo systemctl restart octoagent-local
```

### Reporting bugs / commercial inquiries

- **Bugs / features:** open a GitHub issue.
- **Security:** email `zillafan80@gmail.com` subject
  `[octoagent-security]`.
- **Commercial license:** use the
  [`Commercial inquiry`](.github/ISSUE_TEMPLATE/commercial_inquiry.md)
  template or email directly.

---

## 日本語 — はじめに

### OctoAgent とは

OctoAgent は **タスク中心のマルチエージェントプラットフォーム** です。
ローカル（または自社サーバ）で動作し、日本語 / 英語 / 中国語の指示文を
以下のような出力に変換します：

- 検証可能なツール呼び出しの連続（Web 検索、ファイル I/O、サンドボックス
  上のコード実行、ブラウザ自動化、データベース問い合わせなど）
- WebUI 上でストリーミング表示される行動ログ
- 最終成果物（Markdown レポート、Excel、PPT、書き換えた Word、リファクタ
  済みコード、監査レポートなど）

すべての推論ステップ、ツール呼び出し、生成物は **可視・監査可能・再現
可能** です。OpenClaw のような閉じたブラックボックスエージェントとは
対照的に、OctoAgent は **ホワイトボックス** の運用思想を貫いています。

### 必要環境

- **OS:** Linux (Ubuntu 22.04+ / Debian 12 / RHEL 9) または WSL2 上の
  Windows 11。
- **Python 3.12+**、**Node.js 22+**、**pnpm 9+**。
- **2 GB の空きディスク**、**8 GB RAM（推奨 16 GB）**。
- 任意で **PostgreSQL 15+**、**CUDA 12** + NVIDIA ドライバ。

### インストール（Docker 推奨）

Linux / macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.sh | bash
```

Windows PowerShell:

```powershell
iwr https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.ps1 -UseBasicParsing | iex
```

起動後、WebUI を開きます：

```text
http://127.0.0.1:19800
```

詳しい日本語ガイドは [`docs/ja/README.md`](docs/ja/README.md)、詳細な英語版 Docker 手順は [`docs/docker-install.md`](docs/docker-install.md) を参照してください。
3. `runtime/`（logs / pids / cache / secrets）を安全な権限で作成。
4. 初回起動時に `runtime/secrets/octoagent_internal_master.key`
   （64 バイト乱数）を生成。内部 DB パスワードや内部 API トークンの
   HKDF IKM として使用されます。**gitignore 対象です。永続化データを
   暗号化している場合は必ずバックアップしてください。**

### 初回設定（既定モデル）

OctoAgent は **OpenRouter 無料枠** を既定で使うように事前設定されて
います。

| 用途 | 既定モデル |
|------|------------|
| Flash 対話 | `openrouter/openai/gpt-oss-20b:free` |
| 長文・推論 | `openrouter/qwen/qwen3-next-free` |
| コード | `openrouter/openai/gpt-oss-120b:free` |

設定コマンド：

```bash
./scripts/octoagent configure
# 無料 OpenRouter API キーを貼り付けてください。
```

`runtime/config/model_auth.env`（mode 0600、gitignore 対象）に保存されます。
独自プロバイダの鍵を使いたい場合は、同ファイルを直接編集してください。

### 起動

開発用（ホットリロード）：

```bash
make dev
# WebUI: http://127.0.0.1:19800
```

本番風（systemd）：

```bash
sudo cp deploy/system/octoagent-local.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now octoagent-local
journalctl -u octoagent-local -f
```

### About パネル

WebUI 右上の歯車 → **Settings → About** を開くとまず **ライセンス概要**
（既定: SSPL v1 / 商用代替あり / Bytedance 由来部分は MIT 継続 — 詳細は
[`NOTICE.md`](NOTICE.md)）が表示され、その直後に **連絡先メール
アドレス** が続きます。両ブロックとも `backend/src/governance/about.py`
に **ハードコード** されており、SHA-256 のフィンガープリントで改ざん
が検出されます。改ざんすると起動失敗、もしくは内部認証情報が再導出
されて DB 接続が壊れます（LICENSE Addendum A 参照）。

### 商用ライセンス / お問い合わせ

- **バグ / 機能要望:** GitHub Issue を起票してください。
- **セキュリティ:** `zillafan80@gmail.com` 件名
  `[octoagent-security]` に直接ご連絡ください。
- **商用ライセンス:**
  [`Commercial inquiry`](.github/ISSUE_TEMPLATE/commercial_inquiry.md)
  テンプレートをご利用いただくか、`zillafan80@gmail.com` 宛に
  直接メールください。

---

## Project facts (canonical)



## Canonical Project Path

The only active OctoAgent project root on this host is `/home/sieve-pub/public-workspace/octoagent`. Do not use `/home/sieve-pub/codex/octoagent` or `/home/sieve-pub/public-workspace/octoagent-module1-webui-only` as project roots; branch and worktree content should be merged into the canonical project root.

OctoAgent is a task-centric multi-agent platform built around a single active runtime path:
Next.js WebUI -> FastAPI gateway -> LangGraph runtime.

Current repository truth:

- active execution provider: LangGraph-only
- backend top-level modules: 45
- gateway router groups: 38 registered groups (41 router files)
- primary workflow truth source: task_workspaces + workflow_core projections
- unified local entrypoint: http://127.0.0.1:19800
- local default model: `openrouter-free-openai-gpt-oss-20b` for flash WebUI dialogue, with quota/cooldown-aware fallback for live WebUI dialogue
- runtime governance version: `2026.6.1`
- systemd startup owner: `/etc/systemd/system/octoagent-local.service` calls only `scripts/start-octoagent.sh`; all OctoAgent child processes are launched and stopped by repository scripts under `scripts/`
- backend Python runtime: one repository venv at `backend/.venv`, exposed to scripts as `OCTOAGENT_PYTHON_BIN`
- repository-scoped tools and maintenance scripts live under `scripts/` and `runtime/`; host-level helper copies under `/usr/local/bin` are not part of the active deployment

Canonical documentation:

- project index: [project_docs/README.md](project_docs/README.md)
- current status: [project_docs/docs/PROJECT_STATUS.md](project_docs/docs/PROJECT_STATUS.md)
- current progress: [project_docs/docs/PROJECT_PROGRESS.md](project_docs/docs/PROJECT_PROGRESS.md)
- P18 full repair and verification: [project_docs/docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md](project_docs/docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md)
- P19 system linkage and long execution repair: [project_docs/docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md](project_docs/docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md)
- P21 context/runtime/repository sync: [project_docs/docs/P21_CONTEXT_RUNTIME_AND_REPOSITORY_SYNC_2026-05-15.md](project_docs/docs/P21_CONTEXT_RUNTIME_AND_REPOSITORY_SYNC_2026-05-15.md)
- P24 autonomous capability enhancement: [project_docs/docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md](project_docs/docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md)
- P25 confirmation and Letta memory integration: [project_docs/docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md](project_docs/docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md)
- P15 Hermes Gemini/WebUI readiness: [project_docs/docs/P15_HERMES_GEMINI_WEBUI_AND_95_LOCAL_READINESS_2026-05-06.md](project_docs/docs/P15_HERMES_GEMINI_WEBUI_AND_95_LOCAL_READINESS_2026-05-06.md)
- architecture: [project_docs/docs/ARCHITECTURE.md](project_docs/docs/ARCHITECTURE.md)
- module owners (Phase 0 frozen): [project_docs/docs/MODULE_OWNERS.md](project_docs/docs/MODULE_OWNERS.md)
- topology freeze (2026-05-26): [project_docs/docs/TOPOLOGY_FREEZE_2026-05-26.md](project_docs/docs/TOPOLOGY_FREEZE_2026-05-26.md)
- P0 closure and cleanup: [project_docs/docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md](project_docs/docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md)
- local FAISS RAG and semgrep scan workflow: [docs/faiss-rag-and-semgrep-scan.md](docs/faiss-rag-and-semgrep-scan.md)
- one-line install and CLI: [docs/one-line-install-and-cli.md](docs/one-line-install-and-cli.md)
- channel bridge deployment: [project_docs/docs/CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md](project_docs/docs/CHANNEL_BRIDGE_DEPLOYMENT_GUIDE.md)


## One-Line Install And CLI

From a Linux host with network access, the service install path can be bootstrapped with:

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-octoagent.sh | bash -s -- --prefix /home/sieve-pub/public-workspace/octoagent --user sieve-pub --mode service --yes --start
```

After installation, `octoagent` starts the full stack. `octoagent configure` updates the repository setup state for the default model, and `octoagent ports` prints the active port map. See [docs/one-line-install-and-cli.md](docs/one-line-install-and-cli.md).

## Production Hardening Before Launch

Set these environment variables before exposing the service beyond a trusted local network:

- `OCTO_OPERATOR_TOKEN`: required shared token for operator/admin governance endpoints when configured.
- `OCTO_EXECUTION_WORKER_TOKEN`: required shared token for distributed worker dispatch and callbacks when configured.
- `OCTO_OPERATOR_AUDIT_SECRET`: HMAC key for signed governance audit events. Without it, audit signatures are plain SHA-256 checksums.
- `OCTO_RUNTIME_MAX_RUNNING_RUN_AGE_SECONDS`: stale LangGraph run ledger timeout, default `3600`. Runtime maintenance marks older abandoned running records as `timeout` so long-running soak checks can settle.
- `OCTO_SMTP_HOST`, `OCTO_SMTP_PORT`, `OCTO_SMTP_USERNAME`, `OCTO_SMTP_PASSWORD`, `OCTO_SMTP_FROM`, `OCTO_SMTP_TLS`: SMTP settings for the built-in user email verification flow. Without SMTP, verification codes are logged for local development only.
- `OCTO_AUTH_DEV_EXPOSE_CODES`: keep unset or `0` in production. Setting `1` returns verification codes in API responses for local smoke tests only.

The repository keeps local development compatible when the tokens are unset, but production deployments should set all production secrets and rotate any values that have been exposed in local `.env` files.

## Runtime Governance Notes (2026-05-22)

The 2026-05-22 governance pass keeps the 2号机 deployment and the Git repository aligned around one startup and environment stack:

- systemd owns only `octoagent-local.service`; the unit delegates startup and shutdown to `scripts/start-octoagent.sh` without separate `ExecStartPre` helper scripts or drop-ins
- `scripts/start-octoagent.sh run` performs repository-owned runtime preparation, then starts every OctoAgent component through `scripts/start-daemon.sh`
- Python entrypoints use `backend/.venv/bin/python` through `OCTOAGENT_PYTHON_BIN`; LangGraph, Gateway, nginx config rendering, and frontend build helpers share that same backend environment
- former host helper scripts `octoagent-monitor.sh` and `octoagent-cleanup.sh` live under `scripts/` and are repository-scoped
- cleanup removes repository caches, pyc files, temporary files, and stale `/tmp/octoagent*` probes while preserving required dependency/runtime stores such as `backend/.venv`, `frontend/node_modules`, and production `.next` assets

## Full Repair And Verification Notes (2026-05-11)

## Autonomous Capability Enhancement Notes (2026-05-16)

The 2026-05-16 pass adds a built-in system operations tool layer for autonomous
agent work: runtime health reports, masked security scanning, configuration
drift snapshots/checks, and local media metadata probing. These tools complement
the existing cron, hook, memory, subagent, workflow, Codex CLI, image processing,
document conversion, and web acquisition surfaces without adding another runtime
service or external daemon.

See [project_docs/docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md](project_docs/docs/P24_AUTONOMOUS_AGENT_CAPABILITY_ENHANCEMENT_2026-05-16.md).

## Confirmation And Letta Memory Notes (2026-05-16)

Dangerous host-level abilities are now available through explicit user
confirmation rather than being globally unavailable. Letta-style core memory
blocks and archival memory are integrated into the existing OctoAgent memory
stack without adding a separate Letta service.

See [project_docs/docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md](project_docs/docs/P25_CONFIRMATION_AND_LETTA_MEMORY_INTEGRATION_2026-05-16.md).

## Context Runtime And Repository Sync Notes (2026-05-15)

The 2026-05-15 pass repaired the long-context local-model failure mode found in
the latest historical LangGraph thread, normalised runtime identity and writable
path ownership for the `sieve-pub` daemon user, configured Google provider
credentials in local ignored `.env`, and cleared the backend Ruff/PEP8 baseline.

Source and tests remain tracked for repository sync; local runtime state under
`backend/runtime/` and `workspace/self_evolution/` is intentionally ignored.
See [project_docs/docs/P21_CONTEXT_RUNTIME_AND_REPOSITORY_SYNC_2026-05-15.md](project_docs/docs/P21_CONTEXT_RUNTIME_AND_REPOSITORY_SYNC_2026-05-15.md).

The 2026-05-11 repair pass hardens the local production path and records a fresh validation baseline:

- model fallback, subagent/workflow wiring, and tool recovery were repaired and covered by backend tests
- SSRF-safe web fetch behavior now validates private/internal network addresses and redirects fail closed
- sidebar width cookie handling no longer causes hydration mismatch on first client render
- root layout includes stale Next chunk recovery for failed `/_next/static/` script or CSS loads
- CLI and Makefile smoke entrypoints now expose safe help output and run their documented checks
- `run_webui_smoke.py` honors configured navigation timeout for cold Next.js dev compiles
- `/workspace/agents/new` form controls now have accessible names and non-interactive status indicators are no longer focusable buttons
- real WebUI verification covered chat, configuration, agent, workflow, management, 320px reflow, skip link, hydration, chunk recovery, and forced-colors mode

See [project_docs/docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md](project_docs/docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md) for the validation matrix.

## System Linkage And Long Execution Notes (2026-05-12)

The 2026-05-12 pass connects management surfaces to real runtime inventory and
improves long-running task continuity:

- `/workspace/agents` now shows custom agents and installed skill-exported
	agent templates; templates create custom copies before chat or workflow use.
- MCP add/update/delete uses single-server APIs, and unresolved environment
	variables are surfaced in readiness status.- Plugin cards no longer expose a fake edit action; the real supported actions
	are install, enable, disable, and uninstall.
- Workflow agent selectors use executable custom agents only.
- Session compaction stores a runtime checkpoint and injects it into later turns
	so long tasks can continue after older dialogue is compressed.

See [project_docs/docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md](project_docs/docs/P19_SYSTEM_LINKAGE_AND_LONG_EXECUTION_REPAIR_2026-05-12.md) for the repair report and verification snapshot.

## Runtime Speed And Stability Notes (2026-05-07)

The 2026-05-07 pass makes WebUI dialogue cheaper to render and cheaper to answer:

- Flash-mode simple turns skip the extra client pre-planning request unless execution, file, repository, or system work is detected.
- Flash-mode dialogue is pinned to the fast free model path and ignores stale slow-model browser overrides such as `nemotron-3-super-free`.
- Dialogue routing now classifies each turn as `direct_answer`, `current_snapshot`, `current_research`, `tool_action`, or `deep_agent`. The route controls model choice, prompt depth, tool binding, and memory writes.
- Short flash-mode turns skip heavy memory summarisation unless the user explicitly asks the system to remember a preference or fact.
- Current weather and X/Twitter trend requests use compact server snapshots; weather snapshots are resolved per city with Open-Meteo retries and a `wttr.in` fallback.
- Snapshot-backed turns can now answer directly from the structured runtime payload without making an LLM call. This keeps simple weather/trend tasks bounded by data-fetch latency instead of model latency.
- Long chat histories render a bounded active window by default, with an explicit "show earlier messages" control for old turns. This keeps browser DOM, markdown, and streaming work bounded during long sessions.
- Stream watchdog timers are cleared both when server messages arrive and when the SDK reports the run is no longer loading.
- Model routing keeps failed or quota-exhausted models on a short persistent cooldown and falls back automatically.
- `make stop` drains local nginx, gateway, frontend, LangGraph, stale port listeners, and stale `backend/.langgraph_api` state before a clean restart.

## Runtime Stability Notes (2026-04-29)

The current chat runtime hardening pass focuses on long-running conversation stability, context-window safety, and real-browser regression coverage.

### Chat And Context Safety

| Area | Current behavior |
| --- | --- |
| Tool registry | `web_search` is registered as a first-class tool alias and duplicate tool names are rejected before execution. |
| Context guard | Oversized tool, human, and assistant messages are safely truncated before model calls that would exceed context limits. |
| UI observability | Host memory pressure and context-window trimming are reported separately so context truncation is not shown as a memory-guard failure. |
| Subtask state | Ordinary tools no longer write into the subtask store; only `task` tool calls are mirrored as subtasks. |
| Long conversation rendering | The message list uses ordinary scrolling plus `content-visibility` containment. A 520-message browser scroll regression is passing, so no virtual list is currently required. |

### Runtime Persistence And Permissions

| Area | Current behavior |
| --- | --- |
| LangGraph checkpointer | SQLite async saver is wrapped with `adelete_for_runs`, `acopy_thread`, and `aprune` maintenance hooks. |
| Maintenance telemetry | Checkpointer maintenance calls now log and expose per-operation counters through the wrapper. |
| Runtime directories | Gateway startup repairs writable runtime paths such as `backend/.octoagent`, `workspace/runtime`, `workspace/env`, and workflow state directories. |
| nginx local temp files | Local nginx uses repository-owned `tmp/nginx/*` temp paths instead of system `/var/lib/nginx/*` paths. |

### Web Fetch TLS Handling

`web_fetch` (`backend/src/community/ddg/tools.py`) and `scrapling_fetch`
(`backend/src/community/scrapling/tools.py`) verify TLS certificates by default.
For `web_fetch`, OctoAgent builds an explicit verification context using
`truststore` when available and falls back to `certifi`; this follows HTTPX's
official `verify=<SSLContext>` path. For Scrapling/curl-cffi, the tool uses
the official requests-style `verify` option.

Some public sites serve an incomplete certificate chain. When the first request
fails specifically with certificate verification errors, OctoAgent retries the
same public URL with certificate verification disabled, matching the documented
HTTPX/curl-cffi `verify=False` escape hatch. Results are marked so the model and
user can see the downgrade: `web_fetch` prepends a TLS warning, and
`scrapling_fetch` returns `tls_verification=disabled_after_certificate_error`.

Operators can disable the insecure retry with
`OCTO_WEB_FETCH_ALLOW_INSECURE_SSL_RETRY=0` or
`OCTO_SCRAPLING_ALLOW_INSECURE_SSL_RETRY=0`. `OCTO_WEB_FETCH_SSL_VERIFY=0`
disables the initial verified HTTPX context entirely and should only be used for
controlled local debugging.

### Browser Regression Coverage

`make smoke-chat-regression` now exercises the real WebUI through nginx and LangGraph:

- new chat shell
- stale thread route recovery
- continuation route shell
- ordinary tool-call history
- `web_search -> web_fetch/read_webpage` history
- context guard visible notice
- multi-turn and continuation history
- 520-message long-scroll pressure
- right-side Artifact and execution panel desktop/mobile screenshots

The command writes local-only artifacts that are intentionally ignored by Git:

- `backend/reports/chat-regression-trends.jsonl`
- `backend/screenshots/right-panel-visual/`

## Local Verification Commands

Use these commands before merging runtime or UI changes:

```bash
cd backend && make lint
cd backend && .venv/bin/python -m compileall -q src scripts
cd backend && .venv/bin/python scripts/run_system_doctor.py --skip-git
cd backend && .venv/bin/python scripts/run_system_execution_security_smoke.py
cd backend && .venv/bin/python scripts/run_operator_module_closure_smoke.py
cd backend && .venv/bin/python scripts/run_release_readiness_contract_smoke.py

cd frontend && pnpm lint
cd frontend && pnpm typecheck
cd frontend && pnpm build

make clean-stale-logs
make smoke-chat-regression
cd backend && .venv/bin/python scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19800 --gateway-url http://127.0.0.1:19800 --timeout-seconds 180
make operator-release
make release-readiness
```

Source-level test trees were intentionally removed by operator policy. Release confidence now relies on compile/lint/build, doctor/API contract smoke, real browser smoke, bounded or long soak, system-execution security smoke, release-readiness contract smoke, and the strict `make release-readiness` evidence gate. CI also runs `chat-regression` and uploads browser screenshots, trend JSONL, and runtime logs as the `chat-regression-artifacts` artifact.

## Operational Notes

System log rotation is managed by logrotate via [deploy/system/logrotate.d/octoagent](deploy/system/logrotate.d/octoagent). Install it once with:

```bash
sudo install -o root -g root -m 0644 deploy/system/logrotate.d/octoagent /etc/logrotate.d/octoagent
sudo logrotate -d /etc/logrotate.d/octoagent
```

For local verification, `make clean-stale-logs` truncates old runtime logs so current scans are not polluted by historical errors.

— Updated 2026-05-22
