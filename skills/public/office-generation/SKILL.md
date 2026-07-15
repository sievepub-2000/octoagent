---
name: office-generation
description: Generate real Word, Excel, PowerPoint, PDF, and Markdown files from a structured JSON specification and save them in the current conversation output directory.
---

# Office Generation

Use this Skill for `.docx`, `.xlsx`, `.pptx`, `.pdf`, and `.md` deliverables.

1. Query Tools Hub first. Prefer this bundled Skill when its supported formats meet the request; do not install a second document library ad hoc.
2. Write a UTF-8 JSON specification into the current conversation workspace. Use `title` plus `sections`; Excel may use `headers` and `rows`, and PowerPoint may use `slides` with `title` and `bullets`.
3. Invoke `scripts/generate.py --format FORMAT --spec SPEC.json --output-file OUTPUT`. The output path must be the active conversation's `outputs` directory so it appears in the right-side Files panel and its download endpoint.
4. Read the generated file back with the appropriate parser and report its absolute path and byte size. For layout-sensitive work, render and inspect it before delivery.

Example:

```bash
python skills/public/office-generation/scripts/generate.py \
  --format docx \
  --spec workspace/default/threads/THREAD/workspace/document.json \
  --output-file workspace/default/threads/THREAD/outputs/report.docx
```

Never write generated deliverables into the source tree, Skill directory, dependency environment, or managed-tool installation root.
