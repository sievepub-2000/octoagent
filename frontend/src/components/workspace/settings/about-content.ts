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

import type { Locale } from "@/core/i18n";

export const CONTACT_EMAIL = "zillafan80@gmail.com";

const aboutMarkdownEnUS = `**Project License**

- Default open-source terms: **Server Side Public License v1 (SSPL v1)**.
- Commercial alternatives also available: **closed-source / SaaS / embedded / OEM licenses** (contact for terms).
- This project includes original code excerpts from **Bytedance Ltd.**, redistributed under the **MIT License**; see \`NOTICE.md\` at the repository root for the full notice.
- Full terms in \`LICENSE\` and \`NOTICE.md\` at the repository root.

**Author Contact: ${CONTACT_EMAIL}**

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

const aboutMarkdownZhCN = `**项目许可证**

- 默认开源条款：**Server Side Public License v1（SSPL v1）**。
- 同时提供商业授权：**闭源 / SaaS / 嵌入式 / OEM 授权**（具体条款请联系作者）。
- 本项目包含来自 **字节跳动有限公司（Bytedance Ltd.）** 的原始代码片段，按 **MIT 许可证** 再分发；完整声明见仓库根目录的 \`NOTICE.md\`。
- 完整条款见仓库根目录的 \`LICENSE\` 与 \`NOTICE.md\`。

**作者联系方式：${CONTACT_EMAIL}**

=====

**OctoAgent** 是一款强大的白盒 AI 工具，面向办公、商业与系统运维：每一步推理、每一次工具调用、每一个产物都可追溯、可审计、可回放——与 OpenClaw 等黑盒智能体形成鲜明对比。

**核心能力**

- 商业情报与多维度分析（行业、竞品、舆情、ToB/ToC 调研）
- 学术研究报告，附带可信引用聚合
- 全自动办公文档处理（Excel / Word / PPT / PDF / Markdown 转换、审阅、改写）
- 系统级运维与 IT 运行手册（一键健康检查、配置审计、日志检索、安全扫描）
- 数据库交互与代码生成 / 重构 / 调试
- 多智能体任务编排，所有中间步骤对用户可见

**白盒承诺**

- 每一次工具调用及其参数完全透明
- 每一步都可暂停、取消或编辑
- 内置审计日志、可观测性看板与回放
- 本地优先：模型、检索、代码沙箱与文件系统均可本地部署

**典型场景**

办公自动化 · 商业尽调 · 数据分析报告 · 学术文献综述 · 系统运维 · 安全审计 · 代码协作 · 私有化部署

---

**许可。** OctoAgent 采用 SSPL v1 + 商业授权双许可。如需托管服务、OEM、嵌入式或去品牌等用途，请联系 **${CONTACT_EMAIL}**——详见 [\`LICENSE\`](https://github.com/sievepub-2000/octoagent/blob/main/LICENSE)。
`;

const aboutMarkdownZhTW = `**專案授權**

- 預設開源條款：**Server Side Public License v1（SSPL v1）**。
- 同時提供商業授權：**閉源 / SaaS / 嵌入式 / OEM 授權**（具體條款請聯絡作者）。
- 本專案包含來自 **字節跳動有限公司（Bytedance Ltd.）** 的原始程式碼片段，依 **MIT 授權** 再散布；完整聲明見儲存庫根目錄的 \`NOTICE.md\`。
- 完整條款見儲存庫根目錄的 \`LICENSE\` 與 \`NOTICE.md\`。

**作者聯絡方式：${CONTACT_EMAIL}**

=====

**OctoAgent** 是一款強大的白盒 AI 工具，面向辦公、商業與系統維運：每一步推理、每一次工具呼叫、每一個產物皆可追溯、可稽核、可重播——與 OpenClaw 等黑盒智能體形成鮮明對比。

**核心能力**

- 商業情報與多維度分析（產業、競品、輿情、ToB/ToC 研究）
- 學術研究報告，附帶可信引用彙整
- 全自動辦公文件處理（Excel / Word / PPT / PDF / Markdown 轉換、審閱、改寫）
- 系統級維運與 IT 操作手冊（一鍵健康檢查、組態稽核、日誌檢索、安全掃描）
- 資料庫互動與程式碼生成 / 重構 / 除錯
- 多智能體任務編排，所有中間步驟對使用者可見

**白盒承諾**

- 每一次工具呼叫及其參數完全透明
- 每一步皆可暫停、取消或編輯
- 內建稽核日誌、可觀測性儀表板與重播
- 在地優先：模型、檢索、程式碼沙箱與檔案系統皆可在地部署

**典型場景**

辦公自動化 · 商業盡職調查 · 資料分析報告 · 學術文獻綜述 · 系統維運 · 安全稽核 · 程式碼協作 · 私有化部署

---

**授權。** OctoAgent 採用 SSPL v1 + 商業授權雙授權。如需託管服務、OEM、嵌入式或去品牌等用途，請聯絡 **${CONTACT_EMAIL}**——詳見 [\`LICENSE\`](https://github.com/sievepub-2000/octoagent/blob/main/LICENSE)。
`;

const aboutMarkdownJa = `**プロジェクトライセンス**

- 既定のオープンソース条項：**Server Side Public License v1（SSPL v1）**。
- 商用ライセンスも提供：**クローズドソース / SaaS / 組み込み / OEM ライセンス**（条件はお問い合わせください）。
- 本プロジェクトには **Bytedance Ltd.** のオリジナルコード抜粋が含まれ、**MIT ライセンス** で再配布しています。全文はリポジトリ直下の \`NOTICE.md\` を参照してください。
- 完全な条項はリポジトリ直下の \`LICENSE\` と \`NOTICE.md\` にあります。

**作者連絡先：${CONTACT_EMAIL}**

=====

**OctoAgent** は、オフィス・ビジネス・システム運用のための強力なホワイトボックス AI ツールです。すべての推論ステップ、すべてのツール呼び出し、すべての成果物が追跡・監査・再生可能であり、OpenClaw のようなブラックボックス型エージェントとは一線を画します。

**主な機能**

- ビジネスインテリジェンスと多次元分析（業界・競合・センチメント・ToB/ToC 調査）
- 信頼できる引用集約を備えた学術調査レポート
- 完全自動のオフィス文書処理（Excel / Word / PPT / PDF / Markdown の変換・レビュー・書き換え）
- システムレベルの運用と IT ランブック（ワンクリック・ヘルスチェック、構成監査、ログ検索、セキュリティスキャン）
- データベース操作とコード生成 / リファクタリング / デバッグ
- すべての中間ステップがユーザーに見えるマルチエージェントのタスクオーケストレーション

**ホワイトボックスの約束**

- すべてのツール呼び出しと引数が完全に透明
- すべてのステップを一時停止・キャンセル・編集可能
- 監査ログ、可観測性ダッシュボード、リプレイを内蔵
- ローカルファースト：モデル・検索・コードサンドボックス・ファイルシステムをすべてローカルに配置可能

**典型的なシナリオ**

オフィス自動化 · ビジネスデューデリジェンス · データ分析レポート · 学術文献レビュー · システム運用 · セキュリティ監査 · コード協業 · プライベート配備

---

**ライセンス。** OctoAgent は SSPL v1 + 商用のデュアルライセンスです。マネージドサービス、OEM、組み込み、ブランド除去などの用途については **${CONTACT_EMAIL}** までお問い合わせください——[\`LICENSE\`](https://github.com/sievepub-2000/octoagent/blob/main/LICENSE) を参照してください。
`;

const aboutMarkdownKo = `**프로젝트 라이선스**

- 기본 오픈소스 조항: **Server Side Public License v1(SSPL v1)**.
- 상업용 라이선스도 제공: **클로즈드 소스 / SaaS / 임베디드 / OEM 라이선스**(조건은 문의 바랍니다).
- 본 프로젝트에는 **Bytedance Ltd.** 의 원본 코드 일부가 포함되어 있으며 **MIT 라이선스** 로 재배포됩니다. 전체 고지는 저장소 루트의 \`NOTICE.md\` 를 참조하세요.
- 전체 조항은 저장소 루트의 \`LICENSE\` 와 \`NOTICE.md\` 에 있습니다.

**작성자 연락처: ${CONTACT_EMAIL}**

=====

**OctoAgent** 는 사무, 비즈니스, 시스템 운영을 위한 강력한 화이트박스 AI 도구입니다. 모든 추론 단계, 모든 도구 호출, 모든 산출물이 추적·감사·재생 가능하여 OpenClaw 와 같은 블랙박스 에이전트와 뚜렷이 대비됩니다.

**핵심 기능**

- 비즈니스 인텔리전스 및 다차원 분석(산업, 경쟁사, 감성, ToB/ToC 조사)
- 신뢰할 수 있는 인용 집계를 갖춘 학술 연구 보고서
- 완전 자동화된 사무 문서 처리(Excel / Word / PPT / PDF / Markdown 변환, 검토, 재작성)
- 시스템 수준 운영 및 IT 런북(원클릭 상태 점검, 구성 감사, 로그 검색, 보안 스캔)
- 데이터베이스 상호작용 및 코드 생성 / 리팩터링 / 디버깅
- 모든 중간 단계가 사용자에게 보이는 멀티 에이전트 작업 오케스트레이션

**화이트박스 약속**

- 모든 도구 호출과 인수가 완전히 투명
- 모든 단계를 일시 중지·취소·편집 가능
- 감사 로그, 관측성 대시보드, 리플레이 내장
- 로컬 우선: 모델·검색·코드 샌드박스·파일 시스템을 모두 로컬에 배포 가능

**대표 시나리오**

사무 자동화 · 비즈니스 실사 · 데이터 분석 보고서 · 학술 문헌 검토 · 시스템 운영 · 보안 감사 · 코드 협업 · 프라이빗 배포

---

**라이선스.** OctoAgent 는 SSPL v1 + 상업용 듀얼 라이선스입니다. 매니지드 서비스, OEM, 임베디드 또는 브랜드 제거 용도의 경우 **${CONTACT_EMAIL}** 로 문의하세요——[\`LICENSE\`](https://github.com/sievepub-2000/octoagent/blob/main/LICENSE) 를 참조하세요.
`;

export const aboutMarkdownByLocale: Record<Locale, string> = {
  "en-US": aboutMarkdownEnUS,
  "ja": aboutMarkdownJa,
  "ko": aboutMarkdownKo,
  "zh-CN": aboutMarkdownZhCN,
  "zh-TW": aboutMarkdownZhTW,
};

export function getAboutMarkdown(locale: Locale): string {
  return aboutMarkdownByLocale[locale] ?? aboutMarkdownEnUS;
}

// Backward-compatible default export (English). The CI license-check and
// any non-localized consumer still resolve the contact email from here.
export const aboutMarkdown = aboutMarkdownEnUS;
