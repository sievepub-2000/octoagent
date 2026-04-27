# Autoresearch 优化计划

## 目标

把当前分析转换为 autoresearch 可以消费的量化目标。重点不是“全仓无界自动改”，而是建立一个统一指标、统一淘汰策略、统一 API 暴露面的优化程序。

## FastAPI 统一接口

新增统一只读接口：

- `GET /api/optimization/program`
- `GET /api/optimization/roadmap`
- `GET /api/optimization/scorecard`
- `GET /api/optimization/metrics`

用途：

1. 让 WebUI、CLI、外部脚本和 autoresearch 读取同一套优化目标。
2. 避免文档、脚本、人工口径出现三套标准。

## 竞品对照基线

### OpenAkita 对照点

- 平台治理：skills / MCP / hooks / plugins / evaluation 组织方式更成熟。
- 优化目标：OctoAgent 必须在统一 capability registry、统一观测接口、统一绑定 contract 上更强。

### Hermes Agent Solution Template 对照点

- durable workflow、wait/signal、人审状态词汇和审计语义更明确。
- 优化目标：OctoAgent 必须在 task_workspaces 单真值上实现更完整的 runtime timeline、checkpoint、hook event、builder transaction 关联。

## 可量化目标

| 指标 ID | 指标名 | 命令/来源 | 方向 | 当前基线 | 目标值 | 对照标准 |
| --- | --- | --- | --- | ---: | ---: | --- |
| M-001 | 平台审计总分 | `/api/optimization/scorecard` | 越高越好 | 66 | 85 | 必须高于 OpenAkita 平台治理综合线 |
| M-002 | Runtime Truth 得分 | `/api/optimization/scorecard` | 越高越好 | 15/20 | 19/20 | 必须优于 Hermes 风格 durable contract 一致性 |
| M-003 | Capability & Hook 治理得分 | `/api/optimization/scorecard` | 越高越好 | 9/15 | 14/15 | 必须高于 OpenAkita 风格目录治理成熟度 |
| M-004 | 前端构建成功率 | `pnpm -C frontend build` | 越高越好 | 100% | 100% | 不允许回退 |
| M-005 | 后端关键回归通过率 | `backend/.venv/bin/python -m pytest ...` | 越高越好 | 100% | 100% | 不允许回退 |
| M-006 | 关键 API P95 延迟 | 后续 benchmark 命令 | 越低越好 | 待建立 | 基线下降 20% | 必须优于当前 OctoAgent 基线 |
| M-007 | task-workspace-board 复杂度代理 | 组件文件行数 + 逻辑分层检查 | 越低越好 | 待建立 | 降低 30% | 必须明显优于当前实现 |

## 推荐的 autoresearch 首轮设置

### 建议目标

提高“平台审计总分”，同时保持构建与关键测试 100% 通过。

### 建议度量命令

统一测量脚本现已确定为：

```bash
backend/.venv/bin/python backend/scripts/run_optimization_scorecard.py --format json
```

脚本要求：

1. 输出可机器读取的总分、分维度分、coverage 缺口、验证命令结果。
2. 主动检查是否有未纳入优化计划的代码目录。
3. 默认把前端 build、后端关键回归和真实 WebUI smoke 作为 scorecard gate。

输出字段建议：

```json
{
  "total_score": 66,
  "runtime_truth": 15,
  "durability": 11,
  "capability_hook_governance": 9,
  "frontend_state_architecture": 6,
  "test_and_release_gates": 11,
  "performance_efficiency": 5,
  "docs_alignment": 3,
  "competitive_superiority": 6
}
```

### 建议作用范围

第一轮只允许修改以下范围：

- backend/src/workflow_core
- backend/src/task_workspaces
- backend/src/agent_core
- backend/src/capability_core
- backend/src/hook_core
- backend/src/gateway
- frontend/src/core/task-workspaces
- frontend/src/components/workspace
- project_docs/docs

### 不允许修改的范围

- third-party imported docs
- node_modules / .venv / workspace runtime state
- docker 镜像依赖与系统级环境

## 淘汰策略

任一实验命中以下条件即淘汰：

1. `pnpm -C frontend build` 失败。
2. 后端关键回归测试失败。
3. 审计总分未提升且复杂度显著增加。
4. 新增第二套 workflow truth source。
5. API 契约回退或前端页面改为依赖临时 payload。
6. 性能提升小于 3%，但引入新的耦合、依赖或不可解释行为。

## 保留策略

改动只在同时满足以下条件时保留：

1. 指标改善。
2. 构建和关键测试不回退。
3. 文档与 `/api/optimization/*` 输出同步更新。
4. 复杂度变化可解释。

## 当前建议

不要把“优化整个项目的所有模块”当成单轮 autoresearch 目标。正确做法是：

1. 先用统一 scorecard 建立基线。
2. 按模块组逐轮迭代。
3. 每轮只优化一个可测切片，并执行 keep / discard。