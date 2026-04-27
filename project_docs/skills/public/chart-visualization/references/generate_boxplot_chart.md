# generate_boxplot_chart - Boxplot Chart

## Overview
Show median, quartiles, spread, and outliers for one or more categories.

## Input Fields
### Required
- `data`: array of records with `category` (string), `value` (number), and optional `group`.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`, `axisXTitle`, `axisYTitle`.

## Usage Notes
Use a sufficient sample size for each category so quartile statistics are meaningful.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
