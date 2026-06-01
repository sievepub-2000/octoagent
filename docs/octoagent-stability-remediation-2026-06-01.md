# OctoAgent 稳定性整改 - 2026-06-01

承接 `docs/octoagent-system-assessment-2026-06-01.md` 的系统评估，本轮针对评估中确认的高影响问题做了**安全、可回滚、已验证**的整改，并明确列出需要计划窗口才能执行的高风险架构项。

## 环境快照（整改前）

- 主机：2号机 `192.168.110.2`，分支 `main`（与 `origin/main` 已同步，无未推送提交）。
- 服务：llama-server `:8000`、gateway `uvicorn :19802`、`langgraph_cli dev :19804`、frontend `next :19806` 均健康。
- LangGraph 运行模式：`langgraph_runtime_inmem`（in-memory，非持久化）。
- 本地模型：`qwen3.6-35b-a3b-q8-mm-prod`（Qwen3.6-35B-A3B Q8 多模态，llama.cpp `:8000`）。

## 已修复并验证（本轮落地）

### 1. 本地模型超时级联（P0-2 / P0-3 / P1-3 根因）

- **现象**：本地模型小请求 0.75s 正常，但长 agent 生成在 `request_timeout: 120` 下超时；超时不会终止 run，导致 run 挂起约 600s 后被 `OrphanRunSweeper` 强杀；同时触发向不稳定免费在线模型回退，`/runs/stream` SSE 被上游提前关闭。
- **修复**：`runtime/config/config.yaml` 中本地模型卡 `request_timeout` 120 → **300**。本地模型无按 token 计费，提高超时上限消除超时→回退→孤儿→断流的级联。
- **范围**：仅本地模型卡，在线模型超时维持 90–120 不变。

### 2. DuckDB 单写锁导致记忆写入丢失（P1-1）

- **现象**：1.8GB 的 `octoagent_rag.duckdb` 同时被 gateway 与 LangGraph 进程以读写方式打开，`SimpleMemBridge store.add` 报 `IO Error: Could not set lock ... Conflicting lock is held`，记忆静默丢失。
- **修复**：`backend/src/storage/rag/unified_store.py` 的 `UnifiedRAGStore._connect()` 增加针对锁冲突的**指数退避重试**（6 次，0.25s→2s 封顶），仅对包含 `lock`/`conflicting` 的异常重试，其余异常照常抛出。短暂争用期内重试取代静默丢弃。
- **校验**：`ast.parse` + `py_compile` 通过。

## 需计划窗口执行的高风险项（本轮未自动执行，附理由与建议）

### A. LangGraph 持久化（P0-1）

- `langgraph dev` 按设计使用 in-memory store，重启即丢失 checkpoint；PostgreSQL(:5432)/Redis(:6379) 在线但空闲。
- 真正修复需以 PostgresSaver/SqliteSaver 运行图（`langgraph up` 需 Docker + 许可证，或自定义 ASGI 承载），属于对在线多用户系统的重大迁移。
- **建议**：在计划维护窗口内，以 `backend/src/runtime/config/checkpointer_config.py`（已支持 `memory|sqlite|postgres`）预置 Postgres 连接，灰度切换并验证回滚。

### B. HITL 危险工具确认体验（P1-2）

- 经核查：只读 git（`git_status`/`git_log`/`git_diff`）在 `backend/src/tools/catalog.py` 为 `directory` 范围，运行期门控 `dangerous_tool_confirmation_middleware._requires_confirmation` 仅对 `permission_scope == "system"` 触发，**当前代码下只读 git 不会被判为危险**，无需改动分级。
- 「同一轮重复弹出确认」的去重涉及 resume 流程，线上改动回归风险较高，列为后续在测试环境验证后再合入项。

### C. DuckDB 单写架构

- 重试可缓解瞬时争用，根治需将写入收敛到单一进程（如全部经 gateway 写入，LangGraph 侧只读 `read_only=True`）。属架构改动，建议单独排期。

## 重启与验证

- 整改前队列空闲（`n_pending=0, n_running=0`），经 `scripts/stop-services.sh` + `scripts/start-daemon.sh` 受控重启以加载新配置与代码。
- 验证项：gateway `/health`、langgraph `/ok`、frontend、WebUI 入口均返回正常；日志不再出现新的本地模型超时与 DuckDB 锁冲突。

## 更正与第二阶段落地（2026-06-01 续作）

> 重要更正：上文 A 项（P0-1）关于「LangGraph 重启即丢失 checkpoint」的前提**有误**。复核实时 PostgreSQL 后确认：自定义 Postgres checkpointer 经 `backend/langgraph.json` 的 `checkpointer` 钩子 + `runtime/config/config.yaml` 的 `checkpointer.type: postgres` **早已生效**，对话状态持久化在 PG 中（实测 `checkpoints` 30,860 行、`checkpoint_writes` 44,901 行、`checkpoint_blobs` 16,792 行）。日志中的 `langgraph_runtime_inmem` 仅指**瞬时 run 调度队列**（在途任务排程，可安全丢失），并非会话状态。

### A'. P0-1 真正缺口：缺失 `acopy_thread`（已修复并实测）

- **真实问题**：自定义 checkpointer 缺少 `acopy_thread`，导致 `POST /threads/<id>/copy` 走 langgraph_api 的通用回退路径（逐条 `aput`/`aput_writes` 重插），复制大会话很慢；启动日志反复打印 `Custom checkpointer missing acopy_thread: using generic fallback (functional but slower)`。
- **修复**：在 `backend/src/agents/checkpointer/async_provider.py` 的 `OctoAgentAsyncPostgresSaverMixin` 上实现 `acopy_thread`，用三条 `INSERT ... SELECT ... ON CONFLICT DO NOTHING` 在库内整体复制 `checkpoint_blobs`/`checkpoints`/`checkpoint_writes`，幂等、对空目标安全。
- **实测**：对实时 PG 选取最大会话（2,713 checkpoints）复制到临时 thread，校验 `checkpoints=2713 / writes=3768 / blobs=1409` 完全匹配后清理临时 thread；adapter 的 `_is_overridden` 检测为 True。
- **重启验证**：`sudo systemctl restart octoagent-local.service` 后，langgraph 日志**不再出现** `missing acopy_thread` 警告；端口 8000/19800/19802/19804/19806 全部 OPEN，WebUI 307→200、标题 `OctoAgent`。

### B'. HITL 危险工具确认去重（P1-2，已修复并测试）

- **保留结论**：只读 git 仍为 `directory` 范围，不会被判危险，无需改分级。
- **新增修复**：危险工具待确认（`dangerous_tool_pending`）置位时，工具节点每次重入都会重复发出**同一 signature** 的确认提示。新增 `_confirmation_already_visible(messages, signature)`，仅当用户当前可见的最近一条机器人输出正是该 signature 的确认提示、且其后无新的人类消息时，**静默 `goto=END` 不再重复发消息**；否则照常发出（fail-open）。
- **安全性**：去重按 signature 精确匹配、按线程内消息序列判断、失败即放行——绝不会跨线程或对不同工具误抑制安全确认。
- **测试**：新增 2 条回归测试（重复抑制 + 人类回复后仍照常发出）；`tests/agents/test_dangerous_tool_confirmation_middleware.py` 8 passed，`tests/agents` 全量 **170 passed**，零回归。

### C'. DuckDB 单写收敛设计（计划项，已给出方案）

- **现状**：退避重试已缓解瞬时锁争用（P1-1 已落地），但 gateway 与 LangGraph 两进程仍同时以 RW 打开 `octoagent_rag.duckdb`，根因未除。
- **目标架构**：写入收敛到单一属主进程（gateway），LangGraph 侧改为只读连接。
  1. gateway 持有唯一 RW 连接，暴露内部写入接口（`store.add/update/delete`）。
  2. LangGraph worker 内 `UnifiedRAGStore` 以 `read_only=True` 打开，所有写请求经 gateway 内部 API/IPC 转发。
  3. 读路径维持各自只读连接（DuckDB 允许多读）。
  4. 迁移期：保留 `_connect()` 退避重试作为兜底；切换后逐步移除写侧并发。
- **风险**：涉及跨进程写入通道，需在测试环境验证一致性与吞吐后再切，单独排期。

## 下一步计划（按优先级）

1. **DuckDB 单写收敛（C' 实施）**：测试环境实现 gateway 唯一写属主 + LangGraph 只读，压测一致性/吞吐，灰度上线，再移除退避重试兜底。
2. **acopy_thread 端到端回归**：在测试环境对 `POST /threads/<id>/copy` 做真实 API 级验证（含大会话计时对比），纳入自动化测试。
3. **HITL 同轮并行去重**：当前去重覆盖「跨轮重入重复」；若出现单个 LLM 轮内并行多危险工具调用的重复，再评估实例级（按线程标识）守卫，仍坚持 fail-open。
4. **持久化健康巡检**：将 PG checkpoint 行数与增长纳入 `/health` 或定时巡检，避免误判 in-memory。
5. **超时级联回归监测**：观察本地模型 `request_timeout: 300` 下是否仍有孤儿 run / SSE 断流，必要时按模型分档调参。

## 第二轮整改与下一步计划落地（2026-06-01 续）

承接本文上半部分列出的「需计划窗口执行的高风险项」，本轮在**不做线上不可逆架构变更**的前提下，落地了 5 项前瞻计划中的安全部分，并对其余高风险部分给出明确排期边界。全部改动均通过 `py_compile`、单元测试与线上实测验证。

### #6 DuckDB 写入安全（item C 的安全步，非全量 IPC 收敛）

- **背景**：上一轮只对 `UnifiedRAGStore._connect()` 加了锁冲突退避重试，但实际静默丢数据的写路径是 `SystemRAGStore._connect()`（`SimpleMemBridge store.add` → 系统记忆写入），它指向同一个 `octoagent_rag.duckdb`（`self._db_path = self._rag.db_path`）却是**裸 `duckdb.connect`、无重试**。
- **修复**：在 `unified_store.py` 抽出模块级 `connect_duckdb_with_retry(db_path, *, read_only=False, attempts=6, base_delay=0.25, max_delay=2.0)`，`UnifiedRAGStore._connect` 与 `SystemRAGStore._connect` 统一委托到它。两进程瞬时争用期内重试取代静默丢弃。
- **未做（按风险排期）**：将所有写入收敛到单一进程、LangGraph 侧 `read_only=True` 的全量单写 IPC 架构改造，属对在线多用户系统的重大变更，仍列为独立计划窗口项。

### #4 持久化健康巡检

- gateway `/health` 新增 `persistence` 字段，并提供独立 `/health/persistence`。探针带 30s 缓存、2s 连接超时、`asyncio.to_thread` 不阻塞事件循环、任何异常都不抛出（健康检查永不因探测失败而 500）。DSN 来自 `get_app_config().checkpointer.connection_string`（仅 `type==postgres` 时探测）。
- **线上实测**：`{"backend":"postgres","ok":true,"checkpoints":31043,"threads":78}`。

### #3 HITL 同轮并行去重

- 在 `dangerous_tool_confirmation_middleware` 增加实例级 `_claim_emission(messages)` 守卫：同一节点并行 fan-out 的多个危险工具调用共享同一个内存 `messages` 列表对象，仅首个 claim 者弹确认，其余在 3s 窗口内按列表 `id()` 命中后静默 `goto=END`。
- **安全性**：两个**存活**对象的 `id()` 不可能相同，故并发处理不同 `messages` 列表不会误判；极端的 id 复用（仅在前一列表被回收后才可能）最坏只是抑制一次弹窗并停在本轮（用户重发即恢复），**绝不会让未授权工具执行**（fail-safe 偏向不执行）；任何簿记异常 fail-open。
- 新增 2 条回归测试，`tests/agents` 共 **172 passed**。

### #2 acopy_thread API 级端到端回归

- 直接对 langgraph dev 原生 `POST /threads/<id>/copy` 实测：复制一个 2713 checkpoint 的会话，结果 **checkpoints 2713 + blobs 1409 + writes 3768，与源 1:1**，耗时 **0.59s**；随后 `DELETE /threads/<id>` 返回 204，复制线程残留清零。证实上一轮新增的 Postgres `acopy_thread` 快路径在真实 API 调用下生效。

### #5 超时级联监测

- 重启后扫描 `logs/langgraph.log` / `logs/gateway.log`：**0 孤儿取消、0 超时、0 SSE 断流**；启动巡检 `runs_cancelled: 0`、`journal_stale: 0`。证实 `request_timeout: 300` 已消除「超时→回退→孤儿→断流」级联，属观测项、无需额外代码改动。
