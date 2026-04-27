# generate_histogram_chart - Histogram Chart

## Overview
Show the frequency distribution of a numeric variable.

## Input Fields
### Required
- `data`: array of numeric observations, or records containing a numeric `value` field.

### Optional
- `bins` or bucket count if supported.
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`, `axisXTitle`, `axisYTitle`.

## Usage Notes
Choose a sensible bucket count so the distribution is visible without overfitting noise.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
