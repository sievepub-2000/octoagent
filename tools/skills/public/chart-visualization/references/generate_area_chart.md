# generate_area_chart - Area Chart

## Overview
Show trends over a continuous dimension such as time, with optional stacking for cumulative contribution.

## Input Fields
### Required
- `data`: array of records with `time` (string), `value` (number), and optional `group` (string) for stacked mode.

### Optional
- `stack`: enable stacked rendering when every record has a `group` field.
- `style.backgroundColor`, `style.lineWidth`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`, `axisXTitle`, `axisYTitle`.

## Usage Notes
Keep the `time` format consistent, for example `YYYY-MM`. In stacked mode, each group should cover the same time points.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
