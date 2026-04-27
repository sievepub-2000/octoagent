# generate_sankey_chart - Sankey Chart

## Overview
Show flow magnitude between stages or categories.

## Input Fields
### Required
- `nodes`: array of node labels or IDs. `links`: array with `source`, `target`, and `value`.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Keep node naming stable and use a Sankey chart when flow volume matters as much as flow direction.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
