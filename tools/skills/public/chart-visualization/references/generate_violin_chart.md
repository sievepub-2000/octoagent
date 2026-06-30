# generate_violin_chart - Violin Chart

## Overview
Combine density shape and distribution summary across categories.

## Input Fields
### Required
- `data`: array of records with `category` (string), `value` (number), and optional `group`.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`, `axisXTitle`, `axisYTitle`.

## Usage Notes
Use enough samples per category so the density estimate is stable.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
