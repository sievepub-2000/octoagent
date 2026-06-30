# generate_organization_chart - Organization Chart

## Overview
Display reporting structure or hierarchy in a formal org-chart layout.

## Input Fields
### Required
- `nodes`: array of people or roles with unique `id`, `label`/`name`, and parent linkage such as `parentId`.

### Optional
- `layout` direction if supported.
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Provide a clean hierarchy with one parent per node unless the chart engine explicitly supports matrix structures.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
