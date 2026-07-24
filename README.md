# OctoAgent

OctoAgent 是一个可审计、自托管的通用 Agent 系统。当前版本只保留一条
生产执行链：LangGraph Agent Runtime 负责模型回合与运行状态，Harness
负责能力发现、权限、工具执行、产物和记忆。

当前版本：`20260724.1.0`

## 架构

```text
Browser
  |
Nginx :19800
  |------------------------------|
  v                              v
Next.js WebUI :19806       app-server :19802
                              |
                Agent Runtime + Harness
                   |              |
                   v              v
          PostgreSQL/pgvector   Executors
                             /      |       \
                        sandbox    MCP    system-executor
                                             |
                                             v
                                      Docker host / Internet
```

Docker Compose 启动五个服务：

| 服务 | 职责 |
| --- | --- |
| `nginx` | WebUI 与 API 的唯一入口 |
| `frontend` | Next.js WebUI |
| `app-server` | FastAPI、LangGraph、Harness、记忆 |
| `system-executor` | 经过认证的主机 root 执行边界 |
| `postgres` | checkpoint、项目、配置、trace、pgvector 索引 |

Redis、独立 Gateway、独立 LangGraph、Tools Hub、Brain Core、Local Work
Bus 和第二套 Task/Run/Event 状态机均不在当前生产架构中。

## 安装

生产环境只支持 Docker Compose。主机不需要安装 Python、Node.js、
pnpm、Nginx 或 PostgreSQL。

Linux / macOS：

```bash
curl -fsSL https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.sh | bash
```

Windows PowerShell：

```powershell
iwr https://raw.githubusercontent.com/sievepub-2000/octoagent/main/scripts/install-docker.ps1 -UseBasicParsing | iex
```

已有仓库：

```bash
cp .env.docker.example .env.docker
# 填写 .env.docker 中的密钥
docker compose --env-file .env.docker up -d --build --remove-orphans
```

打开 `http://127.0.0.1:19800`。完整安装、升级、停止和卸载说明见
[Docker 部署文档](docs/docker-install.md)。

## 权限模式

对话栏中的 Permission Mode 是真实的服务端执行策略，不是 UI 标签：

- `directory`：只允许项目目录和沙箱执行。
- `approval`：敏感动作需要确认，且仍受项目权限上限约束。
- `system`：Harness 才能把请求转交给独立的 `system-executor`；该容器以
  root 身份访问主机 Docker socket 和授权挂载。

前端不能绕过服务端策略。项目权限上限、对话选择和执行适配器会在
Harness 分发时再次校验。

## 记忆

- Markdown 是可读、可迁移、可重建的唯一原始记忆。
- 每个已完成回合自动提取精简信息并原子写入 Markdown。
- PostgreSQL `pgvector` 保存派生向量和 HNSW 索引，用于回忆。
- Harness 启动时扫描 Markdown 并补齐缺失索引。
- 删除向量索引不会丢失原始记忆；可从 Markdown 完整重建。

## 模型

OctoAgent 不在应用容器中嵌入模型权重。任何 OpenAI-compatible 服务、
Google GenAI、NVIDIA NIM、OpenRouter 等均作为普通 Provider 配置。
本地 llama.cpp 也在应用容器之外运行。

模型和 Provider 在 WebUI 的 Models 页面管理，运行时配置保存在挂载的
`runtime/config` 中。不要把密钥提交到 Git。

## 更新

```bash
git pull --ff-only
docker compose --env-file .env.docker up -d --build --remove-orphans
```

数据卷与 `runtime/` 配置在镜像更新时保留。更新前仍建议对 PostgreSQL
卷和运行时配置做常规备份。

## 验证

```bash
docker compose --env-file .env.docker ps
curl -fsS http://127.0.0.1:19800/health
curl -fsS http://127.0.0.1:19800/api/runtime/doctor

cd backend
uv run --frozen pytest -q
uvx ruff check src scripts tests
python -m compileall -q src scripts
cd ..

backend/.venv/bin/python scripts/verify-module-lifecycles.py \
  --base-url http://127.0.0.1:19800 \
  --env-file .env.docker
```

前端：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build
```

## 目录

| 路径 | 内容 |
| --- | --- |
| `backend/src/agents` | LangGraph Agent Runtime |
| `backend/src/harness` | 能力、权限、执行、trace、产物、记忆 |
| `backend/src/gateway` | 同进程 FastAPI 控制接口 |
| `frontend` | WebUI |
| `runtime` | 挂载的配置、工具目录和 Markdown 记忆 |
| `skills` | 内置 Skill |
| `compose.yaml` | 唯一生产拓扑 |

## 许可证与联系

项目采用 SSPL v1 与商业许可双重授权；Bytedance 派生部分继续遵循
MIT，详情见 [LICENSE](LICENSE)、[NOTICE.md](NOTICE.md) 和
[商业许可 FAQ](docs/COMMERCIAL_LICENSE_FAQ.md)。

- Bug 与功能建议：GitHub Issues
- 安全问题与商业许可：`zillafan80@gmail.com`
