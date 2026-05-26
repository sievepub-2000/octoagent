"use client";

// =========================================================================
// HARDCODED CONTACT EMAIL — DO NOT EDIT WITHOUT RESEALING THE BACKEND
// INTEGRITY FINGERPRINT AT backend/src/governance/about.py
// (see scripts/dev_tools/refresh_about_fingerprint.py)
// =========================================================================
// The contact email must appear verbatim at the top of the About panel.
// The CI workflow license-check.yml grep-asserts both the email constant
// here and the panel registration in settings-dialog.tsx. Removing,
// translating, or hiding this line is a license violation under the
// Anti-Bypassing addendum of LICENSE.

export const CONTACT_EMAIL = "zillafan80@gmail.com";

export const aboutMarkdown = `**本项目授权协议**

- 默认开源条款：**Server Side Public License v1 (SSPL v1)**。
- 同时提供 **闭源 / SaaS / 嵌入 / OEM 等商业许可备选**（来函议定）。
- 项目包含来自 **Bytedance Ltd.** 的原始代码片段，继续以 **MIT 许可** 分发；完整声明见仓库根目录 \`NOTICE.md\`。
- 完整条款详见仓库根目录 \`LICENSE\` 与 \`NOTICE.md\`。

**联系作者：${CONTACT_EMAIL}**

=====

**OctoAgent** 是一款面向办公商务与系统操作的强大白盒化（white-box）AI 工具：每一步推理、每一次工具调用、每一份产出都可追溯、可审计、可回放——与 OpenClaw 之类的黑盒代理形成鲜明对比。

**核心能力**

- 商业数据抓取与多维度分析（行业、竞品、舆情、ToB/ToC 调研）
- 学术研究报告生成与可信引用聚合
- 全自动办公文档处理（Excel / Word / PPT / PDF / Markdown 互转、批改、改写）
- 系统级操作与 IT 运维剧本（一键巡检、配置审计、日志检索、安全扫描）
- 数据库交互与代码生成 / 重构 / 调试
- 多 Agent 协同的任务编排，所有中间步骤对用户可见

**白盒化承诺**

- 所有工具调用与参数完全透明展示
- 每一步可暂停、可取消、可改写
- 内置审计日志、可观测性面板与回放
- 全本地优先：模型、检索、代码沙箱、文件系统均可本地化部署

**典型应用场景**

办公自动化 · 商务尽调 · 数据分析报告 · 学术综述 · 系统运维 · 安全审计 · 代码协作 · 私有部署

---

**License.** OctoAgent is dual-licensed under SSPL v1 + commercial. For
managed-service, OEM, embedded, or brand-removal use cases please
contact **${CONTACT_EMAIL}** — see [\`LICENSE\`](https://github.com/sievepub-2000/octoagent/blob/main/LICENSE).
`;
