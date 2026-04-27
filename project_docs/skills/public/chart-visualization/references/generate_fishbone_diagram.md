# generate_fishbone_diagram - Fishbone Diagram

## Overview
Map root causes into major branches for structured cause-and-effect analysis.

## Input Fields
### Required
- `problem`: the main issue to analyze. `branches`: array of branch objects, each with a branch label and child causes.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Keep branch labels short and group causes into a small number of high-level categories.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
