# generate_dual_axes_chart - Dual-Axes Chart

## Overview
Compare two metrics that share one x-axis but require different y-axis scales.

## Input Fields
### Required
- `data`: array of records with one shared x value and two measures, such as `left_value` and `right_value`.

### Optional
- `leftSeriesType` and `rightSeriesType` if mixed bar-line rendering is supported.
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`, `axisXTitle`, `axisYTitle`, `axisY2Title`.

## Usage Notes
Use dual axes sparingly and label both scales clearly to avoid misleading comparisons.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
