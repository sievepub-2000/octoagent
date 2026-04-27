# generate_liquid_chart - Liquid Chart

## Overview
Show a single normalized percentage or progress value as a liquid fill indicator.

## Input Fields
### Required
- `percent`: number in the range `[0, 1]`.

### Optional
- `shape`: for example `circle`, `rect`, `pin`, or `triangle`.
- `style.backgroundColor`, `style.color`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Normalize the percentage before rendering and use one liquid chart per metric.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
