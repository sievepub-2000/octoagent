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

export const aboutMarkdown = `**Project License**

- Default open-source terms: **Server Side Public License v1 (SSPL v1)**.
- Commercial alternatives also available: **closed-source / SaaS / embedded / OEM licenses** (contact for terms).
- This project includes original code excerpts from **Bytedance Ltd.**, redistributed under the **MIT License**; see \`NOTICE.md\` at the repository root for the full notice.
- Full terms in \`LICENSE\` and \`NOTICE.md\` at the repository root.

**Contact: ${CONTACT_EMAIL}**

=====

**OctoAgent** is a powerful white-box AI tool for office, business, and system operations: every reasoning step, every tool call, and every artifact is traceable, auditable, and replayable — a sharp contrast to black-box agents such as OpenClaw.

**Core Capabilities**

- Business intelligence and multi-dimensional analysis (industry, competitors, sentiment, ToB/ToC research)
- Academic research reports with trustworthy citation aggregation
- Fully automated office document processing (Excel / Word / PPT / PDF / Markdown conversion, review, rewriting)
- System-level operations and IT runbooks (one-click health checks, configuration audits, log search, security scans)
- Database interaction and code generation / refactoring / debugging
- Multi-agent task orchestration with every intermediate step visible to the user

**White-box Commitment**

- Every tool call and its arguments are fully transparent
- Every step can be paused, cancelled, or edited
- Built-in audit logs, observability dashboards, and replay
- Local-first: models, retrieval, code sandbox, and file system can all be deployed locally

**Typical Scenarios**

Office automation · Business due diligence · Data analysis reports · Academic literature reviews · System operations · Security audits · Code collaboration · Private deployment

---

**License.** OctoAgent is dual-licensed under SSPL v1 + commercial. For
managed-service, OEM, embedded, or brand-removal use cases please
contact **${CONTACT_EMAIL}** — see [\`LICENSE\`](https://github.com/sievepub-2000/octoagent/blob/main/LICENSE).
`;
