# OctoAgent 模块 Owner 矩阵

> 版本：2026-05-26
> 状态：**生效（Phase 0 拓扑冻结基准）**
> 配套文件：[`TOPOLOGY_FREEZE_2026-05-26.md`](TOPOLOGY_FREEZE_2026-05-26.md)

## 1. 目的

把 `backend/src/` 下 47 个顶层目录 + 12 个顶层 `.py` 文件（共 ~84K LoC）收敛为 **8 个语义清晰的域**。本矩阵是后续所有重构（Phase 1-9）的事实基准。

## 2. 目标拓扑（8 域）

```
backend/src/
├── runtime/        # 进程生命周期 / 配置 / 身份 / 治理 / OOM / 引导
├── agents/         # Agent 装配 / Middleware 链 / SubAgent / 内存
├── tools/          # 工具目录 / 内建工具 / MCP / 沙箱（含浏览器） / 系统执行
├── harness/        # Hook / Budget / RunJournal / Reflection / Evaluation / Orchestration
├── gateway/        # FastAPI 入口 / Router / Channel / WS / 监控 / Trace
├── storage/        # Brain 记忆 / RAG / Query / TaskWorkspace / Workflow / Skill / SelfEvolution
├── governance/     # AuthN/AuthZ / 多租户 / Operator / 用户账户
└── interfaces/     # PythonSDK / EmbeddedClient / Studio / Research / DistributedExec / InterfaceLayer
```

## 3. Owner 矩阵

每个域有：**主负责人（Primary）**、**副负责人（Backup）**、**当前合并/迁移决策**。
（注：本仓库目前是单人维护，Primary/Backup 暂记为 `@operator`；引入团队后即时填写。）

### 3.1 `runtime/`（目标 LoC ≈ 6K）

| 字段 | 值 |
|---|---|
| Primary | `@operator` |
| Backup | `@operator` |
| 职责 | 进程启停、systemd 集成、运行期配置、身份、写路径修复、OOM 守护、工件生命周期、上下文预算、引导冷启动 |
| 当前 LoC | 6,361 |

**迁移清单（源 → 目标）**：

| 源 | 目标 | 决策 |
|---|---|---|
| `backend/src/bootstrap/` | `runtime/bootstrap/` | 直接移动 |
| `backend/src/config/` | `runtime/config/` | 直接移动 |
| `backend/src/ml_intern_defaults/` | `runtime/config/ml_intern_defaults.py` | 折叠为单文件 |
| `backend/src/runtime_config.py` | `runtime/config/effective.py` | 重命名 |
| `backend/src/runtime_governance.py` | `runtime/governance.py` | 直接移动 |
| `backend/src/runtime_identity.py` | `runtime/identity.py` | 直接移动 |
| `backend/src/runtime_oom_guard.py` | `runtime/oom_guard.py` | 直接移动 |
| `backend/src/runtime_permissions.py` | `runtime/permissions.py` | 直接移动 |
| `backend/src/artifact_lifecycle.py` | `runtime/artifact_lifecycle.py` | 直接移动 |
| `backend/src/context_budget.py` | `runtime/context_budget.py` | 直接移动 |
| `backend/src/system_guard/` | `runtime/system_guard/` | 直接移动 |
| `backend/src/architecture.py` | `runtime/architecture.py` | 直接移动（保留模块分类清单） |

### 3.2 `agents/`（目标 LoC ≈ 17K）

| 字段 | 值 |
|---|---|
| Primary | `@operator` |
| Backup | `@operator` |
| 职责 | Lead Agent 装配、25 个 Middleware、SubAgent 调度、Agent 内存、Checkpointer、对话路由 |
| 当前 LoC | 16,694（含子合并） |

**迁移清单**：

| 源 | 目标 | 决策 |
|---|---|---|
| `backend/src/agents/` | `agents/` | 原地保留 |
| `backend/src/subagents/` | `agents/subagents/` | 移入 |
| `backend/src/generic_agent/` | `agents/generic/` | 移入并降级（仅 132 LoC，作为参考实现） |
| `backend/src/agent_core/` | `agents/core/` | **合并审查**：与 `agents/` 内部 `lead_agent/` 存在职责重叠，需在 Phase 7 解决 |
| `backend/src/agent_runtime/` | `agents/runtime/` | **合并审查**：同上 |

⚠️ `agent_core` / `agent_runtime` / `agents` 三模块的去重是 Phase 7 的核心工作量之一。Phase 0 仅冻结目录结构，**不动代码**。

### 3.3 `tools/`（目标 LoC ≈ 10K）

| 字段 | 值 |
|---|---|
| Primary | `@operator` |
| Backup | `@operator` |
| 职责 | 工具注册、内建工具、MCP 提供方、能力策略、软件接口、沙箱（Local/Docker/K8s/Browser）、系统执行 |
| 当前 LoC | 10,439 |

**迁移清单**：

| 源 | 目标 | 决策 |
|---|---|---|
| `backend/src/tools/` | `tools/` | 原地保留 |
| `backend/src/tools_registry/` | `tools/registry/` | 移入 |
| `backend/src/mcp/` | `tools/mcp/` | 移入 |
| `backend/src/capability_core/` | `tools/capability/` | 移入 |
| `backend/src/software_interfaces/` | `tools/software_interfaces/` | 移入 |
| `backend/src/plugins/` | `tools/plugins/` | 移入 |
| `backend/src/sandbox/` | `tools/sandbox/` | 移入 |
| `backend/src/system_execution/` | `tools/system_execution/` | 移入 |
| `backend/src/browser_runtime/` | `tools/sandbox/browser/` | 移入并降级为子驱动（Phase 4 沙箱收敛预备） |

### 3.4 `harness/`（目标 LoC ≈ 4K）

| 字段 | 值 |
|---|---|
| Primary | `@operator` |
| Backup | `@operator` |
| 职责 | Hook 调度、Budget 守护、Run Journal、生命周期清扫、Reflection、Evaluation、Orchestration |
| 当前 LoC | 4,069 |

**迁移清单**：

| 源 | 目标 | 决策 |
|---|---|---|
| `backend/src/harness/` | `harness/` | 原地保留 |
| `backend/src/hook_core/` | `harness/hook_core/` | 移入（与 `harness/hooks.py` 合并审查） |
| `backend/src/reflection/` | `harness/reflection/` | 移入 |
| `backend/src/evaluation/` | `harness/evaluation/` | 移入 |
| `backend/src/orchestration/` | `harness/orchestration/` | 移入 |

⚠️ `hook_core/` 与 `harness/hooks.py` 双钩子注册路径是已知技术债（本周回归 `d6c5f5a`）。Phase 6 / 7 中合并为单一注册面。

### 3.5 `gateway/`（目标 LoC ≈ 15K）

| 字段 | 值 |
|---|---|
| Primary | `@operator` |
| Backup | `@operator` |
| 职责 | FastAPI 应用 / 38 个 router 组 / 上传 / 渠道桥接 / Prometheus 指标 / Tool Trace |
| 当前 LoC | 14,950 |

**迁移清单**：

| 源 | 目标 | 决策 |
|---|---|---|
| `backend/src/gateway/` | `gateway/` | 原地保留 |
| `backend/src/channels/` | `gateway/channels/` | 移入 |
| `backend/src/channel_sdk/` | `gateway/channel_sdk/` | 移入 |
| `backend/src/monitoring/` | `gateway/monitoring/` | 移入 |
| `backend/src/observability/` | `gateway/observability/` | 移入 |

### 3.6 `storage/`（目标 LoC ≈ 17K）

| 字段 | 值 |
|---|---|
| Primary | `@operator` |
| Backup | `@operator` |
| 职责 | Brain 记忆、RAG、Query Engine、TaskWorkspace、Workflow 引擎、Skill 注册与演化、SelfEvolution、Optimization、Session Compaction |
| 当前 LoC | 16,478 |

**迁移清单**：

| 源 | 目标 | 决策 |
|---|---|---|
| `backend/src/brain/` | `storage/brain/` | 移入 |
| `backend/src/rag/` | `storage/rag/` | 移入 |
| `backend/src/query_engine/` | `storage/query/` | 移入 |
| `backend/src/task_workspaces/` | `storage/task_workspaces/` | 移入 |
| `backend/src/workflow_core/` | `storage/workflow/` | 移入 |
| `backend/src/skills/` | `storage/skills/` | 移入 |
| `backend/src/skill_evolution/` | `storage/skill_evolution/` | 移入 |
| `backend/src/self_evolution/` | `storage/self_evolution/` | 移入 |
| `backend/src/optimization_program/` | `storage/optimization/` | 移入 |
| `backend/src/session_compaction/` | `storage/session_compaction/` | 移入 |

⚠️ `skill_evolution` / `self_evolution` / `optimization_program` 三块自演化逻辑边界不清，Phase 7 需要重新画线。

### 3.7 `governance/`（目标 LoC ≈ 1.5K）

| 字段 | 值 |
|---|---|
| Primary | `@operator` |
| Backup | `@operator` |
| 职责 | 模型凭证、多租户、Operator 审计、用户账户 |
| 当前 LoC | 1,430 |

**迁移清单**：

| 源 | 目标 | 决策 |
|---|---|---|
| `backend/src/model_auth/` | `governance/model_auth/` | 移入 |
| `backend/src/multi_tenant/` | `governance/multi_tenant/` | 移入 |
| `backend/src/operator_governance/` | `governance/operator/` | 移入 |
| `backend/src/user_accounts/` | `governance/users/` | 移入 |

### 3.8 `interfaces/`（目标 LoC ≈ 3K）

| 字段 | 值 |
|---|---|
| Primary | `@operator` |
| Backup | `@operator` |
| 职责 | 嵌入式 Python 客户端、Python SDK、Studio 编排运行时、Research 运行时、分布式执行节点、接口契约层 |
| 当前 LoC | 2,898 |

**迁移清单**：

| 源 | 目标 | 决策 |
|---|---|---|
| `backend/src/client.py` | `interfaces/embedded/client.py` | 移入 |
| `backend/src/client_agent.py` | `interfaces/embedded/agent.py` | 移入 |
| `backend/src/client_streaming.py` | `interfaces/embedded/streaming.py` | 移入 |
| `backend/src/python_sdk/` | `interfaces/python_sdk/` | 移入 |
| `backend/src/interface_layer/` | `interfaces/contracts/` | 移入 |
| `backend/src/studio_runtime/` | `interfaces/studio/` | 移入 |
| `backend/src/research_runtime/` | `interfaces/research/` | 移入 |
| `backend/src/distributed_execution/` | `interfaces/distributed/` | 移入（Phase 6 扩展为简易 dispatcher） |

### 3.9 共享层（不计入 8 域）

| 源 | 目标 | 决策 |
|---|---|---|
| `backend/src/utils/` | `backend/src/utils/` | 保持 |
| `backend/src/community/` | `backend/src/community/` | 保持（第三方贡献兼容层） |
| `backend/src/__init__.py` | 保持 | |

## 4. 跨域调用规则（依赖方向）

允许的依赖方向（**只允许从上往下调用，禁止反向**）：

```
interfaces ─┐
            ├──► gateway ──► agents ──► harness ──► tools ──► storage ──► runtime
governance ─┘                                                                ▲
                                                                             │
                            utils / community （任意域可调用） ───────────────┘
```

**强制约束**：

1. `runtime/` 不得 import 任何其他 8 域代码（仅可 import `utils/`）。
2. `tools/` 不得 import `agents/` 或 `harness/`。
3. `agents/` 通过 `harness/` 的 Hook 注册面调用 Middleware，不得直接 import `harness/budget.py` 等具体实现。
4. `gateway/` 是唯一允许导入 `agents/` 的入口域。
5. `interfaces/` 通过 HTTP/WS 与 `gateway/` 通信，**不得**直接 import `agents/` / `harness/` / `tools/`。

CI 检查（Phase 1 落地）：用 `import-linter` 或 `tach` 工具锁定上述规则，违反则 build fail。

## 5. 命名规范

- 每个域根目录有 `__init__.py` 提供**公共 API**（`__all__` 显式声明），跨域调用只能用公共 API。
- 域内子目录 snake_case，单元文件 snake_case。
- 不再出现 `*_core` / `*_runtime` 后缀（这两个后缀语义模糊，已是当前混乱来源）。

## 6. 例外审批

任何新增顶层目录、跨域反向调用、模块拆分，必须：

1. 在本文档新增一行决策记录；
2. 在 [`TOPOLOGY_FREEZE_2026-05-26.md`](TOPOLOGY_FREEZE_2026-05-26.md) 的例外清单签字；
3. 通过 CI `import-linter` 规则更新。

未走流程的改动在 CI 阶段直接拒绝。

## 7. 不在本矩阵范围内

- 前端目录（`frontend/src/`）：将在 Phase 2 单独输出 `MODULE_OWNERS_FRONTEND.md`。
- `scripts/` / `runtime/` / `workspace/` / `deploy/` / `docker/`：运维资产，由 [`scripts/README.md`](../../scripts/README.md) 治理（待补）。

## 8. 修订记录

| 日期 | 版本 | 修订 |
|---|---|---|
| 2026-05-26 | v1.0 | Phase 0 首次发布，47 模块 → 8 域映射 |
