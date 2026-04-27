# 项目审计检查清单与评分表

## 使用方式

这份表用于版本审计、阶段交付和 autoresearch 验收。每个维度都要求：

1. 有明确检查项。
2. 有量化分数。
3. 有证据文件或命令。

总分 100 分。低于 70 分不得称为“稳定优化版本”。低于 60 分不得进入默认发布流。

## 评分维度

| 维度 | 权重 | 当前分 | 目标分 | 说明 |
| --- | ---: | ---: | ---: | --- |
| Runtime Truth 一致性 | 20 | 15 | 19 | workflow_core / task_workspaces / agent_core 是否保持单真值 |
| Workflow Durability | 15 | 11 | 14 | compile/run/checkpoint/pause/resume/terminate 与审计恢复能力 |
| Capability 与 Hook 治理 | 15 | 9 | 14 | skills/MCP/plugins/hooks/channels 的统一注册、绑定、审计能力 |
| Frontend 状态架构 | 10 | 6 | 9 | React Query、local state、LangGraph SDK、Gateway 状态是否清晰 |
| 测试与回归门禁 | 15 | 11 | 14 | 后端测试、前端构建、真实 WebUI smoke、关键路径集成测试 |
| 性能与资源效率 | 10 | 5 | 9 | 关键 API 延迟、构建耗时、运行时资源占用 |
| 文档与代码一致性 | 5 | 3 | 5 | 文档是否描述当前真实运行路径 |
| 扩展能力与竞品超越 | 10 | 6 | 10 | 相对 OpenAkita 与 Hermes 的功能密度和统一性 |

## 当前基线总分

当前总分：66 / 100

评估结论：

- 已具备强后端能力密度和较完整的任务工作流面。
- 仍处于“高能力、高复杂度、部分契约待收口”的状态。
- 不适合直接宣称全模块高成熟度自优化平台。

## 审计检查清单

### A. Runtime Truth 一致性

- [ ] `task_workspaces` 是否仍是 workflow 运行时唯一真值源。
- [ ] `workflow_core` 是否只做 facade / projection，而不是再造第二持久化层。
- [ ] `agent_core` 是否只通过统一 service 更新 workspace 状态。
- [ ] router 是否仍然存在本地 heuristic 聚合而非统一 service 调用。
- [ ] studio runtime / public runtime / task workspace 相关 contract 是否字段对齐。

评分标准：

- 0-8：存在多个真值源或严重重复聚合。
- 9-15：主线真值已基本统一，但仍有局部 heuristic。
- 16-20：所有相关面都由统一 service / projection 输出。

### B. Workflow Durability

- [ ] compile / run / pause / resume / terminate 是否都有统一状态流转。
- [ ] checkpoint、run log、result、artifacts 是否可回溯。
- [ ] timeline 是否支持审计与恢复时重建关键事件。
- [ ] 失败路径是否可观测且失败关闭。

评分标准：

- 0-6：生命周期语义不完整或恢复能力弱。
- 7-11：主路径可用，但审计或恢复仍不稳定。
- 12-15：durable workflow 语义完整并可被外部消费。

### C. Capability 与 Hook 治理

- [ ] skills、MCP、plugins、hooks、channels 是否已纳入统一 registry。
- [ ] hook 管理面与运行时 dispatch 是否清晰分层。
- [ ] capability runtime-state 与 audit 是否可通过 API 查询。
- [ ] 最小权限、失败关闭、超时隔离是否明确。

评分标准：

- 0-5：多模块各自为政。
- 6-10：已有 capability core 雏形，但统一 binding 不完整。
- 11-15：统一 registry、统一审计、统一权限语义全部落地。

### D. Frontend 状态架构

- [ ] task-workspace-board 是否职责过载。
- [ ] React Query key、polling、fallback state 是否可解释。
- [ ] 关键页面是否能明确说出状态源来自 SDK、Gateway 还是 localStorage。
- [ ] i18n、settings、system status 是否与 runtime truth 对齐。

评分标准：

- 0-3：状态源混杂且难测。
- 4-6：主路径可用，但复杂度偏高。
- 7-10：状态源清晰、组件职责合理、自动化验证充分。

### E. 测试与回归门禁

- [ ] 后端关键 router / service / contract 是否都有回归测试。
- [ ] 前端 build 是否始终通过。
- [ ] 真实 WebUI smoke 是否进入日常验收流。
- [ ] 前端聊天与 workflow 生命周期是否有真实浏览器测试。
- [ ] system_execution / system_guard / recovery 是否有专项回归。

评分标准：

- 0-6：仅有局部测试或无法支撑重构。
- 7-11：后端较强、前端偏弱。
- 12-15：全链路测试门禁清晰，烟测和集成测试都可重复。

### F. 性能与资源效率

- [ ] 关键 API 是否有基线测量。
- [ ] query_engine / task execution / model fallback 是否有耗时观测。
- [ ] frontend build 与关键页面首屏是否可量化。
- [ ] 自优化候选改动是否必须带指标对比。

评分标准：

- 0-3：基本无基线。
- 4-6：有局部感知，无统一指标。
- 7-10：有统一 benchmark、scorecard 和 keep/discard 规则。

### G. 文档与代码一致性

- [ ] README 是否仍描述当前 LangGraph-only 主线。
- [ ] project_docs 是否优先指向当前真相而非历史报告。
- [ ] 端口、入口、API 面是否与代码一致。

### H. 扩展能力与竞品超越

- [ ] 是否已经把 OpenAkita 的治理优势转为本项目内统一能力目录。
- [ ] 是否已经把 Hermes 的 durable / audit 语义落到 task_workspaces 主线。
- [ ] 是否存在可证明强于竞品的量化目标，而不是口号。

## 审计输出物要求

每次正式审计至少输出以下内容：

1. 当前总分与各维度分。
2. 证据命令或证据文件。
3. Top 5 风险。
4. 下一阶段提升分值的最小任务集。