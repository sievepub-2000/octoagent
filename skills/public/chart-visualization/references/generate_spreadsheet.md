# generate_spreadsheet - Spreadsheet

## Overview
Render structured tabular data as a spreadsheet-style view.

## Input Fields
### Required
- `columns`: column definitions. `rows`: array of row records or cell values.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture` if the renderer supports it.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Keep column names explicit and use tabular output when the user needs scanning, sorting, or exact values.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
