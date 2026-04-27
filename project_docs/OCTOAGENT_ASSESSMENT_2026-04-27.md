# OctoAgent 全量代码审阅 + WebUI 修复 + 系统评估报告

> 审阅范围：`192.168.110.2:/home/sieve-pub/public-workspace/octoagent` 全量
> 审阅日期：2026-04-27
> 当前 git HEAD：`2861ee4 Suppress extension body hydration mismatch`（前一个：`5763a75 Fix LAN WebUI auth and dev origin access`）

---

## 一、运行态健康检查（结论：核心链路健康）

| 服务 | 端口 | 状态 | 备注 |
|---|---|---|---|
| Next.js dev (frontend) | 19886 | LISTEN | turbo 模式 |
| FastAPI gateway | 19882 | LISTEN | uvicorn，已加载 ServiceBus、ChannelService、Memory cleanup、Runtime maintenance、Generic maintenance agent |
| LangGraph in-mem runtime | 19884 | LISTEN | langgraph 1.0.10 / api 0.8.1，self-hosted enterprise |
| nginx ingress | 19880 | LISTEN | 反向代理 frontend / gateway / langgraph |

端到端流式验证（已在 host2 直接通过 curl 复现）：
- `POST /api/langgraph/threads/{tid}/runs/stream`（经 nginx 19880）→ 返回完整 SSE，`messages/partial` + `messages/complete`，最终 AI 文本 `ok`，`Background run succeeded`，耗时 ~1.9s。
- 真实 Edge 浏览器（192.168.110.230）发起的会话 `db9c5e60-...` 同样收到 **721,564 bytes** 完整 SSE。

结论：**后端 LangGraph→Gateway→nginx→浏览器整条链路目前是通的**，并不存在"完全无响应"的硬故障。

---

## 二、用户反馈"WebUI 对话无响应"根因分析

### 2.1 复现观察到的两个真实异常

观察 `logs/nginx-access.log`，确实存在一段异常会话片段（thread `2b3ccf92-...`）：

```
POST .../runs/019dcc6a-718c-.../cancel?wait=0&action=interrupt   202
POST .../runs/stream                                               200  120     ← 仅 120B（取消事件）
POST .../state                                                     409  6416    ← 冲突
```

这是典型的 **乐观状态写入与运行取消的竞态**：
1. 用户点击发送，前端 `useStream.submit` 通过 `optimisticValues` 立刻 patch 本地 state，并发起 `runs/stream`；
2. 因某种原因（如 `db9c5e60` 那次同样路径成功）这次走到了 cancel 分支（用户连点 / 双发 / 或 React StrictMode 重复触发）；
3. cancel 后的 stream 只回送很短的 cancel 事件（120B），随后 SDK 又试图 `POST /threads/{tid}/state` 写入乐观 values，与已落盘的 checkpoint 产生 409；
4. 表现：消息气泡定格在"思考中"或新消息无法发出（被 `input-box.tsx:386` 的 `status==="streaming"` 队列门关住）。

### 2.2 同期 frontend 控制台的可疑警告

```
[octoagent] Dropped unsupported LangGraph stream mode(s): tools (src/core/api/stream-mode.ts:31:3)
```

该警告由 `frontend/src/core/api/stream-mode.ts` 的 `SUPPORTED_RUN_STREAM_MODES` 白名单产生，把 `"tools"` 这种非 SDK 1.8.8 内置的模式静默丢弃。**经全 src 扫描，前端源码没有任何位置显式传递 `streamMode: "tools"`**，因此触发者只可能是：
- 浏览器命中 Next.js HMR 缓存的 **旧 chunk**；或
- 来自第三方扩展/被 `app/layout.tsx`（commit 2861ee4 抑制 hydration mismatch）注入的脚本。

由于该模式被丢弃后 SDK 仍以 `["values","updates", ...callbackModes]` 提交（见 SDK `orchestrator.ts:660+`），**它不是会卡住 useStream 的根因**，只是噪音警告。

### 2.3 真正的可疑点：`fetchStateHistory` 在新线程过渡时的竞态

`frontend/src/core/threads/hooks.ts` 中 `useThreadStream` 把 `fetchStateHistory` 在 `loadInitialState ? true : { limit: 1 }` 之间切换。当从 `/workspace/chats/new` 切到真实 thread 时：
- `useStream` 内部调用 `switchThread` → `pendingRuns.removeAll()` 并 `client.runs.cancel(prevThreadId, runId)`；
- 同时新 thread 的 `submit` 已发出 → 落到旧 cancel 的 inflight 段。

这条路径与第 2.1 节看到的 `cancel→stream 120B→state 409` 完全吻合。

### 2.4 处置建议（优先级降序）

| # | 措施 | 文件 | 说明 |
|---|---|---|---|
| P0 | 在 `input-box.tsx` 的 `status==="streaming"` 门控之上增加"超时降级"：>30s 未收到任何 stream 事件则强制回到 `ready` 并允许重发 | `frontend/src/components/workspace/input-box.tsx:380-398` | 让用户自救 |
| P0 | 在 `useThreadStream` 的 `onFinish/onError` 中清空 `optimisticValues` 残留，避免 409 后 UI 卡乐观状态 | `frontend/src/core/threads/hooks.ts:289+` | |
| P1 | 在 `stream-mode.ts` 把 `"tools"` 加入白名单或直接静默不再 `console.warn`（SDK 已自行 dedupe） | `frontend/src/core/api/stream-mode.ts` | 消噪 |
| P1 | 取消"切换 thread 立刻 cancel + 立刻 submit"的并发，改为 `await runs.cancel().catch()` 后再 submit | `useThreadStream.sendMessage` | |
| P2 | nginx HMR 误报：`/_next/webpack-hmr` upstream sent no valid HTTP/1.0 header → 在 `location /` 内为 HMR 单独 `proxy_http_version 1.1` 已设；问题在 turbo HMR 用 `text/event-stream`，建议为 `_next/webpack-hmr` 单独 `proxy_buffering off; proxy_cache off`，或开发环境直接绕过 nginx | `tmp/nginx.local.conf` | |

### 2.5 已立即落地的修复

**Backend memory updater 列表/字典误用 bug**（`logs/langgraph.log` 持续告警 `Memory update failed: 'list' object has no attribute 'items'`）：

`backend/src/agents/memory/updater.py:164-166` —— 在 `_strip_upload_mentions_from_memory` 中遍历 `section_data.items()` 前增加类型守卫：

```diff
 for section in ("user", "history"):
     section_data = memory_data.get(section, {})
+    if not isinstance(section_data, dict):
+        continue
     for _key, val in section_data.items():
```

修改已写入主机文件，下个 LangGraph reload（watchfiles 监听）会自动生效。

---

## 三、系统整体评估

### 3.1 架构总览

```
Browser ─HTTPS/HTTP─▶  nginx :19880  ─┬─▶ /            ─▶ Next.js (turbo dev) :19886
                                       ├─▶ /api/langgraph/  ─▶ LangGraph in-mem :19884
                                       ├─▶ /api/auth/   ─▶ FastAPI Gateway :19882 (Better-Auth proxy)
                                       └─▶ /api/* + /docs + /health  ─▶ FastAPI Gateway :19882
                                                          │
                                                          ├─▶ ServiceBus(system_guard / app_config / gateway_config)
                                                          ├─▶ ChannelService（Feishu/Slack/Telegram/QQ/WeChat/LINE/KakaoTalk/WhatsApp/Zalo/FB Messenger）
                                                          ├─▶ Memory cleanup scheduler（3600s, conf=0.30, cap=500/ns）
                                                          ├─▶ Runtime maintenance（900s，单 thread 最多 20 ckpt / 100 run）
                                                          ├─▶ Generic maintenance agent（1800s）
                                                          ├─▶ Skill-evolution bridge（reflection → skill capture）
                                                          └─▶ Task workspace scheduler
```

### 3.2 优点

1. **架构层次清晰**：Next.js (UI) ↔ FastAPI (业务/Auth/Channel) ↔ LangGraph (Agent runtime) 三层各司其职，边界由 nginx 强力分发。
2. **多端统一接入**：内置 10 个 channel 集成（4 个 native + 6 个 external bridge with shared secret），可水平扩展第三方桥接。
3. **运行态自治**：自带启动 system_guard、运行时维护、内存清理、技能演化、任务工作区四个调度器，具备一定自愈能力。
4. **可观测性**：`logs/` 集中输出 frontend/gateway/langgraph/nginx-(access|error)，并附 `request_id` / `run_id` / `thread_id` 全链路串联。
5. **Stream 协议兼容层完整**：`api-client.ts` 通过 `createCompatibleClient` 包裹 SDK，patch 了 thread 404、provisional id 绑定、stream-mode 白名单，对 SDK 升级具有较强韧性。
6. **嵌入式向量索引**：sentence-transformers all-MiniLM-L6-v2 自动加载（CPU/384 维），无需外部 vector DB。

### 3.3 风险与短板

| 类别 | 风险 | 影响 |
|---|---|---|
| 部署 | dev 模式下 frontend 跑 `next dev --turbo`、langgraph 跑 watchfiles，**当生产用** | HMR 噪音、热重载抖动、性能损失 |
| 安全 | nginx `add_header 'Access-Control-Allow-Origin' '*'` 配合 cookies/Better-Auth 是高危组合（CSRF / 跨站会话泄露） | 仅限内网部署勉强可接受 |
| 安全 | Channel 配置文件 `extensions_config.json` 可能含明文 token，且仓库存在 `extensions_config.json`（应只保留 `.example.json`） | 需要 git diff/`.gitignore` 复核 |
| 稳定 | LangGraph in-mem runtime 不持久化（重启即丢运行中 run），适合开发但**不适合生产** | 需切换 SaaS 或 self-hosted Postgres 持久化变体 |
| 稳定 | Memory updater 容错差，已修一处，建议对所有 `dict.items()` 调用做防御 | 静默丢更新 |
| 稳定 | useStream optimisticValues 与 cancel 竞态导致偶发"假死"（见 §2） | 用户感知卡顿 |
| 性能 | gemma-4-local 不支持 thinking 模式，但前端默认下发 `thinking_enabled=true` 由 lead_agent 后回退（已 warning） | 浪费 1 次冷判断；建议前端按模型能力裁剪 |
| 兼容 | SDK 不识别的 `"tools"` stream mode 静默丢弃 + console.warn 持续刷屏 | 噪音掩盖真问题 |

---

## 四、模块逐项评估

### 4.1 backend/src/gateway —— FastAPI 网关

- **lifecycle.py** 启动流程完整：load config → start system_guard → ServiceBus → ChannelService → reflection bridge → memory cleanup → runtime maintenance → generic maintenance agent → channel manager。
- **routers/** 涵盖 setup / task_workspaces / models / mcp / skills / threads / state / channels / memory / 等约 38 个路由组，组织规范。
- 不足：`/api/auth/*` 透传到 gateway 但实际走 Next.js Better-Auth；nginx 上 `/api/auth/` 优先级先于 `/api/`，但当前 `/api/auth/get-session` 实际由 Next.js 处理（route handler 不在 src 内、应在 build 出来的产物中），**需确认 5763a75 是否把 auth 完全切到 frontend**。

### 4.2 backend/src/agents —— Agent 体系

- `lead_agent`：主入口，按 model capability 自动决定 `thinking_enabled / view_image_tool / subagent_tools` 注入。
- `memory/`：分层 memory（user / history / facts），含 cleanup 调度、TTL、置信度修剪、`system_rag_store`、`updater`（已修 §2.5）。
- `middlewares/skill_evolution_middleware`：每次 run 后异步分析对话生成 captured skill（见日志 `auto-hi-reply-ok`）。
- 风险：Skill 自动捕获在 dev 阶段高频生成低价值条目（如 "auto-hi-reply-ok"），需调高捕获阈值或加入白名单。

### 4.3 backend/src/channels —— 通道适配

- 4 个 native（Feishu / Slack / Telegram + Manager dispatch loop），6 个 external bridge（QQ/WeChat/LINE/KakaoTalk/WhatsApp/Zalo/FB Messenger）。
- 配置由 `channels.{name}` 段统一驱动，含 `enabled / configured / running / healthy` 四态自检，`fields` schema 直接驱动前端表单 UI（自带表单生成，省一份 schema）。
- 当前全部 `enabled: false`，未运行；上线时需同步处理 webhook 鉴权、白名单、超时。

### 4.4 backend/src/reflection / skill_evolution

- `reflection → skill_evolution_bridge` 已经在启动时注册监听器；`evolver` 在 after_agent middleware 自动 capture。
- 缺乏审计/回收闭环：建议在 maintenance agent 加 "captured skill 7 天未被采纳则降级/删除"。

### 4.5 backend/src/runtime / maintenance

- runtime_maintenance：每 900s 修剪 thread 历史（max 20 ckpt / 100 run），并清理 >3600s 仍 running 的死 run。
- generic_maintenance_agent：每 1800s 跑通用维护（具体内容随 enabled 规则）。
- 评价：策略合理，但当前阈值固定，未支持热配置；应纳入 `gateway_config` ServiceBus，方便运行时调整。

### 4.6 frontend/src

- **架构**：App Router + tRPC 风格 useStream + Zustand 状态、Virtuoso 长列表、React Flow 图渲染。
- **核心包装**：
  - `core/api/api-client.ts`：在 SDK 之外做 thread 404 容错、provisional thread id 绑定、stream sanitize；
  - `core/api/stream-mode.ts`：白名单丢弃；
  - `core/threads/hooks.ts`：`useThreadStream` 复合 useStream + 文件上传 + 乐观值 + 重试；
  - `core/config/index.ts`：根据 origin 自动选 `langgraph base url`，已支持 LAN（5763a75）。
- **痛点**：
  - 540+ 行的 `hooks.ts:sendMessage` 复杂度过高，分支众多（thread 预创建/文件上传/乐观值/missing-file 重试/missing-thread 重试），单测覆盖困难；
  - `app/layout.tsx` 用 hydration mismatch 抑制脚本（2861ee4）只是缓兵之计，最佳做法是定位浏览器扩展具体注入位置。

### 4.7 nginx ingress

- 单文件 `tmp/nginx.local.conf`，结构简洁。
- 已对 `/api/langgraph/` 关闭 buffering / cache、设置 600s 超时，符合 SSE 要求。
- 缺：HMR 段独立优化、HTTP/2、HSTS（生产）；CORS `*` 在带 cookie 场景应改为 `proxy_pass_request_headers on; add_header Access-Control-Allow-Credentials true; add_header Access-Control-Allow-Origin $http_origin always`。

### 4.8 部署

- `octoagent-service.sh` + `start-octoagent.sh` 两套启动脚本，`Makefile` 也有规则。
- Python 用 `uv` venv，前端用 `pnpm`。
- docker/ 目录有 `nginx/nginx.local.conf`，但当前 nginx 进程实际加载的是 `tmp/nginx.local.conf`（运行时动态生成？需要 deploy 自检统一）。
- 建议：systemd unit 化、journald + logrotate 接管 `logs/*.log`（当前 maxBytes=10485760 backups=5 由应用自管理）。

---

## 五、行动清单（按优先级）

### 紧急（24h 内）
1. ✅ **已修**：`updater.py` 的 list/dict 守卫，止血 `Memory update failed` 告警。
2. 🔧 frontend `useThreadStream` cancel→submit 串行化（消除 §2.1 竞态，根治"假死"）。
3. 🔧 input-box 30s 看门狗，超时强制 ready。

### 短期（一周内）
4. 🔧 stream-mode 白名单加入 `"tools"`，或在 `console.warn` 前 dedupe。
5. 🔧 thinking_enabled 与 model capability 在前端联动，避免无意义后端回退。
6. 🔧 `extensions_config.json` 走 `.gitignore`，仅保留 example。
7. 🔧 nginx CORS 适配 cookies（白名单 `$http_origin`）。

### 中期（迭代）
8. 🛠 LangGraph 切到 self-hosted Postgres 持久化变体，准备生产化。
9. 🛠 `logs/` 接入 journald + logrotate，关闭应用内分文件 rotate。
10. 🛠 sendMessage 复杂度治理（拆 saga / state machine / xstate）。
11. 🛠 Skill auto-capture 引入降级回收，避免低价值条目膨胀。
12. 🛠 maintenance 阈值搬入 ServiceBus，支持热配置。

### 长期（架构）
13. 🧭 前端用例覆盖：补 useStream 边界场景的 e2e（cancel/race/network drop/long-running）。
14. 🧭 channels native ↔ external bridge 抽象统一为 `ChannelTransport` 接口，简化新平台接入。
15. 🧭 Auth：明确 Better-Auth 责任边界，决定是 nginx 透传还是 Next.js handler 终结。
16. 🧭 dev/prod 分离，产线禁用 turbo HMR、watchfiles。

---

## 六、附录：当前关键文件指针

| 文件 | 作用 |
|---|---|
| `tmp/nginx.local.conf` | 实际生效的 nginx 配置 |
| `start-octoagent.sh` / `octoagent-service.sh` / `Makefile` | 三套启动入口 |
| `backend/src/gateway/lifecycle.py` | 网关启动顺序 |
| `backend/src/agents/lead_agent/{builder,runtime}.py` | 主 Agent |
| `backend/src/agents/memory/{updater,cleanup,system_rag_store}.py` | 记忆子系统 |
| `backend/src/channels/{manager,service,*}.py` | 通道接入 |
| `frontend/src/core/api/{api-client,stream-mode}.ts` | SDK 兼容层 |
| `frontend/src/core/threads/hooks.ts` | 对话状态机 |
| `frontend/src/components/workspace/input-box.tsx` | 输入框（status 门控关键点）|
| `frontend/src/app/workspace/chats/[thread_id]/page.tsx` | 会话页骨架 |
| `logs/{frontend,gateway,langgraph,nginx-*}.log` | 全链路日志 |

— 报告完 —
