# generate_line_chart - Line Chart

## Overview
Show change over an ordered dimension such as time or sequence.

## Input Fields
### Required
- `data`: array of records with `time` (or another ordered x value), `value`, and optional `group`.

### Optional
- `smooth`, `stack`, or other series options if supported.
- `style.backgroundColor`, `style.lineWidth`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`, `axisXTitle`, `axisYTitle`.

## Usage Notes
Keep the x-axis ordered and use a line chart only when continuity between points is meaningful.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
