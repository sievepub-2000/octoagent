# generate_district_map - District Map

## Overview
Display values by district or administrative sub-region on a choropleth-style map.

## Input Fields
### Required
- `data`: array of district records such as `district`/`name` plus `value`.

### Optional
- `map`, `region`, or district-level geographic options when the renderer supports them.
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Use standardized district names so the map can match data records to geographic boundaries reliably.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
