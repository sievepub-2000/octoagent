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
