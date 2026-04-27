# generate_bar_chart - Bar Chart

## Overview
Compare values across categories with horizontal bars.

## Input Fields
### Required
- `data`: array of records with `category` (string) and `value` (number). Optional `group` can be used for grouped bars.

### Optional
- `stack` or grouped-series behavior when `group` is present.
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`, `axisXTitle`, `axisYTitle`.

## Usage Notes
Use bar charts when category labels are long or when category comparison matters more than sequence.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
