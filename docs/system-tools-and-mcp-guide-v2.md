# OctoAgent 系统工具调用说明文档

**版本**: v2.0  
**更新日期**: 2026-06-30  
**维护者**: OctoAgent Team

---

## 一、MCP 服务器调用指南

### 1.1 文件系统 MCP (filesystem)

**功能描述**: 系统级文件操作，支持完整的主机文件系统访问（受聊天权限模式保护）

**可用工具**:
| 工具名 | 用途 | 使用场景 |
|--------|------|----------|
| `read_file` | 读取文件内容 | 查看配置文件、日志、代码文件 |
| `read_text_file` | 读取文本文件 | 阅读文档、脚本、配置文件 |
| `read_media_file` | 读取媒体文件 | 查看图片、音频、视频元数据 |
| `read_multiple_files` | 批量读取文件 | 分析多个相关文件、代码审查 |
| `write_file` | 写入文件内容 | 创建新文件、保存结果、生成报告 |
| `edit_file` | 编辑文件内容 | 修改配置、修复代码、更新文档 |
| `create_directory` | 创建目录 | 组织项目结构、创建临时工作区 |
| `list_directory` | 列出目录内容 | 浏览文件夹、查找文件 |
| `list_directory_with_sizes` | 带大小的目录列表 | 分析磁盘使用、查找大文件 |
| `directory_tree` | 生成目录树 | 可视化项目结构、文档编写 |
| `move_file` | 移动文件/目录 | 整理文件、迁移数据 |
| `search_files` | 搜索文件内容 | 代码搜索、日志分析、配置查找 |
| `get_file_info` | 获取文件信息 | 查看权限、大小、修改时间 |
| `list_allowed_directories` | 列出允许访问的目录 | 安全检查、权限验证 |

**调用示例**:
```python
# 读取配置文件
read_file(path="/home/sieve-pub/public-workspace/octoagent/backend/.env")

# 搜索代码中的特定模式
search_files(pattern="TODO", path="/home/sieve-pub/public-workspace/octoagent/backend/src", recursive=True)

# 创建项目目录结构
create_directory(path="/home/sieve-pub/public-workspace/new-project/docs")
```

**注意事项**:
- 受 `permission_scope: sandbox` 保护，仅允许访问沙箱目录
- 敏感文件操作需要额外权限确认

---

### 1.2 PostgreSQL MCP (postgres)

**功能描述**: 本地 PostgreSQL 数据库连接，支持 SQL 查询和数据管理

**可用工具**:
| 工具名 | 用途 | 使用场景 |
|--------|------|----------|
| `query` | 执行 SQL 查询 | 数据检索、统计分析、表结构查看 |

**调用示例**:
```python
# 查询项目列表
query(sql="SELECT * FROM projects LIMIT 10")

# 统计任务数量
query(sql="SELECT COUNT(*) as task_count FROM tasks WHERE status = 'completed'")

# 查看表结构
query(sql="SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'projects'")
```

**注意事项**:
- 数据库连接：`postgresql://root@localhost:5432/sieve_pub`
- 仅支持 SELECT 查询（只读模式）
- 复杂查询建议分批执行避免超时

---

### 1.3 OpenAPI MCP (openapi) - 含 http-api_probe

**功能描述**: OpenAPI MCP 包暴露 OctoAgent 网关端点作为 MCP 资源/工具。集成 http-api_probe 用于健康检查和 API 冒烟测试。

**可用工具**:
| 工具名 | 用途 | 使用场景 |
|--------|------|----------|
| `list-api-endpoints` | 列出所有 API 端点 | 查看可用接口、API 文档生成 |
| `get-api-endpoint-schema` | 获取端点 Schema | 了解请求/响应格式、参数验证 |
| `invoke-api-endpoint` | 调用 API 端点 | 测试接口、获取实时数据 |
| `http_api_probe` | HTTP API 探测（已集成） | 健康检查、网关连通性验证 |

**调用示例**:
```python
# 列出所有 API 端点
list-api-endpoints()

# 获取项目端点的 Schema
get-api-endpoint-schema(endpoint="/api/projects", method="GET")

# 调用创建项目接口
invoke-api-endpoint(endpoint="/api/projects", method="POST", body={"name": "新项目"})

# 健康检查（已集成到 openapi）
http_api_probe(url="http://127.0.0.1:19802/openapi.json")
```

**注意事项**:
- API 基础 URL：`http://127.0.0.1:19802`
- OpenAPI Spec：`http://127.0.0.1:19802/openapi.json`
- `http_api_probe` 已合并到 openapi，无需单独配置 http-api MCP

---

### 1.4 Docker MCP (docker)

**功能描述**: 本地 Docker 守护进程连接，包含安全的容器列表/版本冒烟检查

**可用工具**:
| 工具名 | 用途 | 使用场景 |
|--------|------|----------|
| `docker_container_list` | 列出容器 | 查看运行中的容器、状态监控 |
| `docker_container_inspect` | 检查容器详情 | 获取 IP、端口映射、配置信息 |
| `docker_container_start` | 启动容器 | 恢复暂停的容器、部署服务 |
| `docker_container_stop` | 停止容器 | 临时关闭服务、维护操作 |
| `docker_container_restart` | 重启容器 | 应用更新、故障恢复 |
| `docker_container_logs` | 查看容器日志 | 调试问题、监控运行状态 |
| `docker_system_info` | 系统信息 | 查看 Docker 版本、存储驱动 |
| `docker_system_version` | 版本信息 | 检查 Docker CE/EE 版本 |

**调用示例**:
```python
# 列出所有容器（包括未运行的）
docker_container_list(all=True)

# 查看 NGINX 容器日志
docker_container_logs(container="nginx", tail=100)

# 重启 LangGraph 服务
docker_container_restart(container="langgraph")
```

**注意事项**:
- 环境变量：`DOCKER_MCP_LOCAL=true`
- 仅支持本地 Docker 守护进程操作
- 容器操作需要适当的权限（通常由 docker 组管理）

---

### 1.5 Docker Compose MCP (docker-compose)

**功能描述**: 本地 Docker Compose 检查，用于版本和 compose 配置验证

**可用工具**:
| 工具名 | 用途 | 使用场景 |
|--------|------|----------|
| `compose_version` | 查看 Compose 版本 | 兼容性检查、功能确认 |
| `compose_config_check` | 检查配置文件 | 部署前验证、错误排查 |

**调用示例**:
```python
# 查看 Docker Compose 版本
compose_version()

# 检查当前目录的 compose 配置
compose_config_check(file="docker-compose.yml")
```

**注意事项**:
- 与 docker MCP 配合使用，专注于编排层面
- config_check 可验证 YAML 语法和服务定义正确性

---

### 1.6 Redis MCP (redis)

**功能描述**: 本地 Redis 连接，用于缓存/会话键检查

**可用工具**:
| 工具名 | 用途 | 使用场景 |
|--------|------|----------|
| `set` | 设置键值对 | 缓存数据、存储临时状态 |
| `get` | 获取键值 | 读取缓存、恢复会话 |
| `delete` | 删除键 | 清理过期数据、重置状态 |
| `list` | 列出匹配的键 | 查找特定前缀的缓存、调试 |

**调用示例**:
```python
# 设置会话缓存
set(key="session:abc123", value="{\"user_id\": 456}", expire=3600)

# 获取用户缓存
get(key="user:456")

# 查找所有 session 前缀的键
list(pattern="session:*")

# 删除过期会话
delete(key="session:expired_123")
```

**注意事项**:
- Redis 连接：`redis://localhost:6379`
- 支持 TTL（过期时间）设置
- list 操作使用 pattern 匹配（支持 * ? 通配符）

---

### 1.7 X-MCP (x-mcp) - 默认搜索引擎

**功能描述**: X (Twitter) 搜索引擎 MCP，用于搜索推文、用户和趋势。**作为默认搜索引擎使用**。

**可用工具**:
| 工具名 | 用途 | 使用场景 |
|--------|------|----------|
| `x_search` | 搜索推文/用户 | 舆情监控、热点追踪、信息检索 |
| `x_user_lookup` | 查询用户信息 | 账号验证、粉丝分析 |
| `x_trends` | 获取趋势话题 | 热门话题监控、内容策划 |

**调用示例**:
```python
# 搜索关于 octoagent 的推文
x_search(query="octoagent", result_type="mixed", count=20)

# 查询特定用户信息
x_user_lookup(username="octoagent_ai")

# 获取当前趋势话题
x_trends(location="worldwide")
```

**注意事项**:
- **默认搜索引擎**：优先使用 x-mcp 进行网络搜索
- 与其他搜索引擎（web_search、image_search）配合使用，覆盖不同数据源
- 需要 X/Twitter API 凭证支持

---

## 二、Skills 调用指南

### 2.1 研究类 Skills

#### autoresearch
**功能**: Karpathy 灵感的研究循环，4 阶段实验流程（假设→实验→分析→迭代）

**使用场景**:
- 技术调研项目
- A/B 测试设计
- 算法优化实验

**调用方式**: 在 Agent 会话中引用 `@autoresearch` 激活研究循环工作流

---

#### tokenspeed-benchmark
**功能**: LLM 推理基准测试规划

**使用场景**:
- 模型性能对比
- 推理速度评估
- 成本效益分析

**调用方式**: 在 Agent 会话中引用 `@tokenspeed-benchmark` 激活基准测试流程

---

### 2.2 设计类 Skills

#### pencil-design ⭐ (最完整)
**功能**: 设计-to-code 工作流，含 MCP 工具参考表（12 个工具）、6 条核心规则、Tailwind CSS 映射

**使用场景**:
- UI/UX 设计实现
- 前端开发
- 设计系统构建

**调用方式**: 在 Agent 会话中引用 `@pencil-design` 激活设计工作流

---

#### beautiful-html-templates
**功能**: HTML 幻灯片模板选择

**使用场景**:
- 演示文稿制作
- 报告可视化
- 会议展示

**调用方式**: 在 Agent 会话中引用 `@beautiful-html-templates` 选择模板

---

#### ian-handdrawn-ppt
**功能**: 中文手绘技术图片 deck

**使用场景**:
- 技术培训材料
- 概念解释图示
- 创意演示

**调用方式**: 在 Agent 会话中引用 `@ian-handdrawn-ppt` 生出手绘风格内容

---

### 2.3 浏览器与视觉类 Skills

#### cloakbrowser-controlled-browser ⭐ (需授权)
**功能**: 受控浏览器自动化（需要用户授权）

**使用场景**:
- 网页数据采集
- 自动化测试
- 表单填写

**调用方式**: 在 Agent 会话中引用 `@cloakbrowser-controlled-browser`，**需要明确用户授权**

---

#### peekaboo-vision-mcp
**功能**: MCP 视觉 QA 工作流

**使用场景**:
- UI 元素识别
- 截图分析
- 视觉回归测试

**调用方式**: 在 Agent 会话中引用 `@peekaboo-vision-mcp` 激活视觉检查流程

---

#### photo-agents
**功能**: 视觉/计算机操作任务 skill

**使用场景**:
- 图像识别
- 屏幕操作指导
- 视觉任务分解

**调用方式**: 在 Agent 会话中引用 `@photo-agents` 处理视觉任务

**与 peekaboo-vision-mcp 的区别**:
- `peekaboo-vision-mcp`: 专注于 MCP 工具集成的 QA 工作流
- `photo-agents`: 更通用的视觉/计算机操作任务处理

---

### 2.4 内容发布类 Skills

#### cheat-on-content
**功能**: 内容发布校准工作流

**使用场景**:
- 博客/文章发布前检查
- SEO 优化验证
- 多平台适配确认

**调用方式**: 在 Agent 会话中引用 `@cheat-on-content` 激活发布校准流程

---

### 2.5 图表与可视化类 Skills

#### fireworks-tech-graph
**功能**: 技术图表生成（SVG/PNG）

**使用场景**:
- 架构图绘制
- 流程图生成
- 数据可视化

**调用方式**: 在 Agent 会话中引用 `@fireworks-tech-graph` 生成功能图

---

### 2.6 项目管理类 Skills

#### goalbuddy
**功能**: 目标合约 skill，用于目标设定与追踪

**使用场景**:
- OKR 制定
- 任务分解
- 进度追踪

**调用方式**: 在 Agent 会话中引用 `@goalbuddy` 激活目标管理流程

---

#### get-shit-done ⭐ (含详细元数据)
**功能**: 5 条核心规则 + 反模式表 + 决策树 + 提交协议

**使用场景**:
- 任务执行优化
- 工作流标准化
- 避免常见陷阱

**调用方式**: 在 Agent 会话中引用 `@get-shit-done` 激活高效工作流

---

### 2.7 技术规范类 Skills

#### spec-kit ⭐ (含详细元数据)
**功能**: BDD 场景模板、API 合约 YAML 模板、质量门控

**使用场景**:
- 需求规格编写
- API 设计文档
- 测试用例生成

**调用方式**: 在 Agent 会话中引用 `@spec-kit` 激活规范编写流程

---

#### voltagent-best-practices ⭐ (含详细元数据)
**功能**: VoltAgent 代码示例、布局规范、内存默认值、服务器选项

**使用场景**:
- VoltAgent 项目开发
- 最佳实践遵循
- 性能优化配置

**调用方式**: 在 Agent 会话中引用 `@voltagent-best-practices` 激活规范检查

---

### 2.8 系统诊断类 Skills

#### witr-runtime-diagnosis
**功能**: 运行时进程诊断

**使用场景**:
- 服务故障排查
- 性能瓶颈分析
- 日志分析

**调用方式**: 在 Agent 会话中引用 `@witr-runtime-diagnosis` 激活诊断流程

---

### 2.9 架构与配置类 Skills

#### lightseek-smg-gateway
**功能**: SMG 模型路由实验规划

**使用场景**:
- 多模型路由策略
- 网关配置优化
- 实验设计

**调用方式**: 在 Agent 会话中引用 `@lightseek-smg-gateway` 激活路由规划流程

---

#### mirage-vfs
**功能**: 虚拟文件系统规划（有界 VFS 合约）

**使用场景**:
- 虚拟化存储设计
- 文件抽象层实现
- 跨平台文件管理

**调用方式**: 在 Agent 会话中引用 `@mirage-vfs` 激活 VFS 规划流程

---

### 2.10 Agent 规则类 Skills

#### agent-rules-books
**功能**: Agent 规则与审查启发式

**使用场景**:
- Agent 行为约束
- 安全审查
- 最佳实践遵循

**调用方式**: 在 Agent 会话中引用 `@agent-rules-books` 激活规则检查流程

---

## 三、搜索引擎使用策略

### 3.1 搜索引擎列表（全部保留）

| 搜索引擎 | 覆盖范围 | 优先级 | 使用场景 |
|----------|----------|--------|----------|
| **x-mcp** | X/Twitter 推文、用户、趋势 | ⭐ 默认 | 舆情监控、热点追踪、社交数据 |
| web_search | 通用网页搜索 | 高 | 一般信息查询、新闻、文档 |
| image_search | Bing 图片搜索 | 中 | 图片素材查找、视觉参考 |

### 3.2 调用策略

1. **默认优先**: 所有搜索引擎请求优先使用 `x-mcp`（作为默认搜索引擎）
2. **互补使用**: 
   - 需要社交数据 → x-mcp
   - 需要通用信息 → web_search
   - 需要图片素材 → image_search
3. **不删除原则**: 各搜索引擎覆盖范围不同，全部保留以确保数据源多样性

---

## 四、工具调用决策树

```
用户请求
    ↓
[是什么类型的任务？]
    ├─ 文件操作 → filesystem MCP
    ├─ 数据库查询 → postgres MCP
    ├─ API 测试/健康检查 → openapi MCP (含 http_api_probe)
    ├─ Docker 管理 → docker + docker-compose MCP
    ├─ 缓存/会话 → redis MCP
    ├─ 社交搜索 → x-mcp (默认搜索引擎)
    ├─ 通用搜索 → web_search
    ├─ 图片搜索 → image_search
    └─ 专业工作流 → 对应 Skills (@skill-name)
```

---

## 五、MCP 服务器配置总览

| MCP 名称 | 状态 | 工具数 | 权限范围 | 描述 |
|----------|------|--------|----------|------|
| filesystem | ✅ enabled | 14 | sandbox | 系统级文件操作 |
| postgres | ✅ enabled | 1 | sandbox | PostgreSQL 查询 |
| openapi | ✅ enabled | 4 (含 http_api_probe) | sandbox | API 端点 + 健康检查 |
| docker | ✅ enabled | 8 | sandbox | Docker 容器管理 |
| docker-compose | ✅ enabled | 2 | sandbox | Compose 配置验证 |
| redis | ✅ enabled | 4 | sandbox | Redis 缓存操作 |
| x-mcp | ✅ enabled | 3+ | sandbox | X/Twitter 搜索引擎（默认） |

**已删除**: kubernetes (disabled, kubectl 不可用)  
**已合并**: http-api → openapi (以 openapi 为基准集成)

---

## 六、更新日志

### v2.0 (2026-06-30)
- ✅ 删除 kubernetes MCP（disabled）
- ✅ 合并 http-api 到 openapi MCP
- ✅ 添加 x-mcp 作为默认搜索引擎
- ✅ 重新整理 Skills 调用说明（18 个 skills，功能无完全重叠）
- ✅ 明确搜索引擎使用策略（全部保留，x-mcp 优先）

### v1.0 (2026-05-28)
- 初始版本发布
- 基础 MCP 服务器配置
- Skills 目录初始化

---

*文档维护：OctoAgent Team*  
*最后更新：2026-06-30T21:45 HKT*
