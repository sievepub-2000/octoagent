# generate_column_chart - Column Chart

## Overview
Compare values across categories with vertical columns.

## Input Fields
### Required
- `data`: array of records with `category` (string) and `value` (number). Optional `group` can be used for grouped or stacked columns.

### Optional
- `stack` when grouped series should accumulate vertically.
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`, `axisXTitle`, `axisYTitle`.

## Usage Notes
Choose a column chart when category labels are short and the vertical ranking is easy to scan.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
