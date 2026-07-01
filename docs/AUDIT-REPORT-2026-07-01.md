# OctoAgent 全量代码评估分析报告

**审计日期**: 2026-07-01  
**版本**: 2026.7.1  
**审计范围**: backend/src/ (470 Python files), scripts/, runtime/config/

---

## 一、执行摘要

| 类别 | 发现数 | 优先级 |
|------|--------|--------|
| **关键问题 (Critical)** | 2 | P0 - 立即修复 |
| **高风险 (High)** | 3 | P1 - 本周内修复 |
| **中风险 (Medium)** | 8 | P2 - 本月内修复 |
| **低风险/风格 (Low)** | 46 | P3 - 持续改进 |
| **总计** | 59 | - |

---

## 二、关键问题 (P0 - 立即修复)

### 2.1 中间件钩子缺少异常保护

**文件**: `backend/src/agents/middlewares/critic_middleware.py:17`  
**问题**: `after_model()` 方法没有 try/except 保护

```python
# 当前代码 (第 17 行)
def after_model(self, state, runtime: Runtime):
    # 直接执行，无异常处理
```

**风险**: 
- 如果 critic 逻辑抛出未捕获异常，会导致整个 agent run 失败
- LangGraph middleware 契约要求钩子方法必须防御性编程

**修复建议**:
```python
def after_model(self, state, runtime: Runtime):
    try:
        # existing logic
    except Exception as e:
        logger.warning("CriticMiddleware.after_model failed: %s", e)
        return None  # Never block the main response
```

---

### 2.2 GoalMiddleware 使用同步 LLM 调用

**文件**: `backend/src/agents/middlewares/goal_middleware.py:79`  
**问题**: 使用 `.invoke()` (同步) 而非 `.ainvoke()` (异步)

```python
# 第 79 行
resp = model.invoke(prompt)  # 阻塞式调用
```

**风险**:
- 阻塞 LangGraph worker 线程，降低并发吞吐
- 在 `--n-jobs-per-worker 2` 配置下影响更显著

**修复建议**:
```python
# 改为异步调用
resp = await model.ainvoke(prompt)
```

---

## 三、高风险问题 (P1 - 本周内修复)

### 3.1 MemoryMiddleware 缺少显式大小限制

**文件**: `backend/src/agents/middlewares/memory_middleware.py`  
**问题**: 没有对 conversation_summary 写入设置上限

**现状**:
- DuckDB RAG store: 235.8 MB, 101 entries (去重后)
- 每次 agent run 都会调用 `_store_simplemem_conversation_async()`
- 无上限控制，理论上可无限增长

**风险**:
- 长期运行后 memory store 膨胀
- RAG 检索性能下降 (更多噪声)
- DuckDB 文件体积持续增长

**修复建议**:
```python
# 在 MemoryMiddleware.after_agent 中添加
MAX_CONVERSATION_SUMMARY_ENTRIES = 500  # env var: OCTO_MAX_CS_ENTRIES

def after_agent(self, state, runtime):
    # ... existing logic ...
    
    # Check store size before writing
    if self._get_store_count() > MAX_CONVERSATION_SUMMARY_ENTRIES:
        logger.info("conversation_summary limit reached, skipping write")
        return {"runtime": runtime_state}
```

---

### 3.2 Shell Scripts 缺少错误陷阱

**影响文件**: 15 个 scripts/*.sh  
**问题**: `set -e` 但没有 trap 处理

**示例**: `scripts/derive_insights_cron.sh`, `scripts/workspace_cleanup.sh`

**风险**:
- 脚本中途失败时不会清理临时文件
- 不会记录失败状态到日志
- cron 任务可能静默失败

**修复建议**:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Add error trap
trap 'echo "ERROR: $0 failed at line $LINENO" >> "$LOG_FILE"; exit 1' ERR

# ... existing script ...
```

---

### 3.3 File Handle 潜在泄漏

**文件**: `backend/src/tools/builtins/publishing_workflow_tools.py:504`  
**问题**: 没有使用 context manager

```python
text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
# 如果 read() 抛出异常，file handle 不会关闭
```

**修复建议**:
```python
with open(sys.argv[1], encoding='utf-8', errors='replace') as f:
    text = f.read()
```

---

## 四、中风险问题 (P2 - 本月内修复)

### 4.1 33 处 print() 语句在 production code

**分布**:
- `interfaces/embedded/client.py`: 6 处 (调试代码未清理)
- `middlewares/`: 8 处 (title, memory, clarification, view_image)
- `gateway/channel_sdk/client.py`: 1 处
- `storage/skills/`: 2 处
- 其他: 16 处

**建议**: 替换为 `logger.info()` / `logger.debug()`

---

### 4.2 5 个未分配的 TODO/FIXME

**文件**:
1. `backend/src/storage/brain/goal_contract.py:5` - GoalDriftMiddleware TODO
2. `backend/src/tools/builtins/openharness_compat_tools.py:1057-1073` - todo_write_tool 实现

**建议**: 分配 owner 或标记为 deprecated

---

### 4.3 Database Connections 缺少 Connection Pooling

**影响文件**: 17 个  
**示例**: `lifecycle.py`, `app.py`, `vector_store.py`, `checkpointer_config.py`

**现状**: 每次操作都创建新连接  
**建议**: 使用 SQLAlchemy pool 或 asyncpg pool

---

### 4.4 Hardcoded Paths in Scripts

**文件**: 
- `scripts/derive_insights_cron.sh`
- `scripts/workspace_cleanup.sh`

**问题**: `/home/sieve-pub/public-workspace/octoagent` 硬编码

**建议**: 使用 `$REPO_ROOT` env var (已在 start-daemon.sh 中定义)

---

## 五、低风险/风格问题 (P3 - 持续改进)

### 5.1 Caching Patterns

**现状**: 6 个文件使用缓存
- `title_middleware.py`: `_TITLE_CACHE` (本次优化新增 ✓)
- `lesson_injection_middleware.py`: `_lesson_cache` (本次优化新增 ✓)
- `skill_evolution_middleware.py`: `_planning_cache` (本次优化新增 ✓)

**建议**: 考虑使用 `functools.lru_cache` 或 `cachetools` 统一管理

---

### 5.2 .env Files

**发现**: `.env.docker.example` 在仓库中  
**状态**: 已 gitignore，无风险

---

## 六、性能基准 (优化后)

| 指标 | 数值 | 备注 |
|------|------|------|
| Python files | 470 | - |
| DuckDB RAG store | 235.8 MB | 去重后 101 entries |
| Middlewares | 27 个 | 3 个已优化缓存 |
| Sync LLM calls | 1 处 | goal_middleware.py (待修复) |
| Unprotected hooks | 1 处 | critic_middleware.py (待修复) |

---

## 七、修复优先级矩阵

```
立即 (P0)          本周 (P1)           本月 (P2)           持续 (P3)
─────────────      ─────────────       ─────────────       ─────────────
• critic_mw        • goal_mw sync      • memory size limit  • print→logger
  hook protection   LLM call            • shell error trap   • TODO assignment
                                  • file handle leak    • connection pool
                                  • hardcoded paths     • caching standard
```

---

## 八、正面发现 (Good Practices)

✓ **MemoryMiddleware** 使用 async writes (`_store_simplemem_conversation_async`)  
✓ **本次优化新增** 3 个 middleware 的线程级缓存  
✓ **P4 完成** conversation_summary 去重 (457→81 entries, -82%)  
✓ **配置管理** API keys 使用 env vars，无硬编码密钥  
✓ **错误日志** llama-server/gateway/logs 无明显错误  

---

## 九、建议的下一步行动

### 立即执行 (今天)
1. 修复 `critic_middleware.py` 添加 try/except
2. 修复 `goal_middleware.py` 改为 async invoke

### 本周执行
3. 为 15 个 shell scripts 添加 error trap
4. 修复 `publishing_workflow_tools.py` file handle
5. 为 MemoryMiddleware 添加 size limit

### 本月执行
6. 替换 33 处 print() 为 logger
7. 实现 database connection pooling
8. 清理 hardcoded paths in scripts

---

**报告生成**: 2026-07-01T15:30:00Z  
**审计工具**: 自定义 Python 静态分析 + 人工审查  
**下次审计建议**: 2026-07-15 (双周)
