# OctoAgent Tools 统一目录结构说明

**版本**: v1.0  
**更新日期**: 2026-06-30  
**维护者**: OctoAgent Team

---

## 一、统一目录结构

```
tools/                          # 所有工具模块的统一根目录
├── skills/                     # Skills 技能库（合并所有来源）
│   ├── public/                 # 公开 skills (49 个)
│   │   ├── agent-rules-books/
│   │   ├── autoresearch/
│   │   ├── beautiful-html-templates/
│   │   ├── cloakbrowser-controlled-browser/ ⭐ (默认浏览器工具)
│   │   ├── fireworks-tech-graph/
│   │   ├── get-shit-done/
│   │   ├── goalbuddy/
│   │   ├── ian-handdrawn-ppt/
│   │   ├── lightseek-smg-gateway/
│   │   ├── mirage-vfs/
│   │   ├── peekaboo-vision-mcp/
│   │   ├── pencil-design/ ⭐⭐⭐ (最完整)
│   │   ├── photo-agents/
│   │   ├── spec-kit/
│   │   ├── tokenspeed-benchmark/
│   │   ├── voltagent-best-practices/
│   │   └── witr-runtime-diagnosis/
│   │   └── ... (共 49 个)
│   └── custom/                 # 自定义 skills (已清空)
├── mcp/                        # MCP 服务器配置
│   ├── servers/                # MCP 服务器配置文件
│   │   ├── filesystem.json
│   │   ├── postgres.json
│   │   ├── openapi.json
│   │   ├── docker-compose.json
│   │   ├── redis.json
│   │   └── docker.json
│   └── bin/                    # MCP 服务器可执行文件
│       ├── mcp-server-filesystem
│       ├── mcp-server-postgres
│       ├── openapi-mcp-server
│       ├── mcp-server-redis
│       └── docker-mcp
├── hooks/                      # Hooks 插件（合并所有来源）
│   ├── governance-audit/       # 治理审计 hook
│   │   ├── hooks.json
│   │   ├── audit-session-start.sh
│   │   ├── audit-prompt.sh
│   │   └── audit-session-end.sh
│   └── session-logger/         # 会话日志 hook
│       ├── hooks.json
│       ├── log-session-start.sh
│       ├── log-prompt.sh
│       └── log-session-end.sh
├── plugins/                    # Plugins（合并所有来源）
│   └── registry.json           # 插件注册表
└── bin/                        # 其他工具二进制文件
    ├── bin/                    # 通用二进制文件
    ├── go/                     # Go 工具
    └── playwright-browsers/    # Playwright 浏览器
```

---

## 二、安装说明

### 2.1 Skills 安装

**位置**: `tools/skills/{public,custom}/`

**安装新 skill**:
```bash
# 公开 skill
mkdir -p tools/skills/public/my-skill
cp SKILL.md tools/skills/public/my-skill/

# 自定义 skill
mkdir -p tools/skills/custom/my-custom-skill
cp SKILL.md tools/skills/custom/my-custom-skill/
```

**卸载 skill**:
```bash
# 删除 skill 目录
rm -rf tools/skills/public/my-skill
rm -rf tools/skills/custom/my-custom-skill
```

**验证安装**:
```bash
curl http://localhost:19802/api/skills | python3 -c "import json,sys; data=json.load(sys.stdin); print(f'Total: {len(data[\"skills\"])}')"
```

---

### 2.2 MCP 服务器安装

**位置**: `tools/mcp/`

**安装新 MCP 服务器**:
1. 复制可执行文件到 `tools/mcp/bin/`
2. 创建配置文件到 `tools/mcp/servers/{name}.json`
3. 更新 `extensions_config.json`

**示例配置** (`tools/mcp/servers/filesystem.json`):
```json
{
  "enabled": true,
  "type": "stdio",
  "command": "/home/sieve-pub/public-workspace/octoagent/tools/mcp/bin/mcp-server-filesystem",
  "args": ["/home/sieve-pub/public-workspace/octoagent"],
  "description": "System-scoped filesystem MCP with full host filesystem access.",
  "permission_scope": "sandbox"
}
```

**卸载 MCP 服务器**:
```bash
# 删除可执行文件
rm tools/mcp/bin/mcp-server-{name}

# 删除配置文件
rm tools/mcp/servers/{name}.json

# 更新 extensions_config.json（删除对应条目）
```

---

### 2.3 Hooks 安装

**位置**: `tools/hooks/`

**安装新 hook**:
```bash
mkdir -p tools/hooks/my-hook
cp hooks.json tools/hooks/my-hook/
cp *.sh tools/hooks/my-hook/
```

**卸载 hook**:
```bash
rm -rf tools/hooks/my-hook
```

---

### 2.4 Plugins 安装

**位置**: `tools/plugins/`

**安装新 plugin**:
1. 更新 `tools/plugins/registry.json`
2. 添加插件配置条目

**卸载 plugin**:
1. 从 `tools/plugins/registry.json` 中删除对应条目

---

## 三、调用说明

### 3.1 Skills 调用

**在 Agent 会话中引用 skill**:
```
@skill-name
```

**示例**:
```
@pencil-design        # 激活设计工作流
@cloakbrowser-controlled-browser  # 使用浏览器自动化（无需授权）
@get-shit-done        # 激活高效工作流
```

**Skills 分类**:
- **public**: 公开 skills，系统默认加载
- **custom**: 自定义 skills，需要明确启用

---

### 3.2 MCP 服务器调用

**通过工具名调用**:
```python
# Filesystem MCP
read_file(path="...")
write_file(path="...", content="...")

# PostgreSQL MCP
query(sql="SELECT * FROM ...")

# OpenAPI MCP
list-api-endpoints()
invoke-api-endpoint(endpoint="/api/...", method="GET")

# Docker MCP
docker_container_list(all=True)
docker_container_logs(container="nginx", tail=100)

# Redis MCP
set(key="...", value="...")
get(key="...")
```

**MCP 服务器列表** (6 个):
| MCP 名称 | 工具数 | 用途 |
|----------|--------|------|
| filesystem | 14 | 文件操作 |
| postgres | 1 | SQL 查询 |
| openapi | 4 | API 端点 + 健康检查 |
| docker-compose | 2 | Compose 配置验证 |
| redis | 4 | Redis 缓存操作 |
| docker | 8 | Docker 容器管理 |

---

### 3.3 Hooks 调用

**Hooks 自动触发**（无需手动调用）:

| Hook 组 | 触发事件 | 说明 |
|---------|----------|------|
| governance-audit | sessionStart, sessionEnd, userPromptSubmitted | 治理审计 |
| session-logger | sessionStart, sessionEnd, userPromptSubmitted | 会话日志记录 |

---

### 3.4 Plugins 调用

**Plugins 通过 registry.json 注册**:
```json
{
  "plugins": [
    {
      "name": "plugin-name",
      "enabled": true,
      "config": {...}
    }
  ]
}
```

---

## 四、配置更新指南

### 4.1 extensions_config.json

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

### 4.2 Skills 加载路径

**代码位置**: `backend/src/storage/skills/loader.py`

**当前配置**:
```python
def get_skills_root_path() -> Path:
    """Get the root path of the skills directory."""
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    skills_dir = backend_dir.parent / "skills"  # octoagent/skills
    return skills_dir

EXTRA_SKILL_ROOTS = [
    (repo_root / ".agents" / "skills", "public"),
    (repo_root / "project_docs" / "skills" / "public", "public"),
]
```

**建议更新为**:
```python
def get_skills_root_path() -> Path:
    """Get the root path of the skills directory."""
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    skills_dir = backend_dir.parent / "tools" / "skills"  # octoagent/tools/skills
    return skills_dir

EXTRA_SKILL_ROOTS = []  # 已合并到主目录
```

---

## 五、迁移指南

### 5.1 从旧结构迁移到新结构

**旧结构**:
```
octoagent/
├── skills/                    # 主 skills 目录
├── .agents/skills/            # 额外 skills 目录
├── project_docs/skills/       # 项目文档 skills
├── runtime/tools/mcp/         # MCP 服务器
├── .github/hooks/             # Hooks
└── workspace/runtime/plugins/ # Plugins
```

**新结构**:
```
octoagent/
└── tools/                     # 统一工具目录
    ├── skills/                # 合并所有 skills
    ├── mcp/                   # MCP 服务器配置和二进制
    ├── hooks/                 # Hooks 插件
    └── plugins/               # Plugins
```

---

### 5.2 迁移步骤

1. **创建新目录结构**:
   ```bash
   mkdir -p tools/{skills/{public,custom},mcp/{servers,bin},hooks,plugins,bin}
   ```

2. **复制 skills**:
   ```bash
   cp -r skills/public/* tools/skills/public/
   cp -r .agents/skills/* tools/skills/public/
   ```

3. **复制 MCP 文件**:
   ```bash
   cp -r runtime/tools/mcp/* tools/mcp/bin/
   ```

4. **复制 hooks**:
   ```bash
   cp -r .github/hooks/* tools/hooks/
   ```

5. **复制 plugins**:
   ```bash
   cp workspace/runtime/plugins/registry.json tools/plugins/
   ```

6. **更新配置文件**:
   - 更新 `extensions_config.json` 中的 MCP 路径
   - 更新 `loader.py` 中的 skills 路径

7. **验证**:
   ```bash
   curl http://localhost:19802/api/skills
   python3 /tmp/check_mcp_smoke.py
   ```

---

## 六、注意事项

### 6.1 权限问题

某些目录（如 `playwright-browsers/chromium_headless_shell-1217/chrome-linux/locales`）可能有权限限制，复制时使用：
```bash
cp -r --no-preserve=ownership,mode ...
```

### 6.2 缓存刷新

Skills API 有 1 小时缓存 TTL，修改后需要：
- 调用 `invalidate_skills_cache()` API
- 或等待自动刷新
- 或重启 Gateway 服务

### 6.3 向后兼容

在完全迁移前，建议保留旧目录作为备份：
```bash
mv skills skills.backup
mv .agents/skills .agents/skills.backup
```

---

## 七、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-06-30 | 初始统一目录结构 |

---

*文档维护：OctoAgent Team*  
*最后更新：2026-06-30T23:45 HKT*
