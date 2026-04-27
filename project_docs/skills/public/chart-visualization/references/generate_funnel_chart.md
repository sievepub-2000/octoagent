# generate_funnel_chart - Funnel Chart

## Overview
Show drop-off across sequential stages such as conversion or pipeline flow.

## Input Fields
### Required
- `data`: array of stage objects with `stage` (string) and `value` (number).

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Order stages from largest to smallest or from first step to last step so conversion loss is immediately visible.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
