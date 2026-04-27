# 模块优先级重构路线图

## 目标

本路线图把当前代码分析收敛成可执行的模块优先级重构顺序。原则只有三条：

1. 先收口运行时真值，再做产品扩展。
2. 先降低高耦合高回归面，再做性能和竞品超越。
3. 每一阶段都必须有量化验收，而不是“代码看起来更干净”。

## 优先级分层

| 优先级 | 模块组 | 当前判断 | 核心问题 | 阶段目标 | 完成标准 |
| --- | --- | --- | --- | --- | --- |
| P0 | workflow_core + task_workspaces + agent_core | 必须优先 | 真值链路分层过厚，执行与投影交织 | 收口唯一工作流真值、统一生命周期 summary、减少路由侧聚合 | task workspace 生命周期接口全部可追溯到单一 service 链 |
| P0 | query_engine + threads/runtime bridge | 必须优先 | 前端聊天流与 query planning 存在多状态源 | 统一 session planning、compact、handoff 输出契约 | 前端聊天主链只消费稳定 contract，不再依赖 heuristic |
| P1 | capability_core + hook_core + plugins + mcp + channels | 高优先 | 能力目录、hook、扩展管理面和运行时绑定仍有边界重叠 | 建立 capability registry / hook dispatch 统一面 | 技能、MCP、hooks、plugins、channels 可被同一 binding contract 消费 |
| P1 | system_execution + system_guard | 高优先 | 系统级副作用强，策略和恢复复杂 | 收紧权限策略、审计、超时、恢复流程 | 关键副作用路径均有审计事件、失败关闭和恢复验证 |
| P2 | frontend workspace shell + task board + settings | 中优先 | 单组件过大、状态源分散 | 降低页面级复杂度，统一 query key 与 polling | task board 拆出独立面板和可测 hooks，核心页面自动化覆盖建立 |
| P2 | models + bootstrap + evaluation | 中优先 | 模型回退、嵌入模型和评估面耦合度高 | 建立模型能力评分、fallback 和 benchmark 统一观测 | 模型选择逻辑可独立测量，评估输出可作为 autoresearch 指标输入 |
| P3 | desktop shell + operator surfaces + distributed execution | 后置 | 产品外延面已存在但成熟度不均衡 | 以统一 runtime contract 驱动外部面 | Desktop 与 operator surface 不再依赖隐式页面 payload |

## 分阶段实施

### 阶段 A: 运行时真值收口

### 范围

- backend/src/workflow_core
- backend/src/task_workspaces
- backend/src/agent_core
- backend/src/gateway/routers/task_workspaces.py

### 要做什么

1. 删除 router 层重复聚合逻辑，把 runtime summary、handoff、timeline、checkpoint 统一下沉到 workflow_core facade。
2. 缩减 task_workspaces execution 文件职责，把执行编排、失败判定、结果归档拆为独立策略函数或子模块。
3. 明确 task workspace、workflow projection、agent lifecycle 三者的写入顺序与唯一真源。

### 量化验收

- task workspace 生命周期接口 100% 可从 gateway 路由追踪到 workflow_core -> task_workspaces -> store。
- 与 runtime truth 相关的 router 逻辑代码减少 25% 以上。
- task_workspaces execution 单文件行数降低到 700 行以下，或至少拆出两个以上职责明确子模块。

### 阶段 B: 能力治理与 Hook 运行时统一

### 范围

- backend/src/capability_core
- backend/src/hook_core
- backend/src/plugins
- backend/src/mcp
- backend/src/channels
- frontend/src/app/workspace/config/*

### 要做什么

1. 统一能力目录 contract，把 skills、MCP、hooks、plugins、channels 收敛为 workflow-bindable metadata。
2. 把 hook 安装管理和 hook dispatch 语义分层，明确配置面与运行时面边界。
3. 建立统一 FastAPI 观测接口，输出 capabilities、runtime state、audit state。

### 量化验收

- `/api/capabilities/*`、`/api/hooks/*`、`/api/optimization/*` 三类接口均可由统一 registry / dispatch service 驱动。
- hook 失败关闭和超时隔离测试覆盖率达到 100% 的核心路径。
- settings 页面四类能力面共享统一 metadata schema。

### 阶段 C: 前端状态简化与可测性增强

### 范围

- frontend/src/components/workspace
- frontend/src/core/task-workspaces
- frontend/src/core/threads
- frontend/src/core/query-engine
- frontend/src/core/settings

### 要做什么

1. 把 task workspace board 拆成更小的面板与 hooks。
2. 清理 React Query key 与 polling 规则，减少重复 refetch 和 fallback state。
3. 为聊天、workflow、settings 主路径补浏览器自动化。

### 量化验收

- task-workspace-board 代码体积下降 30% 以上。
- 核心页面 hooks 单元测试与集成测试覆盖建立，P0 页面至少 6 条真实用户流。
- 前端 build 持续通过，类型错误为 0。

### 阶段 D: 性能与竞品超越

### 范围

- backend/src/models
- backend/src/evaluation
- backend/src/query_engine
- backend/src/system_guard
- backend/src/system_execution

### 要做什么

1. 建立统一的 benchmark / scorecard / autoresearch 输入输出格式。
2. 把 OpenAkita 优势能力映射为平台治理与扩展指标，把 Hermes 优势能力映射为 durable workflow 与 audit 指标。
3. 通过 autoresearch 做分模块可测优化，而不是“全仓无界优化”。

### 量化验收

- OctoAgent 平台治理、durability、auditability、extensibility 四项得分都高于竞品目标线。
- 关键 API P95 延迟较当前基线下降 20% 以上。
- release precheck 成功率稳定保持 100%。

## 重构淘汰策略

任何候选改动满足以下任一条件即淘汰：

1. 破坏现有 FastAPI 公共路由契约。
2. 让前端构建、后端关键测试或 smoke 失败。
3. 引入第二套 workflow truth source。
4. 指标没有改善却显著增加复杂度。
5. 性能改进低于 3%，但新增不可逆耦合或新依赖。

## 与竞品对照的超越方向

| 对照维度 | OpenAkita 强项 | Hermes 强项 | OctoAgent 目标 |
| --- | --- | --- | --- |
| 平台治理 | skills / MCP / hooks / plugins 目录清晰 | - | 单一 capability registry + FastAPI 统一观测面，比 OpenAkita 更易运维 |
| Durable workflow | - | wait / signal / auditability 强 | 在 task_workspaces 单真值下实现更细粒度事件审计与恢复 |
| 扩展绑定 | 多类能力可挂接 | durable execution 语义明确 | 保持现有 UI 结构下实现更完整 binding contract |
| 性能 | 平台能力强但本地运行未必更轻 | durable 语义强但执行栈偏厚 | 在单机入口、LangGraph-only 主线下做到更低延迟和更少层级 |

## 下一步执行建议

1. 先做阶段 A 和阶段 B 的 contract 收口。
2. 再以阶段 C 建立前端自动化与状态治理。
3. 最后再让 autoresearch 进入阶段 D 的分模块量化优化。