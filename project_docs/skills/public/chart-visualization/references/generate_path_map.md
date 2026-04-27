# generate_path_map - Path Map

## Overview
Display routes or movement paths across a map or coordinate space.

## Input Fields
### Required
- `paths`: array of path objects that describe source and destination locations or coordinate sequences.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`, route style options.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Use consistent geographic naming or coordinate systems for every path segment.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
