# OctoAgent 拓扑冻结声明（2026-05-26）

> 状态：**生效**
> 主文档：[`MODULE_OWNERS.md`](MODULE_OWNERS.md)
> 解冻日期：2026-08-31（Phase 7 完成时随物理合并解冻并重新发布 v2.0）

## 1. 冻结范围

自 **2026-05-26 起**，`backend/src/` 顶层目录拓扑进入冻结期。冻结规则：

### 1.1 禁止动作

- ❌ **新增**任何 `backend/src/` 顶层目录（即 `backend/src/<NEW_DIR>/`）。
- ❌ **重命名**任何 `backend/src/` 顶层目录。
- ❌ **新增** `backend/src/*.py` 顶层文件（必须放进既有顶层目录或新建符合 8 域规范的子目录）。
- ❌ **跨 8 域的反向依赖**（依赖方向见 `MODULE_OWNERS.md` §4）。
- ❌ 在合并完成前，**禁止**对 `agent_core` / `agent_runtime` / `agents` / `generic_agent` 四个重叠模块做大规模 API 变更（仅允许 bug fix）。

### 1.2 允许动作

- ✅ 在既有顶层目录**内部**重组（子目录新增、文件合并、内部重命名）。
- ✅ 修复缺陷、添加测试、添加文档。
- ✅ 在 `tools/builtins/` 下新增内建工具（这是 Phase 8 SMB 垂直能力扩展的预留入口）。
- ✅ 在 `gateway/routers/` 下新增 router（需在 `MODULE_OWNERS.md` 记录）。

### 1.3 冻结结束条件

以下三个条件**全部满足**后，冻结结束并发布 `TOPOLOGY_v2.0`：

1. Phase 7（模块物理合并）完成，`backend/src/` 顶层从 47 个目录 + 12 个文件收敛到 8 个目录 + 2 个共享目录（`utils/` + `community/`）+ `__init__.py`。
2. CI `import-linter` / `tach` 锁定 8 域依赖图通过。
3. 全套件回归（`make release-readiness`）通过。

## 2. 例外清单

任何冻结期内的例外都必须在此登记，**未登记的改动一律退回**。

| 日期 | 改动 | 申请人 | 审批 | 理由 |
|---|---|---|---|---|
| — | — | — | — | （空） |

## 3. 当前快照

冻结时刻的 `backend/src/` 顶层目录清单：

```
agent_core/        agent_runtime/     agents/            bootstrap/
brain/             browser_runtime/   capability_core/   channels/
channel_sdk/       community/         config/            distributed_execution/
evaluation/        gateway/           generic_agent/     harness/
hook_core/         interface_layer/   mcp/               ml_intern_defaults/
model_auth/        models/            monitoring/        multi_tenant/
observability/     operator_governance/  optimization_program/  orchestration/
plugins/           python_sdk/        query_engine/      rag/
reflection/        research_runtime/  sandbox/           self_evolution/
session_compaction/  skill_evolution/  skills/           software_interfaces/
studio_runtime/    subagents/         system_execution/  system_guard/
task_workspaces/   tools/             tools_registry/    user_accounts/
utils/             workflow_core/
```

顶层 `.py` 文件：

```
architecture.py    artifact_lifecycle.py    client.py            client_agent.py
client_streaming.py    context_budget.py    runtime_config.py    runtime_governance.py
runtime_identity.py    runtime_oom_guard.py    runtime_permissions.py    __init__.py
```

总计 47 个目录 + 12 个文件 + `__init__.py`。

## 4. 强制执行

### 4.1 CI Hook（Phase 1 落地）

```yaml
# .github/workflows/topology-freeze.yml
- name: Check topology freeze
  run: |
    python scripts/check_topology_freeze.py
```

`scripts/check_topology_freeze.py` 比对当前 `backend/src/` 顶层目录与 §3 快照清单：

- 新增顶层目录/文件 → exit 1
- 重命名 → exit 1
- 允许：内部子目录变化、内部文件变化

### 4.2 PR 模板

新增 `.github/pull_request_template.md` 段落：

```markdown
## 拓扑冻结检查
- [ ] 本 PR **未**新增 backend/src/ 顶层目录或顶层 .py 文件
- [ ] 如果新增，已在 TOPOLOGY_FREEZE_2026-05-26.md §2 登记例外
- [ ] 跨域 import 已检查（参照 MODULE_OWNERS.md §4）
```

## 5. 关联 Phase 路线

| Phase | 是否依赖本冻结 | 备注 |
|---|---|---|
| Phase 1（配置整治） | ✅ | 新增 `runtime/config/effective.py` 在 §3.1 已预留 |
| Phase 2（前端状态机） | ❌ | 前端独立，不受影响 |
| Phase 3（测试重构） | ✅ | 测试目录跟随源目录结构 |
| Phase 4（沙箱 + Trace） | ✅ | `browser_runtime/` → `tools/sandbox/browser/` 在 §3.3 已预定 |
| Phase 5（安装器） | ❌ | 仅 scripts/ 改动 |
| Phase 6（分布式 Dispatcher） | ✅ | `distributed_execution/` → `interfaces/distributed/` 在 §3.8 已预定 |
| Phase 7（物理合并 + LOC 精简） | ✅ | **本冻结的执行阶段，完成后解冻** |
| Phase 8（SMB 垂直能力） | ❌ | 仅在 `tools/builtins/` 与 `gateway/routers/` 扩展 |
| Phase 9（文档 + GitHub 同步） | ✅ | 同步 v2.0 拓扑 |

## 6. 修订记录

| 日期 | 版本 | 修订 |
|---|---|---|
| 2026-05-26 | v1.0 | 拓扑冻结生效，47 目录基线 |
