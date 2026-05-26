# OctoAgent 架构文档

> 最后更新：2026-04-26

## 1. 项目概述

OctoAgent 是一个模块化、可扩展的 AI 智能体框架，提供完整的对话式 AI 工作平台。核心特性包括：

- **多智能体协同**：主智能体 + 子智能体架构，支持链式、分支、群聊三种拓扑
- **沙箱执行**：支持本地、Docker、Kubernetes 三种代码执行隔离方式
- **工作流引擎**：基于卡片图（Card Graph）的任务编排与可视化
- **全链路可观测**：中间件链（15+）实现日志、追踪、权限管控
- **多渠道接入**：支持 Web UI、Slack、飞书、Telegram 等渠道
- **嵌入式模型**：内置 Bootstrap 模型用于冷启动、统一 RAG 语义检索

## 2. 系统架构总览

```
┌──────────────── 客户端层 ────────────────┐
│  Next.js 16 WebUI (Port 19806)           │
│  ├── Workspace 路由系统                   │
│  ├── Agent / Chat / Workflow 页面         │
│  ├── Neumorphic 设计系统 (9色主题)        │
│  └── @xyflow/react 画布可视化            │
└─────────────┬───────────────────────────┘
              │ REST / SSE
┌─────────────▼───────────────────────────┐
│  FastAPI Gateway (Port 19802)            │
│  ├── 38 个注册 Router 组（41 个 router 文件）│
│  ├── 配置管理 (config.yaml)              │
│  ├── 模型注册 & 自动推断                  │
│  └── CORS / 元数据 / 生命周期            │
└─────────────┬───────────────────────────┘
              │ HTTP / WebSocket
┌─────────────▼───────────────────────────┐
│  LangGraph Runtime (Port 19804)          │
│  ├── Lead Agent (核心对话图)              │
│  ├── 15+ Middleware Chain                │
│  ├── Tool Registry + MCP Provider        │
│  ├── SubAgent Orchestration              │
│  └── Checkpoint Persistence              │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│  执行层                                  │
│  ├── Local Sandbox (直接执行)             │
│  ├── Docker Sandbox (容器隔离)            │
│  ├── K8s Provisioner (Pod 调度)           │
│  └── Browser Runtime (自动化浏览器)       │
└──────────────────────────────────────────┘
```

## 3. 前端架构 (frontend/)

### 3.1 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Next.js | 16.1.6 | App Router SSR/CSR 框架 |
| React | 19.0.0 | UI 运行时 |
| TypeScript | 5.x | 类型安全 |
| Tailwind CSS | 4.0.15 | 原子化样式 |
| Radix UI | latest | 无障碍基础组件 |
| @xyflow/react | 12.10.0 | 工作流画布 |
| @tanstack/react-query | 5.x | 服务端状态管理 |
| @langchain/langgraph-sdk | latest | LangGraph 客户端 |
| CodeMirror | 6.x | 代码编辑器 |

### 3.2 目录结构

```
frontend/src/
├── app/                        # Next.js App Router
│   ├── layout.tsx              # 根布局 (主题/i18n/metadata)
│   ├── page.tsx                # 着陆页
│   ├── workspace/
│   │   ├── agents/             # 智能体管理
│   │   │   ├── page.tsx        # 列表页
│   │   │   ├── new/page.tsx    # 新建智能体
│   │   │   └── [agent_name]/chats/[thread_id]/page.tsx
│   │   ├── chats/              # 对话管理
│   │   │   ├── page.tsx        # 聊天列表
│   │   │   └── [thread_id]/page.tsx
│   │   ├── workflows/          # 工作流
│   │   │   ├── page.tsx        # 工作流列表 + 创建向导
│   │   │   └── [task_id]/page.tsx  # 工作流详情
│   │   ├── tasks/              # 任务管理
│   │   └── config/             # 系统设置
│   │       ├── models/         # 模型配置
│   │       ├── skills/         # 技能管理
│   │       ├── plugins/        # 插件管理
│   │       ├── channels/       # 渠道集成
│   │       ├── mcp/            # MCP 配置
│   │       └── evolution/      # 技能进化
│   └── mock/                   # Mock API (开发用)
│
├── components/
│   ├── ui/                     # ~40+ Shadcn/Radix 基础组件
│   ├── ai-elements/            # AI 专用组件
│   │   ├── canvas.tsx          # ReactFlow 画布封装
│   │   ├── artifact.tsx        # 制品渲染
│   │   ├── chain-of-thought.tsx # 思维链展示
│   │   ├── plan.tsx            # 计划展示
│   │   ├── prompt-input.tsx    # 富文本输入
│   │   └── reasoning.tsx       # 推理展示
│   ├── brand/                  # Logo / Avatar
│   ├── workspace/              # 核心工作区
│   │   ├── agents/             # 智能体卡片、列表
│   │   ├── chats/              # 对话框、消息流
│   │   ├── messages/           # 消息组件
│   │   ├── orchestrator/       # 编排器
│   │   │   ├── workflow-graph.tsx     # 工作流图 (ReactFlow)
│   │   │   ├── workflow-inspector.tsx # 工作流检查器
│   │   │   └── execution-console.tsx  # 执行控制台
│   │   ├── settings/           # 设置面板
│   │   ├── setup-wizard/       # 首次设置向导
│   │   └── task-card-graph.tsx # 任务卡片画布 (ReactFlow)
│   └── landing/                # 首页组件
│
├── core/                       # 业务逻辑层
│   ├── api/                    # HTTP 客户端
│   │   ├── api-client.ts       # LangGraphClient 单例
│   │   └── http.ts             # getJSON/postJSON/putJSON/deleteJSON
│   ├── agents/                 # 智能体 CRUD
│   │   ├── api.ts              # createAgent, updateAgent, deleteAgent, uploadAvatar
│   │   ├── hooks.ts            # useAgents, useCreateAgent
│   │   └── types.ts            # Agent interface
│   ├── task-workspaces/        # 任务工作区
│   │   ├── api.ts              # loadTaskWorkspace, updateTaskCardGraph
│   │   ├── hooks.ts            # useTaskWorkspace, useUpdateTaskCardGraph
│   │   └── types.ts            # TaskCard, TaskCardEdge, TaskCardGraph
│   ├── i18n/                   # 国际化 (5 语言)
│   │   ├── locales/            # zh-CN, zh-TW, en-US, ja, ko
│   │   ├── context.tsx         # I18nProvider
│   │   └── types.ts            # 类型定义 (~300+ key)
│   ├── models/                 # 模型管理
│   ├── threads/                # 会话线程
│   ├── brain/                  # 脑力(规划)
│   ├── settings/               # 本地设置 (含9色主题系统)
│   ├── skills/                 # 技能 CRUD
│   ├── plugins/                # 插件 CRUD
│   ├── channels/               # 渠道集成
│   ├── bootstrap/              # 嵌入式模型管理
│   ├── orchestration/          # 编排状态
│   ├── query-engine/           # 查询引擎
│   ├── runtime/                # 运行时能力
│   ├── tool-registry/          # 工具目录
│   └── todos/                  # TODO 管理
│
└── styles/
    └── globals.css             # Neumorphic 设计系统 (OKLCH 颜色)
```

### 3.3 核心调用链

```
用户交互 → page.tsx → hooks (useXxx) → api.ts → HTTP → Gateway → LangGraph
                                                            ↓
用户界面 ← component.tsx ← React Query 缓存 ← SSE/JSON ← Gateway
```

## 4. 后端架构 (backend/)

### 4.1 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.12 | 运行时 |
| FastAPI | 0.115 | REST API 网关 |
| LangGraph | 1.0.6 | 智能体图运行时 |
| Pydantic | 2.12.5 | 数据验证 |
| LiteLLM | latest | 多模型提供商适配 |
| DuckDB | latest | 嵌入式分析数据库 |
| sentence-transformers | 3.4 | 语义嵌入 |

### 4.2 模块结构

```
backend/src/
├── gateway/                    # FastAPI 网关层
│   ├── app.py                  # FastAPI() 实例 + 启动/关闭
│   ├── lifecycle.py            # 生命周期钩子
│   ├── router_registry.py      # 路由注册
│   └── routers/                # 41 个 router 文件
│       ├── agents.py           # /api/agents — CRUD + 头像上传
│       ├── models.py           # /api/models — 模型列表
│       ├── task_workspaces.py  # /api/task-workspaces — 工作区 CRUD
│       ├── brain.py            # /api/brain — 规划引擎
│       ├── skills.py           # /api/skills — 技能管理
│       ├── plugins.py          # /api/plugins — 插件管理
│       ├── channels.py         # /api/channels — IM 集成
│       ├── mcp.py              # /api/mcp — MCP 协议
│       ├── tools_registry.py   # /api/tools — 工具目录
│       ├── memory.py           # /api/memory — 记忆管理
│       ├── system_execution.py # /api/system — 系统执行
│       ├── uploads.py          # /api/uploads — 文件上传
│       └── ... (13 more)
│
├── agents/                     # 智能体核心
│   ├── lead_agent/
│   │   ├── agent.py            # make_lead_agent() 工厂函数
│   │   ├── builder.py          # 图构建器 (LangGraph StateGraph)
│   │   ├── middleware_builder.py # 中间件链组装
│   │   ├── prompt.py           # 系统提示词模板
│   │   └── runtime.py          # LeadAgentRuntimeResolver
│   ├── middlewares/            # 15+ 中间件
│   │   ├── clarification_middleware.py   # 澄清确认
│   │   ├── client_command_middleware.py  # 客户端命令
│   │   ├── continuation_middleware.py    # 续写控制
│   │   ├── dangling_tool_call_middleware.py # 孤立工具调用修复
│   │   ├── memory_middleware.py          # 记忆注入
│   │   ├── runtime_state_middleware.py   # 运行时状态同步
│   │   ├── session_compaction_middleware.py# 会话压缩
│   │   ├── skill_evolution_middleware.py  # 技能进化触发
│   │   ├── subagent_limit_middleware.py  # 子智能体限制
│   │   ├── thread_data_middleware.py     # 线程数据注入
│   │   ├── title_middleware.py           # 自动标题
│   │   ├── todo_middleware.py            # TODO 状态同步
│   │   ├── uploads_middleware.py         # 文件上传处理
│   │   └── view_image_middleware.py      # 图像查看
│   ├── memory/                 # 记忆子系统
│   │   ├── updater.py          # 记忆更新器
│   │   └── queue.py            # 记忆队列
│   ├── checkpointer/           # 检查点持久化
│   └── thread_state.py         # SandboxState, ThreadState
│
├── brain/                      # 规划引擎
│   ├── planner.py              # 任务规划
│   ├── strategy_graph.py       # 策略图构建
│   ├── research.py             # 研究模式
│   ├── quant.py                # 定量分析
│   ├── policy.py               # 政策引擎
│   └── evidence.py             # 证据推理
│
├── task_workspaces/            # 任务工作区
│   ├── contracts.py            # TaskWorkspace, TaskCard, TaskCardEdge, TaskCardGraph
│   ├── defaults.py             # TaskWorkspaceBlueprintFactory
│   │   ├── make_agents()       # 创建智能体列表 (支持主/子智能体)
│   │   ├── build_card_graph()  # 构建卡片图 (支持 branch/group/chain 拓扑)
│   │   └── _agent_blueprints_from_wizard() # 向导数据生成蓝图
│   ├── service.py              # TaskWorkspaceService
│   │   ├── create_workspace()  # 解析 summary JSON → 生成卡片图
│   │   ├── update_workspace()  # 更新工作区
│   │   └── list_workspaces()   # 列表
│   ├── card_templates.py       # TaskCardTemplateFactory
│   ├── execution.py            # 任务执行引擎
│   ├── planner.py              # 工作区级规划
│   └── store.py                # 持久化存储
│
├── config/                     # 配置管理 (20+ 配置模块)
│   ├── app_config.py           # AppConfig 主配置
│   ├── model_config.py         # 模型配置
│   ├── model_auto_inference.py # 模型自动推断
│   ├── agents_config.py        # 智能体配置
│   ├── sandbox_config.py       # 沙箱配置
│   └── ... (16 more)
│
├── models/                     # 模型管理
│   ├── factory.py              # 模型工厂 (多提供商)
│   ├── embedding_service.py    # 语义嵌入服务
│   └── runtime_telemetry.py    # 运行时遥测
│
├── subagents/                  # 子智能体编排
│   ├── executor.py             # 子智能体执行器
│   ├── policy.py               # 编排策略 (coordinator_workers/manager_review)
│   ├── catalog.py              # 子智能体目录
│   └── registry.py             # 注册中心
│
├── sandbox/                    # 代码执行沙箱
│   ├── sandbox.py              # 沙箱接口
│   ├── sandbox_provider.py     # 提供商工厂 (local/docker/k8s)
│   ├── local/                  # 本地执行
│   └── tools.py                # 沙箱工具
│
├── tools/                      # 内置工具
│   ├── catalog.py              # 工具目录
│   ├── mcp_provider.py         # MCP 工具提供商
│   └── builtins/               # 内置工具实现
│       ├── task_tool.py
│       └── web_reader_tool.py
│
├── skills/                     # 技能系统
│   ├── loader.py               # 技能加载器
│   └── parser.py               # 技能解析器
│
├── skill_evolution/            # 技能自动进化
│   ├── evolver.py              # 进化器
│   └── quality_monitor.py      # 质量监控
│
├── channels/                   # 多渠道集成
│   ├── slack.py                # Slack
│   ├── feishu.py               # Feishu / Lark
│   ├── telegram.py             # Telegram
│   ├── external_bridge.py      # 外部桥接型渠道
│   ├── service.py              # 渠道生命周期与 registry
│   ├── manager.py              # ChannelManager / LangGraph 分发
│   ├── store.py                # chat/thread 映射持久化
│   └── message_bus.py          # 消息总线
│
├── mcp/                        # Model Context Protocol
│   ├── client.py               # MCP 客户端
│   └── tools.py                # MCP 工具
│
├── community/                  # 社区扩展
│   ├── tavily/                 # 搜索引擎
│   ├── jina_ai/                # Jina AI 工具
│   └── image_search/           # 图片搜索
│
├── system_guard/               # 安全护栏
├── session_compaction/         # 会话压缩
├── browser_runtime/            # 浏览器自动化
├── research_runtime/           # 研究运行时
├── bootstrap/                  # 嵌入式模型 Bootstrap
├── query_engine/               # 查询引擎
├── plugins/                    # 插件系统
└── utils/                      # 工具函数
```

### 4.3 核心调用链

```
HTTP 请求 → FastAPI Router → Service Layer → LangGraph Agent
                                    ↓
                             TaskWorkspaceService
                             ├── make_agents(primary_agent, sub_agents)
                             ├── build_card_graph(mode, topology)
                             └── create_workspace()
                                    ↓
                             LangGraph StateGraph
                             ├── Lead Agent Node
                             ├── Middleware Chain (15+)
                             ├── Tool Execution
                             └── Checkpoint Persistence
```

## 5. 工作流系统

### 5.1 执行模式

| 模式 | 英文 | 说明 |
|------|------|------|
| 主智能体 | single | 单一智能体独立执行任务 |
| 分支模式 | branch | 主智能体分发 → 子智能体并行 → 汇报合并 |
| 群聊模式 | group | 所有智能体双向通信，围成圆形协作 |
| 链式模式 | chain | 主 → 子1 → 子2 顺序传递 |

### 5.2 卡片图 (Card Graph)

工作流创建后生成 TaskCardGraph，包含：
- **Card 1**：项目信息卡 (kind=start, tags=[project, entry])
- **Card 2**：主智能体卡 (kind=agent, tags=[agent, primary])
- **Card 3+**：子智能体卡 (kind=agent, tags=[agent, sub-agent])

卡片之间的边 (TaskCardEdge) 表示关系：
- `orchestrates`：项目 → 主智能体
- `dispatches`：主智能体 → 子智能体 (任务派发)
- `reports`：子智能体 → 主智能体 (结果汇报)
- `collaborates`：子智能体 ↔ 子智能体 (群聊模式互联)
- `chain`：顺序传递 (链式模式)

### 5.3 前端画布可视化

`task-card-graph.tsx` 使用 `@xyflow/react` + `ReactFlowProvider` 实现：
- 三种拓扑自动布局 (树状/半圆/链式)
- 卡片可自由拖动
- 双向箭头连接线
- 双击编辑子智能体任务描述
- 拖拽添加 / Delete 键删除边
- 变更自动持久化至后端

## 6. 部署架构

### 6.1 端口分配

| 服务 | 端口 | 说明 |
|------|------|------|
| Next.js Frontend | 19806 | WebUI |
| FastAPI Gateway | 19802 | REST API |
| LangGraph Runtime | 19804 | Agent 运行时 |
| Nginx (Docker) | 19800 | 反向代理 / 统一入口 / `/auth/register` 注册登录页 |

### 6.2 部署方式

**本地开发**：
```bash
# 前端
cd frontend && pnpm exec next dev --turbo --hostname 127.0.0.1 --port 19806
# 网关
cd backend && .venv/bin/python -m uvicorn src.gateway.app:app --host 127.0.0.1 --port 19802
# LangGraph
cd backend && .venv/bin/python -m langgraph_cli dev --no-browser --allow-blocking --host 127.0.0.1 --port 19804
```

**Docker Compose**：
```bash
docker compose -f docker/docker-compose-dev.yaml up
```

**生产部署**：
- Systemd 服务：`deploy/octoagent-local.service`
- K8s Provisioner：`docker/provisioner/`

## 7. 配置系统

主配置文件：`config.yaml`
- 模型定义 (provider, model_name, capabilities)
- 运行时配置 (sandbox, permissions)
- 集成配置 (channels, MCP)

环境变量：`.env`
- API Keys (OPENAI_API_KEY, ANTHROPIC_API_KEY 等)
- 端口配置
- 数据库路径

## 8. 国际化

支持 5 种语言：zh-CN、zh-TW、en-US、ja、ko
- 300+ 翻译 key
- 前端 `core/i18n/` 模块化管理
- `useI18n()` Hook 提供翻译函数
