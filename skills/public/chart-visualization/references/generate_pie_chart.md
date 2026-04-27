# generate_pie_chart - Pie Chart

## Overview
Show part-to-whole proportions for a small set of categories.

## Input Fields
### Required
- `data`: array of records with `category` (string) and `value` (number).

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Use a pie chart only when the category count is small and the total-to-part relation matters.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
