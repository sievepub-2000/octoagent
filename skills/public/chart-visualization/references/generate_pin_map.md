# generate_pin_map - Pin Map

## Overview
Place point markers on a map to show specific locations and optional values.

## Input Fields
### Required
- `points`: array of locations with fields such as `name`, coordinates, and optional `value`.

### Optional
- `pinStyle`, `label`, or marker options if supported.
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Use valid coordinates or standardized place names and keep labels concise to avoid clutter.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
