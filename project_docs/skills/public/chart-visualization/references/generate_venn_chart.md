# generate_venn_chart - Venn Chart

## Overview
Show overlap between sets and their intersections.

## Input Fields
### Required
- `data`: array of set objects such as `{ sets: [...], size: number }`.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Use Venn charts only for a small number of sets. Too many set combinations quickly become unreadable.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
