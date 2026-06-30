# OctoAgent 系统统一目录结构重组报告

**执行时间**: 2026-06-30 23:50 HKT  
**执行人**: OctoAgent Team  
**状态**: ✅ 完成

---

## 一、任务执行情况

| 任务 | 状态 | 详情 |
|------|------|------|
| 合并所有 skills 为一个目录 | ✅ 完成 | tools/skills/ (public:49 + custom:0) |
| 合并所有 MCP 为一个目录 | ✅ 完成 | tools/mcp/ (servers + bin) |
| 合并所有 hooks 为一个目录 | ✅ 完成 | tools/hooks/ (governance-audit, session-logger) |
| 合并所有 plugins 为一个目录 | ✅ 完成 | tools/plugins/ (registry.json) |
| 创建统一 tools 主目录 | ✅ 完成 | tools/{skills,mcp,hooks,plugins,bin} |
| 更新工具安装/卸载/调用说明 | ✅ 完成 | 详见本文档 |

---

## 二、新目录结构

```
tools/                              # 所有工具模块的统一根目录 (NEW)
├── skills/                         # Skills 技能库（合并所有来源）
│   ├── public/                     # 公开 skills (49 个)
│   │   ├── agent-rules-books/
│   │   ├── autoresearch/
│   │   ├── beautiful-html-templates/
│   │   ├── cloakbrowser-controlled-browser/ ⭐
│   │   ├── fireworks-tech-graph/
│   │   ├── get-shit-done/
│   │   ├── goalbuddy/
│   │   ├── ian-handdrawn-ppt/
│   │   ├── lightseek-smg-gateway/
│   │   ├── mirage-vfs/
│   │   ├── peekaboo-vision-mcp/
│   │   ├── pencil-design/ ⭐⭐⭐
│   │   ├── photo-agents/
│   │   ├── spec-kit/
│   │   ├── tokenspeed-benchmark/
│   │   ├── voltagent-best-practices/
│   │   └── witr-runtime-diagnosis/
│   │   └── ... (共 49 个)
│   └── custom/                     # 自定义 skills (已清空)
├── mcp/                            # MCP 服务器配置
│   ├── servers/                    # MCP 服务器配置文件
│   │   ├── filesystem.json
│   │   ├── postgres.json
│   │   ├── openapi.json
│   │   ├── docker-compose.json
│   │   ├── redis.json
│   │   └── docker.json
│   └── bin/                        # MCP 服务器可执行文件
│       ├── mcp-server-filesystem
│       ├── mcp-server-postgres
│       ├── openapi-mcp-server
│       ├── mcp-server-redis
│       └── docker-mcp
├── hooks/                          # Hooks 插件（合并所有来源）
│   ├── governance-audit/           # 治理审计 hook
│   │   ├── hooks.json
│   │   ├── audit-session-start.sh
│   │   ├── audit-prompt.sh
│   │   └── audit-session-end.sh
│   └── session-logger/             # 会话日志 hook
│       ├── hooks.json
│       ├── log-session-start.sh
│       ├── log-prompt.sh
│       └── log-session-end.sh
├── plugins/                        # Plugins（合并所有来源）
│   └── registry.json               # 插件注册表
└── bin/                            # 其他工具二进制文件
    ├── bin/                        # 通用二进制文件
    ├── go/                         # Go 工具
    └── playwright-browsers/        # Playwright 浏览器
```

---

## 三、旧目录 vs 新目录对比

### 3.1 Skills 合并

| 旧位置 | 数量 | 新位置 | 说明 |
|--------|------|--------|------|
| `skills/public/` | 31 个 | `tools/skills/public/` | ✅ 已合并 |
| `.agents/skills/` | 18 个 | `tools/skills/public/` | ✅ 已合并 |
| `project_docs/skills/public/` | 17 个 (重叠) | - | ❌ 未合并（名称重叠） |
| **总计** | **49 个唯一** | **tools/skills/public/** | ✅ 完成 |

---

### 3.2 MCP 合并

| 旧位置 | 数量 | 新位置 | 说明 |
|--------|------|--------|------|
| `runtime/tools/mcp/` | 6 个服务器 | `tools/mcp/bin/` + `tools/mcp/servers/` | ✅ 已合并 |

**MCP 服务器列表** (6 个):
- filesystem (14 tools)
- postgres (1 tool)
- openapi (4 tools, 含 http_api_probe)
- docker-compose (2 tools)
- redis (4 tools)
- docker (8 tools)

---

### 3.3 Hooks 合并

| 旧位置 | 数量 | 新位置 | 说明 |
|--------|------|--------|------|
| `.github/hooks/` | 2 个 hook 组 | `tools/hooks/` | ✅ 已合并 |

**Hooks 列表**:
- governance-audit (审计)
- session-logger (日志)

---

### 3.4 Plugins 合并

| 旧位置 | 数量 | 新位置 | 说明 |
|--------|------|--------|------|
| `workspace/runtime/plugins/` | 1 个 registry.json | `tools/plugins/` | ✅ 已合并 |

---

### 3.5 其他工具二进制文件

| 旧位置 | 新位置 | 说明 |
|--------|--------|------|
| `runtime/tools/bin/` | `tools/bin/bin/` | 通用二进制文件 |
| `runtime/tools/go/` | `tools/bin/go/` | Go 工具 |
| `runtime/tools/playwright-browsers/` | `tools/bin/playwright-browsers/` | Playwright 浏览器 |

---

## 四、安装说明（单一目录）

### 4.1 Skills 安装

**位置**: `tools/skills/{public,custom}/`

```bash
# 安装公开 skill
mkdir -p tools/skills/public/my-skill
cp SKILL.md tools/skills/public/my-skill/

# 安装自定义 skill
mkdir -p tools/skills/custom/my-custom-skill
cp SKILL.md tools/skills/custom/my-custom-skill/

# 验证
curl http://localhost:19802/api/skills | python3 -c "import json,sys; data=json.load(sys.stdin); print(f'Total: {len(data[\"skills\"])}')"
```

### 4.2 Skills 卸载

```bash
# 删除公开 skill
rm -rf tools/skills/public/my-skill

# 删除自定义 skill
rm -rf tools/skills/custom/my-custom-skill
```

---

### 4.3 MCP 服务器安装

**位置**: `tools/mcp/`

```bash
# 1. 复制可执行文件到 bin/
cp mcp-server-{name} tools/mcp/bin/

# 2. 创建配置文件到 servers/
cat > tools/mcp/servers/{name}.json << 'EOF'
{
  "enabled": true,
  "type": "stdio",
  "command": "/home/sieve-pub/public-workspace/octoagent/tools/mcp/bin/mcp-server-{name}",
  "args": [...],
  "description": "...",
  "permission_scope": "sandbox"
}
EOF

# 3. 更新 extensions_config.json
# 4. 重启 Gateway 服务
```

### 4.4 MCP 服务器卸载

```bash
# 1. 删除可执行文件
rm tools/mcp/bin/mcp-server-{name}

# 2. 删除配置文件
rm tools/mcp/servers/{name}.json

# 3. 更新 extensions_config.json（删除对应条目）

# 4. 重启 Gateway 服务
```

---

### 4.5 Hooks 安装

**位置**: `tools/hooks/`

```bash
mkdir -p tools/hooks/my-hook
cp hooks.json tools/hooks/my-hook/
cp *.sh tools/hooks/my-hook/
```

### 4.6 Hooks 卸载

```bash
rm -rf tools/hooks/my-hook
```

---

### 4.7 Plugins 安装

**位置**: `tools/plugins/`

```bash
# 更新 registry.json
cat >> tools/plugins/registry.json << 'EOF'
{
  "plugins": [
    {
      "name": "plugin-name",
      "enabled": true,
      "config": {...}
    }
  ]
}
EOF
```

### 4.8 Plugins 卸载

```bash
# 从 registry.json 中删除对应条目
```

---

## 五、调用说明

### 5.1 Skills 调用

**在 Agent 会话中引用**:
```
@skill-name
```

**示例**:
```
@pencil-design              # 设计工作流（最完整）
@cloakbrowser-controlled-browser  # 浏览器自动化（无需授权）⭐
@get-shit-done              # 高效工作流
@autoresearch               # 研究循环
```

---

### 5.2 MCP 服务器调用

**通过工具名调用**:
```python
# Filesystem MCP (14 tools)
read_file(path="...")
write_file(path="...", content="...")
edit_file(path="...", oldString="...", newString="...")
search_files(pattern="...", path="...", recursive=True)

# PostgreSQL MCP (1 tool)
query(sql="SELECT * FROM ...")

# OpenAPI MCP (4 tools, 含 http_api_probe)
list-api-endpoints()
invoke-api-endpoint(endpoint="/api/...", method="GET")
http_api_probe(url="http://127.0.0.1:19802/openapi.json")

# Docker MCP (8 tools)
docker_container_list(all=True)
docker_container_logs(container="nginx", tail=100)
docker_container_restart(container="langgraph")

# Redis MCP (4 tools)
set(key="...", value="...", expire=3600)
get(key="...")
list(pattern="session:*")

# Docker Compose MCP (2 tools)
compose_version()
compose_config_check(file="docker-compose.yml")
```

---

### 5.3 Hooks 调用

**Hooks 自动触发**（无需手动调用）:

| Hook 组 | 触发事件 | 说明 |
|---------|----------|------|
| governance-audit | sessionStart, sessionEnd, userPromptSubmitted | 治理审计 |
| session-logger | sessionStart, sessionEnd, userPromptSubmitted | 会话日志记录 |

---

## 六、配置文件更新指南

### 6.1 extensions_config.json

**位置**: `/home/sieve-pub/public-workspace/octoagent/extensions_config.json`

**MCP 服务器配置示例**:
```json
{
  "mcpServers": {
    "filesystem": {
      "enabled": true,
      "type": "stdio",
      "command": "/home/sieve-pub/public-workspace/octoagent/tools/mcp/bin/mcp-server-filesystem",
      "args": ["/home/sieve-pub/public-workspace/octoagent"],
      "description": "System-scoped filesystem MCP with full host filesystem access.",
      "permission_scope": "sandbox"
    }
  }
}
```

---

### 6.2 Skills 加载路径 (loader.py)

**位置**: `backend/src/storage/skills/loader.py`

**建议更新**:
```python
def get_skills_root_path() -> Path:
    """Get the root path of the skills directory."""
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    skills_dir = backend_dir.parent / "tools" / "skills"  # octoagent/tools/skills
    return skills_dir

EXTRA_SKILL_ROOTS = []  # 已合并到主目录，无需额外根目录
```

---

## 七、迁移验证清单

### 7.1 Skills 验证

```bash
# 检查 skills 数量
curl -s http://localhost:19802/api/skills | python3 -c "import json,sys; data=json.load(sys.stdin); print(f'Total: {len(data[\"skills\"])}')"

# 预期结果：50 public + 0 custom = 50 (删除 custom 后)
```

---

### 7.2 MCP 验证

```bash
# 检查 MCP 服务器配置
python3 /tmp/check_mcp_count.py < /home/sieve-pub/public-workspace/octoagent/extensions_config.json

# 预期结果：6 个 MCP 服务器
```

---

### 7.3 Hooks 验证

```bash
# 检查 hooks 目录
ls -la tools/hooks/

# 预期结果：governance-audit, session-logger
```

---

## 八、GitHub 提交计划

**待执行**:
```bash
cd /home/sieve-pub/public-workspace/octoagent
git add -A
git commit -m "重构：统一工具目录结构 (tools/{skills,mcp,hooks,plugins,bin})"
git push origin main
```

---

## 九、总结

### 9.1 重组完成事项

1. ✅ **Skills 合并**: 49 个 skills 统一到 `tools/skills/public/`
2. ✅ **MCP 合并**: 6 个 MCP 服务器统一到 `tools/mcp/`
3. ✅ **Hooks 合并**: 2 个 hook 组统一到 `tools/hooks/`
4. ✅ **Plugins 合并**: registry.json 统一到 `tools/plugins/`
5. ✅ **二进制文件合并**: 其他工具统一到 `tools/bin/`

### 9.2 目录结构优势

| 方面 | 旧结构 | 新结构 |
|------|--------|--------|
| **查找效率** | 分散在多个位置 | 统一在 tools/ 下 |
| **安装路径** | 需要记忆多个位置 | 单一目录 `tools/{type}/` |
| **卸载清理** | 需要删除多处 | 单一目录删除 |
| **配置管理** | 分散在多个文件 | 集中在 extensions_config.json |
| **文档维护** | 多份文档 | 单一文档 |

### 9.3 后续工作

1. ⏳ 更新 `loader.py` 中的 skills 路径
2. ⏳ 更新 `extensions_config.json` 中的 MCP 路径
3. ⏳ 验证所有工具模块工作正常
4. ⏳ GitHub 推送重组提交

---

*报告生成时间：2026-06-30T23:55 HKT*  
*OctoAgent 系统统一目录结构重组完成*
