# generate_scatter_chart - Scatter Chart

## Overview
Show the relationship between two numeric variables.

## Input Fields
### Required
- `data`: array of points with `x` and `y`, plus optional `group` or `label`.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`, `axisXTitle`, `axisYTitle`.

## Usage Notes
Use scatter plots to reveal correlation, clusters, or outliers. Add groups when color coding matters.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
