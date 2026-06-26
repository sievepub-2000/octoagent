# OctoAgent 系统评估分析报告

日期: 2026-06-27
评估范围: 全系统代码审计 + 针对性修复

---

## 一、系统架构总览

OctoAgent 是一个基于 LangGraph + FastAPI 的多智能体 AI 平台。

| 组件 | 技术栈 | 规模 |
|------|--------|------|
| Gateway API | FastAPI, 4 uvicorn workers | 60+ routers |
| Agent Runtime | LangGraph, LangChain | 24 middlewares, 3 agent types |
| Frontend | Next.js 16.2.3 | 多页面 SPA |
| Memory | PostgreSQL + JSON file | layered_v1 contract |
| Tool System | registry-based, MCP + builtins | 110 builtins, 7 MCP, 53 skills |
| Search | Bing/DDG/Jina multi-backend | ~1000 lines web_search tool |

---

## 二、发现的系统性问题（按严重程度排序）

### P0: 协议文本泄露到用户输出

**症状**: Agent 将内部 research protocol（"闭合"、"软约束"、"搜索后端不可用"等系统术语）直接输出给用户。

**根因**:
1. `web_search` 工具在搜索失败时返回详细的后端错误状态（`Search backend unavailable right now; returning fallback public sources for manual verification. Tried backends: bing_rss:..., bing_html:...`）
2. Agent 没有区分"工具返回的错误信息"和"应该呈现给用户的答案"
3. System prompt 大量篇幅教 agent "如何做研究"（搜索策略、多后端回退、证据收集），但没有强调"什么时候隐藏内部细节"

**与 opencode 的对比**:
- opencode 的 web_search 工具返回简洁结果 + 错误时返回简短消息 "No results found"
- opencode 的 system prompt 没有 research methodology 内容

**修复**: 精简 web_search 错误消息 + prompt 添加"永远不要输出系统内部协议"指令

### P0: 系统提示词膨胀（42KB → 21KB）

**症状**: System prompt 模板 42,113 chars / 808 行，远超合理范围。

**问题**:
- `<subagent_system>`: 6962 chars — 包含 5 个完整示例（"Why is Tencent's stock declining"、"Compare 5 cloud providers"等）
- `<clarification_system>`: 3749 chars — 每个澄清场景都带完整示例
- `<default_prompt_standard>`: 4153 chars — 重复 opencode 的所有 prompt engineering 指南

**影响**:
- 模型将大量 tokens 消耗在处理元指令而非实际任务
- 长 prompt 稀释关键指令的权重
- 模型在长 prompt 中更可能复制 system 输出风格（protocol leak）

**与 opencode 的对比**:
- opencode 的 system prompt 极为精简（< 2000 chars），只包含角色定义、核心规则、输出格式
- 示例通过外部 skill/agent 配置文件提供，不嵌入 prompt

**修复**: 精简各章节至核心规则（49% 压缩）

### P1: 复合意图路由失败

**症状**: "介绍一下你自己。帮我查一下天气" — Agent 只执行了天气查询，跳过了自我介绍。

**根因**: `execution.py` 中的 `select_execution_target` 和 `is_conversation_request` 将消息路由到**单一** runtime target。

**与 opencode 的对比**:
- opencode 没有预路由层 — 消息直接给 LLM，LLM 自主决定工具调用顺序
- octoagent 的预路由层（query engine → browser_runtime/research_runtime/repo_read）增加了复杂的分类逻辑，但多意图场景分类失败

**修复**: 在 `execution.py` 中添加复合请求检测逻辑

### P1: 工具调用结果到最终回复的链路断裂

**症状**: Agent 调用了 weather API（fetch 了 JSON 数据），然后调用了 web_search（得到了搜索结果），但最终输出没有呈现任何具体天气数据。

**根因**:
1. 工具调用结果存储在 LangGraph message 列表中
2. 但最终回复生成时，模型没有从工具结果中提取数据形成答案
3. 而是输出了"我搜索了 X, Y, Z 来源，但遇到了限制"

**与 opencode 的对比**:
- opencode 的 agent 循环强制要求：要么交付答案，要么说明阻塞原因
- octoagent 的 termination classifier 只判断"是否还有 tool_calls"，不判断"是否交付了答案"

**修复**: Prompt 添加"After thinking, deliver the actual answer"和"Never output search/methodology metadata"指令

### P1: Prompt 中混合中英文

**症状**: Agent 回复中英混杂（中文回答 + 英文 protocol 术语）。

**根因**: System prompt 97% 为英文，虽然有 `<language_preference>` 标签，但优先级别不够高。

**修复**: Prompt 中保留 language_preference 指令并简化其他内容以降低干扰

### P2: Web 搜索工具过于复杂

**症状**: `openharness_compat_tools.py` 为 50KB，包含 4 种搜索后端、领域约束评分、避风港逻辑、种子结果、新闻检测、基金查询标记等。

**问题**: 50KB 的工具代码增加了导入时间和内存占用；大量边缘逻辑（基金查询、AI 新闻源、避风港链接）对普通 weather/search 请求完全无用。

**修复**: 精简了错误消息（协议文本去掉），工具本身保留但等待未来重构分割

---

## 三、本次修复总结

| 文件 | 修改内容 | 影响 |
|------|----------|------|
| `prompt.py` | 6 个章节精简 (42KB→21KB, -49%) | 减少元指令干扰，添加 output-first 规则 |
| `openharness_compat_tools.py` | 6 处错误消息精简 | 去掉协议文本泄露源 |
| `execution.py` | 复合请求检测 + 路由改进 | 多意图消息正确处理 |

## 四、推荐后续工作（本轮未处理）

1. **分解 50KB web_search 工具** — 拆分为独立的 search / fetch / scrape 模块
2. **移除 query engine 预路由层** — 直接给 LLM 处理所有消息（减少一层复杂的分类逻辑）
3. **添加 10 秒超时后的 fallback 答案** — 避免模型无限思考
4. **引入迭代验证** — 每次 tool call 后验证"是否需要交付答案"
5. **PostgreSQL 持久化改造** — 当前使用内存字典存储 sessions
6. **统一错误处理** — 所有 tool 返回必须包含 answer_delivered 标记
