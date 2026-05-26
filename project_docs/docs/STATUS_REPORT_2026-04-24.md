# OctoAgent 状态报告 2026-04-24

本报告汇总本轮工作进度，按 R1（Git 仓库同步）+ P1/P2/P3 待办事项展开。

## R1 · GitHub 仓库同步（✅ 完成）

- 目标：更新开发 PAT、完成本地与远端全部文件同步。
- 新 PAT：`ghp_[REDACTED_2026-05-16]`（已写入 `~/.git-credentials`）。
- 远端别名：`github-sievepub` → `ssh.github.com:443`，私钥 `~/.ssh/id_ed25519_sievepub`。
- 策略：本地 `.git` 有残留损坏 blob，直接 push 会断裂；采用 **snapshot-push** —— `git archive HEAD | tar -x -C /tmp/snap`，rsync 至纯净仓库后统一 commit+push。
- 远端 `main` HEAD：`417fb91e`（上一轮已推送）。
- 本轮新增 diff（即将在下一次 snapshot-push 带入远端，见下文"同步计划"章节）：

```
 M backend/src/gateway/routers/memory.py
 M backend/src/gateway/routers/tools_registry.py
 M backend/src/tools/catalog.py
 M frontend/src/app/workspace/config/evolution/page.tsx
 M frontend/src/app/workspace/config/tools/page.tsx
?? frontend/scripts/desktop_control_filter_smoke.cjs
?? frontend/scripts/desktop_control_smoke.cjs
?? frontend/scripts/i18n_5locale_smoke.cjs
?? frontend/scripts/trust_scores_smoke.cjs
?? workspace/default/memory.legacy.json
?? workspace/default/memory.v2.json
```

## P1a · Bytebot Desktop Control 观察通道（✅）

- 后端：`backend/src/tools/catalog.py` 引入 `_bytebot_compat_enabled()`，`load_builtin_tools()` 条件挂载 `BYTEBOT_COMPAT_TOOLS`。默认关闭（tool count 46），`BYTEBOT_COMPAT_ENABLED=1` 后变为 52。
- API：`GET /api/tools/desktop-control/status` 返回 `{category:"desktop-control", badge:"stub", enabled:false, env_flag:"BYTEBOT_COMPAT_ENABLED", tools:[6 entries]}`。
- UI：`/workspace/config/tools` 渲染 Desktop Control 分类 6 行，`badge=stub` + `disabled`；Playwright 截图 `/tmp/desktop-control-tools-hub.png`、`/tmp/desktop-control-filtered.png` 均确认。

## P1b · Skill Trust-Score 观察面板（✅）

- UI：`/workspace/config/evolution` 新增 Trust Scores 标签页，`data-testid="trust-scores-panel"`。
- 观察开关：`SKILL_TRUST_OBSERVATION_ENABLED`，默认关闭；面板显示 `Observation: off` 徽章 + 禁用提示。
- i18n：`TRUST_SCORES_I18N` 覆盖 en-US / zh-CN / zh-TW / ja / ko。
- 截图：`/tmp/trust-scores-panel.png`。

## P2 · i18n 5 语言 + Memory v2 桥接（✅）

- i18n：`DESKTOP_CATEGORY_LABEL_I18N` 与 `TRUST_SCORES_I18N` 均为 5 语言完整映射，Playwright 5 locale 切换截图 `/tmp/trust-{en-US,zh-CN,zh-TW,ja,ko}.png` 均正确渲染。
- Memory v2：
  - 脚本 `backend/scripts/migrate_memory_schema.py --memory workspace/default/memory.json` 已实际执行，写出 `memory.v2.json` 和 `memory.legacy.json` 备份。
  - 新增 endpoint `GET /api/memory/schema-status`，容错处理空 `storage_path` 与相对路径，按候选列表搜索。
  - HTTP 验证：

    ```json
    {
      "storage_path": "../workspace/default/memory.json",
      "schema_version": "1.0",
      "v2_available": true,
      "legacy_backup_present": true,
      "prefer_v2": false,
      "note": "..."
    }
    ```

  - 运行时 normalizer 同时兼容 v1/v2；`MEMORY_PREFER_V2=1` 仅作为观察报告标记，不改默认行为。

## P3 · Fallback Pool Stress（观察 OK）

- `GET /api/fallback-pool/status`（无 key）：

  ```json
  {
    "enabled": false,
    "reason": "NVIDIA_API_KEY / FREE_CLAUDE_CODE_API_KEY not set; pool disabled.",
    "api_key_present": false,
    "operator_override": false,
    "pool_models": ["nvidia-llama-3.3-70b", "nvidia-deepseek-r1", "nvidia-qwen2.5-coder-32b"]
  }
  ```

- 观察结论：禁用状态正确暴露原因与 operator_override 标志。注入 `FREE_CLAUDE_CODE_API_KEY` 需重启 gateway 进程（curl 前置 env 只作用于 curl 自身），后续可做一次带 env 的完整启动验证作为回归。

## 未完项（下一轮优先级）

1. `/workspace/config/memory` 页添加 `MemorySchemaStatusCard` UI（endpoint 已就位，仅缺前端卡片 + 5 语言文案 + build/截图）。
2. 带 `FREE_CLAUDE_CODE_API_KEY=test-key` 重启 gateway，验证 fallback-pool `enabled=true` 且 operator override 保留策略。
3. Playwright vs Agent Browser 5 场景 bench（selector 稳定性、headless 性能、网络控制、MCP 集成、错误恢复）。
4. 下一次 snapshot-push 至 `sievepub-2000/octoagent`，同步本轮新增 11 个修改/新增文件。

## 同步计划

执行顺序：
1. `git add -A && git commit -m "feat: bytebot stub mount + trust-score/memory-schema observation + 5-locale i18n"`
2. snapshot-push：
   - `rm -rf /tmp/snap && mkdir /tmp/snap && git archive HEAD | tar -x -C /tmp/snap`
   - `rsync -a --delete /tmp/snap/ /tmp/octoagent-pure/`（pure clone）
   - pure repo 内 `git add -A && git commit && git push github-sievepub main`
3. 完成后重跑 `curl` / WebUI 校验 + 更新 `/memories/repo/git-publish-migration.md`。

## 证据索引

| 项 | 证据 |
|---|---|
| R1 remote HEAD | `417fb91e` |
| tool count toggle | 46 → 52（BYTEBOT_COMPAT_ENABLED=1） |
| `/api/tools/desktop-control/status` | 见 P1a JSON 片段 |
| `/api/memory/schema-status` | 见 P2 JSON 片段，v2 + legacy 皆 true |
| `/api/fallback-pool/status` | 见 P3 JSON 片段 |
| i18n 5 locale 截图 | `/tmp/trust-en-US.png` 等 5 张 |
| Desktop Control 截图 | `/tmp/desktop-control-tools-hub.png` |
| Trust Score 截图 | `/tmp/trust-scores-panel.png` |

## 补充更新（2026-04-24 第二轮闭环）

本节为本会话后续执行的闭环补充，覆盖此前未完项 1/2/3。

### A. Memory Schema UI 卡片落地（✅ 完成）

- 页面已接入 `MemorySchemaStatusCard`：
  - `frontend/src/app/workspace/config/memory/page.tsx`
  - `frontend/src/components/workspace/settings/memory-schema-status-card.tsx`
- 卡片具备 5 语言文案（en-US / zh-CN / zh-TW / ja / ko）和以下状态徽章：
  - `schema_version`
  - `v2_available`
  - `legacy_backup_present`
  - `prefer_v2`
- 真实 WebUI 校验截图（19880 入口）：
  - `screenshots/2026-04-24/memory-schema-card.png`
  - `screenshots/2026-04-24/memory-schema-en-US.png`
  - `screenshots/2026-04-24/memory-schema-zh-CN.png`
  - `screenshots/2026-04-24/memory-schema-zh-TW.png`
  - `screenshots/2026-04-24/memory-schema-ja.png`
  - `screenshots/2026-04-24/memory-schema-ko.png`

### B. FREE_CLAUDE_CODE_API_KEY Stress 验证（✅ 完成）

- 验证步骤：
  1. 清理旧 gateway 进程。
  2. 带 `FREE_CLAUDE_CODE_API_KEY=test-stress-key-xxx` 启动 gateway。
  3. 验证 `/api/fallback-pool/status` 返回 `enabled=true`、`api_key_present=true`、`operator_override=false`。
  4. 无 key 重启 gateway 并验证恢复到 `enabled=false`。
- 固化证据：
  - `project_docs/docs/artifacts/2026-04-24/fallback_status_with_key.json`
  - `project_docs/docs/artifacts/2026-04-24/fallback_status_after_restore.json`

### C. Playwright vs Agent Browser 5 场景 Bench（✅ 完成）

- 运行脚本：`frontend/scripts/playwright_vs_agent_browser_bench.cjs`
- 5 场景结果摘要：

| 场景 | Playwright | Agent Browser |
|---|---|---|
| selector_stability | pass=5/5, avg=2491ms | pass=5/5, avg=975ms |
| headless_performance | runs=5, avg=2496ms | runs=5, avg=516ms |
| network_control | intercepted_requests=27, route_hook_ok=true | domain_guard_blocked=true |
| mcp_integration | mcp_page_ok=true | capabilities_ok=true, provider_agent_browser_present=true |
| error_recovery | timeout_error_captured=true | recover_flow_ok=true |

- 结果工件：
  - `project_docs/docs/artifacts/2026-04-24/playwright_vs_agent_browser_bench.json`
  - `project_docs/docs/artifacts/2026-04-24/playwright_vs_agent_browser_bench.md`
  - `screenshots/2026-04-24/bench-mcp-page.png`

### D. 额外审计说明

- 在 stress 过程中发现旧 shell 链式命令存在目录漂移与后台进程残留风险（`~/public-workspace` 与 `~/public-workspace/octoagent` 之间切换导致路径失效）。
- 已采用“先全量 `pkill -f 'uvicorn src.gateway.app:app'` 再按 `--app-dir` 显式重启”的方式固定恢复流程。
- 当前最终状态已回到无 key 基线（`enabled=false`）。
