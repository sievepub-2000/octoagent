# OctoAgent Round F deliverables (2026-05-14)

## Task 1 — tavily/jina key scan (DONE)
Definitive scan of host 192.168.110.2: only placeholder strings
`your-tavily-api-key` and `your-jina-api-key` exist in `.env` and
`.env.example`. No real `tvly-` / `jina_` token anywhere in `/home/sieve-pub`,
`/root/.bashrc`, `/etc/environment`, or `bash_history`. Decision: keep
keyless DDG path from Round E; Tavily/Jina remain optional fallbacks.

## Task 2 — runtime tool registration verified (DONE)
- `web_search` and `web_fetch` resolve to `src.community.ddg.tools:*` per
  `config.yaml`.
- `/api/system/modules/status` now DDG-aware: `web_search_keys.status=ok`,
  `details.primary=ddg`, `ddg_loaded=true`.
- `_probe_workspace_db` switched to absolute path (Path(__file__).parents[4]);
  `workspace_db.status=ok`.
- OVERALL=ok; 4 ports 307/404/200/307 green.

## Task 3 — skills duplicate audit (DONE)
Layout: `skills/public/` (20 modules) + `skills/custom/` (1 stub).
**Candidates for removal (pending operator confirm):**
1. `skills/custom/agency-agents/` — 434-byte `agent-templates.json` only, no
   SKILL.md, abandoned scaffold.
2. `skills/public/claude-to-octoagent/` — describes calling OctoAgent HTTP API
   from Claude desktop; mounting it as a skill inside OctoAgent is recursive
   and semantically wrong.

**Light overlap, distinct roles (KEEP):**
- `awesome-design-md` (governance) / `frontend-design` (creation) /
  `web-design-guidelines` (audit)
- `deep-research` (web) / `github-deep-research` (github)
- `find-skills` / `skill-creator` / `surprise-me`

## Task 4 — git review + push (DONE)
5 commits added on top of origin/main and pushed:
- `2785b45` chore(infra): ignore session backups, legacy archives, runtime db
- `83fbcf6` refactor(community): replace jina_ai with keyless DDG
- `fabafac` feat(observability): GET /api/system/modules/status
- `6401dac` feat(self-evolution): LessonsStore post-mortem persistence
- `37e5dc4` perf(startup): hash-skip frontend build + watchdog + checkpointer timing

Excluded by design: `*.bak.2026-05-*`, `_legacy_jina_ai.2026-05-13/`,
`workspace/lessons.db*` (all now in .gitignore). Left untouched: the in-flight
`backend/src/config/*.py` refactor (not authored this round).

## Task 5 — refactor plan (core → edge)
Top-15 longest backend files = 11,500+ lines concentrated in monoliths.
Ordered execution plan, surgical (no behavior change), validated per module by
service restart + 4-port probe + `/api/system/modules/status`.

### Wave 1: core
| Module | LOC | Concrete delta | Risk |
|---|---|---|---|
| `self_evolution/__init__.py` | 723 | Extract `models.py` (Enum + 3 dataclasses, lines 42–125). `__init__` keeps re-exports only. Append-only constraint honored: original file is appended-to, then dataclasses imported from new submodule. | Med (live engine) |
| `agents/checkpointer/async_provider.py` | ~120 | Replace ad-hoc `time.perf_counter()` logs with `contextlib.contextmanager` helper `_timed(name)`. -10 LOC. | Low |
| `agents/memory/simplemem_bridge.py` | 757 | Audit for unused params; if >100 LOC dead, defer to dedicated PR. | Med |

### Wave 2: API surface
| Module | LOC | Delta |
|---|---|---|
| `gateway/routers/runtime.py` | 852 | Split: pull workflow/cron endpoints into `runtime_workflow.py`. |
| `gateway/routers/memory.py` | 827 | Extract pydantic models into `memory_schemas.py`. |
| `gateway/routers/task_workspaces.py` | 741 | Audit duplicate request models. |
| `gateway/routers/agents.py` | 736 | Same. |

### Wave 3: services
| Module | LOC | Delta |
|---|---|---|
| `query_engine/service.py` | 837 | Extract embedding helpers into `query_engine/embedding.py`. |
| `optimization_program/service.py` | 789 | Split metric-collectors into `metrics.py`. |
| `capability_core/service.py` | 750 | Same shape (extract registry from service). |
| `task_workspaces/execution.py` | 820 | Move file-IO helpers to `execution_fs.py`. |
| `task_workspaces/research_fallback.py` | 896 | Audit dead fallbacks now that DDG is primary. |

### Wave 4: tooling / community
| Module | LOC | Delta |
|---|---|---|
| `tools/builtins/openharness_compat_tools.py` | 1542 | Likely legacy compat shim — measure import usage; deprecate unused exports. |
| `models/factory.py` | 995 | Audit redundant model classes; the OpenRouter free-list refresh is the ~9s startup bottleneck per Round 3 profile. Cache the list aggressively. |
| `client.py` | 972 | Split high-level facade from low-level transport. |
| Migrate `community/{tavily,firecrawl,image_search,infoquest}` onto `community/_base.py` (5/14 already DDG, jina_ai retired). |

### Validation gate per module
1. `pytest backend/tests/<area>/ -x` (if tests exist).
2. `sudo systemctl restart octoagent-local.service`; expect 307/404/200/307 within 40s.
3. `curl /api/system/modules/status | jq '.overall'` == `"ok"`.
4. `curl :19884/info` returns 200.

## Task 6 — skill auto-install prior art

Reviewed prior art on GitHub:

### A. anthropics/skills (133k stars)
- **Manifest**: `SKILL.md` with YAML frontmatter (`name`, `description` only).
- **Distribution**: Claude Code plugin marketplace command:
  `/plugin marketplace add anthropics/skills` then
  `/plugin install <skill>@<marketplace>`.
- **Spec**: `agentskills.io` (Agent Skills standard).
- **Discovery**: github topic tag `agent-skills`.
- **Strength**: minimum viable schema — just two fields. The plain folder
  contract is dead-simple to mirror.

### B. Other patterns surveyed
- **VSCode extensions** — `publisher.id@version`, manifest = `package.json`
  with `engines.vscode` + `activationEvents` + `contributes`.
- **Homebrew taps** — `brew tap user/repo` then `brew install user/repo/pkg`.
  Decentralised, every tap is just a git repo.
- **Ollama model library** — central registry behind `ollama pull <name>`.
  Single source of truth, signed manifests.
- **LangChain Hub** — `langchain hub pull org/prompt` with versioned prompts.
- **PraisonAI / AutoGen plugin registry** — Python entrypoint via setuptools
  `[project.entry-points."praisonai.tools"]` table.

### Recommended adoption path for OctoAgent
1. **Manifest schema** (minimal, copy anthropics/skills):
   ```yaml
   # SKILL.md frontmatter
   name: my-skill
   version: 0.1.0
   description: one paragraph
   trigger_keywords: [...]    # optional
   requires: ["python>=3.10"] # optional
   ```
2. **Storage convention**: `skills/public/<name>/SKILL.md` already matches.
3. **Discovery API** (server-side, two endpoints):
   - `GET /api/skills/search?q=&topic=agent-skills` — proxy GitHub Search
     `?q=topic:agent-skills <q>` with 1h cache.
   - `GET /api/skills/inspect?repo=org/repo&path=skills/foo` — fetch raw
     `SKILL.md`, parse frontmatter, return + a sha256 of contents.
4. **Install pipeline** (idempotent):
   1. shallow-clone repo to `/tmp/skill-stage-<uuid>`.
   2. verify `SKILL.md` parses; reject if `name` collides with installed skill
      unless `--force`.
   3. resolve `requires` against current Python + system; refuse if unmet.
   4. `rsync` to `skills/public/<name>/`; record sha256 in
      `workspace/skills_manifest.json`.
   5. invalidate skill registry in-process (hot-reload).
5. **Uninstall**: delete directory + remove manifest entry. No DB writes.
6. **Trust model** (start with simplest):
   - Allowlist of repo owners stored in `config.yaml` (e.g. `anthropics`,
     `octoagent-org`, plus operator-added).
   - SHA-256 pinning per skill, re-verify on hot-reload.
7. **UI surface**: integrate into the existing `find-skills` skill — it
   becomes the entrypoint that calls `/api/skills/search` and renders
   results, with a one-click install button that POSTs to `/api/skills/install`.

### Rejected alternatives
- Building a centralised registry (too much infra; GitHub search is enough).
- Signed binary skills (not needed — skills are plaintext markdown + scripts).
- pip-style packages (kills the human-readable SKILL.md contract).
