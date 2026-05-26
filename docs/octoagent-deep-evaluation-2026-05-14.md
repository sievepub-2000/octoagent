# OctoAgent — 深度评估与下一步建议（2026-05-14）

> 评估对象：私有部署的 octoagent 项目（运行在 `192.168.110.2`，systemd unit `octoagent-local.service`）。
> 评估视角：架构 / 执行链路 / 失败模式 / 验证盲区 / 改进优先级。
> 评估方法：贴近代码 + 现场调用 + 日志 + 配置。

## 1. 当前架构快照

```
┌──────────┐    ┌─────────────────┐    ┌────────────────┐
│  Next.js │ →  │ nginx 反向代理  │ →  │ LangGraph 19884│
│   19886  │    │      19880      │    │ Gateway   19882│
└──────────┘    └─────────────────┘    └────────────────┘
                                              ↓
                                      OpenRouter / 备援模型链
                                  (FallbackChatModel + bootstrap)
```

- 前端：Next.js 16.2.3（生产模式 `next start`），Turbopack 构建。React + react-query + `@langchain/langgraph-sdk/react` `useStream`。
- LangGraph 服务：`langgraph dev --allow-blocking`，主 graph `lead_agent`。
- 网关 API：FastAPI，~49 个 router，承载文件上传、运行时快照、RAG 配置、可观测性等。
- 模型策略：`nemotron-3-super-free`（OpenRouter）→ `gpt-oss-120b-free` → `qwen3-next-free` → `__embedded_bootstrap__` 兜底。
- RAG/嵌入：BGE-small-zh-v1.5（嵌入）+ BGE-reranker-base（重排）；HF 镜像 `hf-mirror.com`；`HF_HUB_OFFLINE=1` 全局。
- 持久化：LangGraph checkpointer（默认 SQLite），LanceDB / SQLite 用于 RAG。
- 守护脚本：`scripts/start-daemon.sh` 控制端口、构建 hash、停启顺序。

## 2. 本轮（Sprint 4 + UX 整改）已完成项

| 类型 | 描述 | 文件 |
|---|---|---|
| RAG | BGE 嵌入 + reranker 接入，rerank 在 `_hybrid_vector_table` 内置 | `backend/src/models/embedding_service.py`、`reranker_service.py`、`backend/src/rag/facade.py` |
| RAG 配置 | Gateway `GET/PUT/download` API + 设置页 | `backend/src/gateway/routers/rag_config.py`、`frontend/src/core/rag-config.ts`、`frontend/src/components/workspace/settings/rag-settings-page.tsx` |
| 目标契约 | LLM-based GoalContract 抽取（heuristic + JSON prompt 双轨） | `backend/src/agents/middlewares/goal_contract_middleware.py` |
| UX：字体 | 用户气泡补 `text-sm`，与 AI 气泡一致 | `frontend/src/components/workspace/messages/message-list-item.tsx` |
| UX：事件栏 | 新增 `system-events` store（基于 `useSyncExternalStore`） + 右侧抽屉 `SystemEventsButton` | `frontend/src/core/system-events/store.ts`、`frontend/src/components/workspace/system-events/system-events-button.tsx` |
| UX：toast 重定向 | 5 处 `toast.info/warning` 改写为事件栏 push；致命 `toast.error` 保留 | `frontend/src/core/threads/hooks.ts`、`frontend/src/app/workspace/chats/[thread_id]/page.tsx` |
| UX：watchdog 延时 | 长任务噪声阈值 30s → 90s | `frontend/src/core/threads/hooks.ts` |

## 3. 现存问题与风险

按影响力排序。

### A. 模型/运行时层

1. **`finish_reason: "stopstop"` 与 `model_name` 重复**
   - 现象：`messages/partial` 流事件里 `finish_reason` 拼接成 "stopstop"、`model_name` 被串接两份。
   - 定位：`backend/src/models/factory.py` 中 `FallbackChatModel` 的 partial-merging 逻辑（每个 partial 都把 metadata 重新拼接，而不是替换）。
   - 影响：UI 流尚能识别终止，但任何依赖 `finish_reason` 做下游分流的逻辑都会失真；可能影响未来的可观测性/A-B 实验。
   - 建议：partial 合并使用 last-wins 策略，最终 `final` 事件再覆盖；写一个最小回归测试。

2. **`Ignoring unknown node tools in pending sends` 警告反复出现**
   - 来源：LangGraph 版本和当前 graph 定义的工具/节点命名不一致；多出现在恢复 / 上下文压缩接续路径。
   - 建议：升级 / 锁版 `langgraph` 与 `langgraph-cli`，并把当前 `prebuilt graphs` 内的 `tools` 节点显式注册到 `nodes`；写 `tests/test_graph_definition.py` 校验。

3. **`HF_HUB_OFFLINE=1` 全局强制**
   - 在 `scripts/start-daemon.sh` 中被无条件设置。模型一旦未完整缓存（如换 reranker），会直接报错且不易诊断。
   - 建议：把它改成"启动时检测 + 必要时一次性允许联网"的双态开关；在系统事件栏发出"模型缓存缺失"的告警。

### B. UX / 前端层

1. **WatchDog 心跳轮询继续 30s 一次**
   - 已把首次提示从 30s → 90s，但 `monitorIntervalRef` 仍 30s 持续 fetch；多任务时仍可能轻微抢占主线程。建议改为 60s 或后端推一个 `keep-alive` SSE 事件。

2. **`useStream` 的 toast 入口仍有少量散落**
   - 主链路已收口到 `system-events` store，但 `src/core/uploads/`、`src/core/notification/` 等模块仍直接调用 sonner。建议下一轮统一封装一个 `notifyEvent({level, message, fatal?:bool})`，由它决定走 toast 还是事件栏。

3. **错误边界（fallback-only 视图）尚未落地**
   - 当前如果整个 UI 因运行时报错崩溃，用户只能看到空白。建议在 `src/app/workspace/layout.tsx` 外层包 `ErrorBoundary`，渲染"错误信息 + 系统事件栏"的极简视图。

4. **Studio Runtime Panel 信息密度过大**
   - `execution-log-panel.tsx` 一屏挤 4 列卡片 + 3 个 Card + 时间轴 + 运行日志。建议拆 tabs（Overview / Workflow / Channels / Logs），并把"系统事件"显式作为一个 tab。

### C. 后端组织

1. **Gateway routers 数量（≈49）已超过单一 `gateway/main.py` 的合理上限**
   - 建议按 domain 分包：`runtime/`、`rag/`、`auth/`、`observability/`、`config/`。配合 `APIRouter(prefix=...)` 自动注册。

2. **`generic_agent` 与 `studio_runtime` 双轨**
   - 两套 agent 编排逻辑并行（lead_agent in studio_runtime + generic_agent 系列），存在概念重叠。建议下一轮做一次 API surface 对齐：要么合并，要么明确"实验性 vs 生产"标签。

3. **测试覆盖偏向单元 + smoke**
   - 端到端"用户→stream→checkpoint→恢复"链路缺少回放测试。建议引入 `tests/e2e/test_chat_round.py`，固定 mock provider，用 `pytest-asyncio` 驱动 SDK 客户端跑完整链。

### D. 观察 / 运维

1. **日志分散**：`logs/{langgraph,gateway,nginx,frontend,nginx-access,nginx-error}.log` 各自切割策略不同。
   - 建议统一加入 `logrotate` 配置（gw/lg 每日 + 保留 7 份），并在系统事件栏暴露"近 5 分钟错误数"指标。

2. **没有 Prometheus 或 OpenTelemetry hook**
   - 当前可观测性靠 ad-hoc curl + tail。`langgraph` 已经原生支持 OTel，建议接入并把指标转发到本地 Grafana。

## 4. 推荐的 Sprint 5 计划

| 优先级 | 主题 | 验收信号 |
|---|---|---|
| P0 | 修 `FallbackChatModel` partial-merging（finish_reason / model_name） | 单元测试 + 回归脚本 `tests/test_fallback_partials.py` 通过 |
| P0 | `notifyEvent` 统一封装，剩余 toast 全部走事件栏（除 fatal） | 全仓 `grep -r "toast\."` 仅剩 `toast.error` |
| P1 | ErrorBoundary + 极简错误视图 | 人为抛错时 UI 不白屏 |
| P1 | Gateway router 域拆包 + 自动注册 | `gateway/main.py` ≤ 80 行 |
| P1 | LangGraph "Ignoring unknown node tools" 警告清零 | journal 中 30 分钟内 0 命中 |
| P2 | OpenTelemetry + Grafana 本地仪表盘 | 能看到 token/sec、reranker 命中率、checkpoint 写入耗时 |
| P2 | E2E 回放测试（mock provider） | CI 一次跑通完整 chat round |
| P3 | `HF_HUB_OFFLINE` 双态开关 + 系统事件告警 | 切换 reranker 模型时不再触发服务启动失败 |

## 5. 风险登记

- **HF 缓存隐性依赖**：当前依赖 `~/.cache/huggingface/hub/` 已有 6.9GB。若主机重装或换盘，需文档化"首次预热"流程。
- **systemd 重启 = `next build`**：源码 hash 变就触发完整生产构建（~30s+）。频繁热修复时考虑加一个 dev 模式开关。
- **OpenRouter 免费层限频**：当前所有备援都指向 `:free` 后缀模型，并发上限较低；生产环境务必加 paid fallback。
- **聊天会话 zombie 端口**：端口 `19884` 已多次发生 langgraph_cli 残留。建议在 `start-daemon.sh` 启动前用 `fuser -k -KILL 19880-19886/tcp` 显式清理。

## 6. 立即可做的小动作（≤1 天）

1. `backend/src/models/factory.py`：把 partial 合并改为 last-wins，加 2 个测试。
2. `src/core/uploads/hooks.ts`：把 `toast.error` 之外的提示改成 `pushSystemEvent`。
3. `frontend/src/app/workspace/layout.tsx`：包一层 `ErrorBoundary`。
4. `scripts/start-daemon.sh`：启动前 `fuser -k -KILL 19880-19886/tcp || true`。
5. 把这份评估文件加进 repo `docs/`，并在 README 顶部加 "Roadmap" 锚。

---

文档生成时间：2026-05-14。下一次评估建议在 Sprint 5 结束后。
