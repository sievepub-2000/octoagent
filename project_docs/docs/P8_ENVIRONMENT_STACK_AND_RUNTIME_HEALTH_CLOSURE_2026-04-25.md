# P8 环境栈拉齐与运行时健康治理收口报告

> 日期：2026-04-25  
> 唯一项目目录：`/home/sieve-pub/public-workspace/octoagent`  
> 当前分支：`main`

## 结论

P8 当前交付重点是把 LangGraph 运行环境、项目依赖声明、运行时维护器、doctor/API contract smoke 和 WebUI 健康治理面拉到同一条版本与能力基线上。后端、前端、doctor、soak 和生产构建均已通过，当前系统可以继续以 `main` 作为唯一开发主线推进。

这次收口把 P7 已完成的长期任务能力进一步产品化：不再只停留在 API 与脚本层，而是补上 Runtime Health 设置页、维护器状态/手动运行入口、运行时告警阈值、LangGraph remote capability 探测，以及环境栈声明对齐。

## 环境栈拉齐

当前 `backend/.venv` 已与项目声明对齐到以下关键版本：

- `langgraph-api==0.8.1`
- `langgraph-runtime-inmem==0.28.0`
- `opentelemetry-api==1.41.1`
- `opentelemetry-sdk==1.41.1`
- `opentelemetry-exporter-otlp-proto-http==1.41.1`
- `opentelemetry-exporter-otlp-proto-grpc==1.41.1`
- `opentelemetry-proto==1.41.1`
- `opentelemetry-semantic-conventions==0.62b1`
- `protobuf==6.33.6`
- `pydantic==2.13.3`
- `pydantic-core==2.46.3`

`pip check` 已确认没有 broken requirements。`backend/pyproject.toml` 已将 `langgraph-api`、`langgraph-runtime-inmem` 和 `pydantic` 的下限提升到当前兼容面；`backend/requirements.txt` 已同步 pin 到当前虚拟环境版本。

说明：`uv lock --upgrade-package langgraph-api` 在本机 resolver 阶段长时间无结果，已中止。当前以 `pyproject.toml`、`requirements.txt` 和实际 `.venv` 三者一致作为本次环境栈收口结果；后续若要重新生成 `uv.lock`，建议单独开一个依赖锁刷新任务，并给 resolver 设置明确超时与缓存策略。

## 本次实现内容

### 运行时维护闭环

- 新增 `RuntimeMaintenanceScheduler`，在 gateway lifespan 内启动和停止。
- 定时维护 QueryEngine 会话缓存、摘要和 stale session。
- 定时 prune OctoAgent-side LangGraph workflow contract ledger，避免 checkpoint/run 无限增长。
- 新增维护状态与手动维护 API：
  - `GET /api/runtime/maintenance/status`
  - `POST /api/runtime/maintenance/run`

### Runtime Health 治理面

- WebUI settings 新增 Runtime Health 页面。
- 页面展示运行时快照、worker isolation、LangGraph contract、maintenance 状态和 alerts。
- 支持 operator 从 WebUI 手动触发维护，调整单线程 checkpoint/run 保留阈值。

### LangGraph contract 与 remote 能力

- `/api/runtime/langgraph-contract` 增加 remote capabilities 探测。
- 已探测到当前 SDK 支持 `threads.copy`、`threads.delete`、`threads.prune`、`threads.get_state`、`threads.get_history`，以及 runs 的 `cancel/delete/list` 能力。
- prune/copy/delete 远端调用已增加 UUID 保护，避免本地模拟线程 ID 误打到 LangGraph remote API。

### Doctor 与告警

- runtime long-running health snapshot 增加 alerts。
- doctor 扩展检查 runtime maintenance API、LangGraph remote capabilities、内存、磁盘、checkpoint、队列深度、event-loop latency。
- 维护器异常会写入 warning 日志，避免长期运行失败被静默吞掉。

## 验证记录

已完成验证：

- `backend/.venv/bin/python -m pip check`：通过。
- `cd backend && .venv/bin/python -m compileall -q src scripts`：通过。
- `cd backend && .venv/bin/python -m ruff check src scripts`：通过。
- `cd frontend && pnpm lint`：通过。
- `cd frontend && pnpm typecheck`：通过。
- `cd frontend && pnpm build`：通过。
- `backend/scripts/run_system_doctor.py --skip-git`：通过，15 项 API/doctor smoke 全部 OK。
- `backend/scripts/run_long_running_soak.py --iterations 40 --json`：通过，checkpoint 从 40 prune 到 5，队列和 active worker 回到 0。
- `backend/scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --mock`：通过，聊天、续接、settings、bootstrap、task workspace smoke 全部 OK。
- 重启开发栈后实际运行态 `GET /api/runtime/maintenance/status` 返回 `running=true`，维护器已随 gateway lifespan 启动。

## 当前项目整体评估

OctoAgent 当前已经从“多模块可运行”进入“运行时治理可审计”的阶段。主链路已明确为 Next.js WebUI、FastAPI gateway、LangGraph runtime、task workspace lifecycle 和 capability/operator policy。P6/P7/P8 连续收口后，项目的主要改进是：

- workflow lifecycle 不再散落在多个默认入口，运行时真相更集中。
- capability binding 已具备 operator policy、审计和 WebUI 治理基础。
- 长期任务的上下文、checkpoint、worker queue 和 event-loop latency 已进入 doctor/soak 验证闭环。
- 环境栈已从旧 `langgraph-api 0.7.x` 拉齐到 `0.8.1`，并解决 OTel/protobuf/pydantic 依赖链冲突。

当前仍然需要谨慎看待的点：

- LangGraph remote capability 已可探测并可被调用，但真实多小时 workflow 的 remote checkpoint prune/copy/delete 还需要在线路真实任务下继续压测。
- `uv.lock` 尚未重新生成，后续需要专门处理 resolver hang，避免依赖声明与 lock 文件长期不一致。
- workflow module 与 LangGraph 的 pause/resume/cancel/replay/terminate 还需要补齐端到端 contract smoke。
- Context recovery 已具备维护基线，但摘要质量、跨进程恢复、空状态类型化和 UI 解释仍可继续加强。
- distributed execution、multi-tenant、monitoring、reflection、self-evolution 仍属于 API/最小治理面阶段，尚未达到完整产品模块成熟度。

## 下一步计划

1. 单独完成 `uv.lock` 刷新，明确 dependency lock 生成流程和超时策略。
2. 将 workflow module 与 LangGraph remote thread/run/checkpoint 做端到端契约测试，覆盖 pause、resume、cancel、replay、terminate。
3. 增加真实多小时 soak test，记录内存、磁盘、进程数、event-loop latency、worker queue、checkpoint 数量是否回到稳定区间。
4. 将 Runtime Health alerts 接入 operator notification 或 dashboard badge。
5. 继续完善对话缓存回收：摘要质量评估、stale-thread 自动恢复、跨进程上下文接续、长会话压缩回放。
6. 推进 capability operator policy 的导入导出 UI、签名审计历史、release precheck。
7. 将 distributed execution 与 multi-tenant 从 API-first 推进到可操作的治理面和 smoke 验证面。
