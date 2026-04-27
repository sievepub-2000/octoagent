# generate_radar_chart - Radar Chart

## Overview
Compare one or more profiles across shared indicators.

## Input Fields
### Required
- `indicators`: array of axis definitions such as `name` and optional `max`. `data`: array of series values.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Use radar charts only when all indicators share a comparable scale or a clear normalized range.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
