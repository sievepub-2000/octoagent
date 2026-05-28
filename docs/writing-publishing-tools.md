# Writing and Publishing Tool Suite

OctoAgent includes a managed tool suite for articles, novels, papers, and web serials. The tools can be called independently or chained into a full creation-to-publication workflow.

## External Toolchain

| Capability | Upstream project | OctoAgent wrapper |
|---|---|---|
| Agent browser automation | browser-use/browser-use | `writing_toolchain_status`, `browser_publisher` |
| Deterministic browser automation and screenshots | microsoft/playwright | `browser_publisher`, `publication_auditor` |
| WordPress CLI publishing | wp-cli/wp-cli | `wp_cli_publish` |
| PII detection/anonymization | microsoft/presidio | `writing_review_suite` |
| Format conversion | jgm/pandoc | `writing_format_export` |
| Natural-language linting | textlint/textlint | `writing_review_suite` |
| Prose style linting | vale-cli/vale | `writing_review_suite` |

Install or refresh dependencies with:

```bash
scripts/tools/install-writing-publishing-tools.sh
```

Set `OCTOAGENT_INSTALL_HOST_DEPS=1` when the host is allowed to install `php-cli` and `pandoc` through the OS package manager.

## Professional Writing Tool Flow

The bracketed tools requested for writing are exposed as a professional writing suite for articles, novels, papers, and web serials:

1. `novel_project_store` creates and manages the project folder, manifest, chapter files, paper sections, metadata, and publication packages.
2. `writestory` creates a story bible and outline scaffold from a premise, domain, audience, and chapter/section count.
3. `chapter_drafter` creates a chapter or section planning scaffold with beats, synopsis, target length, and style notes.
4. `chapter_writer` stores generated prose as draft, revised, final, or submitted project assets.
5. `webnovel_write` packages a chapter/article/paper with platform metadata, synopsis, tags, and the required publishing flow.
6. `writing_review_suite` runs textlint, Vale, and Presidio-backed checks before export or publication.
7. `writing_format_export` produces HTML, EPUB, DOCX, PDF, or Markdown artifacts through Pandoc.
8. `human_approval_gate` records explicit approval before public submission or account mutation.
9. `browser_publisher` performs Playwright/browser-use-ready dry runs, previews, screenshots, and guarded submit workflows.
10. `wp_cli_publish` creates WordPress posts/pages through WP-CLI, defaulting to dry-run/draft behavior unless approved.
11. `publication_auditor` verifies the published or preview URL with title, visible text, expected text matching, and screenshot evidence.

## Safety Contract

- `browser_publisher` and `wp_cli_publish` require `human_approval_gate` before public submission.
- CAPTCHA, SMS, payment, identity, contract, and platform terms confirmations must be handled by a human.
- Publishing artifacts and approval records are stored under `runtime/system_tools/writing-suite/`.
- Tool-local Python dependencies live under `runtime/system_tools/writing-python/.venv`; Node lint dependencies live under `runtime/tools/writing-node`; standalone binaries live under `runtime/tools/bin`.
