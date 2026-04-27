# P9 依赖锁、运行时契约与治理面收口报告

> 日期：2026-04-26  
> 唯一项目目录：`/home/sieve-pub/public-workspace/octoagent`  
> 当前分支：`main`

## 结论

P9 已把 P8 后续计划推进为可重复验证的工程闭环：`uv.lock` 已刷新，workflow module 与 LangGraph remote thread/run/checkpoint 契约已有 smoke，长期 soak 脚本支持按真实 duration 采样，Runtime Health alerts 已进入顶部状态栏和浏览器通知，QueryEngine 增加摘要质量评估、stale session 恢复和 replay context，capability operator policy 增加 release precheck，distributed execution 与 multi-tenant 从 API-first 推进到 WebUI 可操作治理面。

## 本次完成内容

- `backend/uv.lock` 已通过有界 resolver 刷新：`timeout 600s uv lock --upgrade-package langgraph-api --upgrade-package langgraph-runtime-inmem`。
- release precheck 固化锁文件校验：`timeout 600s uv lock --locked`。
- 新增 `backend/scripts/run_workflow_langgraph_contract_smoke.py`，覆盖 remote thread create、本地 run/checkpoint 登记、pause/resume/cancel/replay/terminate 生命周期审计、copy/prune/delete cleanup。
- `run_system_doctor.py` 扩展到 19 项检查，新增 workflow LangGraph contract、capability policy precheck、distributed execution、multi-tenant smoke。
- `run_long_running_soak.py` 支持 `--duration-seconds`、`--sample-interval-seconds` 和 `--report-path`，记录 memory、disk、process count、event-loop latency、worker queue、checkpoint、active runs。
- Runtime Health alerts 接入顶部状态栏 badge，并在浏览器通知开启时触发 operator notification。
- QueryEngine 增加 summary quality scoring、stale running session recovery、replay context API。
- Capability operator policy 增加 `/api/capabilities/policies/precheck`，WebUI 增加签名 JSON 导入/导出面。
- Multi-tenant 增加 governance snapshot、policy update、delete 和 audit events，WebUI 增加 tenant 注册、policy apply、limit probe 和 registry 面。
- Distributed execution 继续使用已有 WebUI 操作面，并纳入 doctor smoke。

## 验证记录

已通过：

- `timeout 600s uv lock --locked`
- `backend/.venv/bin/python -m compileall -q src scripts`
- `backend/.venv/bin/python -m ruff check src scripts`
- `backend/scripts/run_workflow_langgraph_contract_smoke.py --json`
- `backend/scripts/run_long_running_soak.py --iterations 40 --duration-seconds 5 --sample-interval-seconds 2 --json`
- `backend/scripts/run_system_doctor.py --skip-git`，19 项 OK
- `frontend pnpm lint`
- `frontend pnpm typecheck`
- `frontend pnpm build`
- `backend/scripts/run_release_precheck.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --mock`，10 项 OK

说明：本次已提供真实多小时 soak 的脚本能力。验证阶段执行的是 5 秒短时版本，用于 release gate；生产推广前建议运行 `--duration-seconds 7200 --sample-interval-seconds 60 --report-path workspace/runtime/soak-2h.json` 作为两小时证明。

## 当前项目评估

OctoAgent 当前处于“可治理的准产品化系统”阶段。核心运行链路、能力治理、长期任务回收、环境锁定、doctor/precheck 和 WebUI operator 面已经成形。相比 P8，P9 的主要提升是：验证从单点 smoke 扩展到了可组合 release precheck；运行时风险从 API 指标扩展到前端 badge/通知；长期任务从 checkpoint prune 扩展到可采样稳定性曲线；policy 和 tenant 从“能查 API”推进到“operator 可操作”。

仍需注意：

- LangGraph remote pause/resume/cancel/replay/terminate 目前是 contract-level smoke，真实运行中 cancel/replay 的 remote 行为还需要基于实际 long-running run id 做在线验证。
- Multi-tenant registry 仍是内存态治理面，尚未接入持久存储、认证授权和资源隔离 enforcement。
- Distributed execution 有 registry 和 routing probe，但真实 remote dispatch worker/control plane 尚未完成。
- 对话摘要质量当前是启发式评分，后续应接入模型评审或 golden conversation replay。
- 真实 2 小时以上 soak 尚未在本次交互里等待完成，已经具备脚本和报告路径。

## 到最终完成的剩余工作与工作量

| 工作项 | 内容 | 估算工作量 |
| --- | --- | --- |
| LangGraph 真实远端生命周期闭环 | 针对实际运行 run id 完成 pause/resume/cancel/replay/terminate 的 remote 行为验证、错误恢复和 UI 操作 | 3-5 人日 |
| 真实多小时 soak 基线 | 运行 2h、8h、24h soak，建立资源回落阈值、历史报告留存和失败告警 | 2-4 人日 |
| Multi-tenant 产品化 | 持久化 tenant/policy、鉴权绑定、租户级 workspace/data/resource enforcement、审计导出 | 5-8 人日 |
| Distributed execution 产品化 | remote worker 注册、dispatch、结果回传、故障转移、节点权限和容量治理 | 6-10 人日 |
| QueryEngine 语义压缩升级 | 摘要质量模型评审、长会话 replay golden set、跨进程恢复、摘要退化检测 | 4-6 人日 |
| Operator policy 发布治理 | policy diff、签名校验、release approval、回滚和 CI gate | 2-4 人日 |
| 前端治理面精修 | Runtime Health、tenant、distributed、policy 的信息架构和空状态/错误状态统一 | 3-5 人日 |
| 安全与权限 | operator role、危险操作二次确认、审计不可抵赖、secret redaction | 4-7 人日 |
| 最终发布工程 | 生产部署文档、backup/restore、migration、observability dashboard、回归矩阵 | 5-8 人日 |

综合估算：距离“最终完成并可稳定生产推广”仍需约 34-57 人日。如果优先追求单机长期任务稳定运行和 operator 可治理，最小剩余闭环约 12-18 人日。

## 下一步优先级

1. 先跑 2 小时 soak 并保存报告，确认资源稳定区间。
2. 基于真实 LangGraph run id 做 remote cancel/replay 的端到端验证。
3. 将 multi-tenant registry 持久化，并把 tenant id 绑定到 workspace/query/capability policy。
4. 为 distributed execution 增加真实 remote worker dispatch。
5. 把 release precheck 接入 CI 或固定 operator release 命令。
