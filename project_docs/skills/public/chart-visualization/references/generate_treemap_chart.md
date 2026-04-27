# generate_treemap_chart - Treemap Chart

## Overview
Show hierarchical part-to-whole relationships as nested rectangles.

## Input Fields
### Required
- `data`: hierarchical data or records that can be grouped into parent-child structure with values.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Treemaps work best when every node has a value and the hierarchy is not too deep.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
