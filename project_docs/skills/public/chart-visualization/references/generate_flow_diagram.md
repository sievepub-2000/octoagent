# generate_flow_diagram - Flow Diagram

## Overview
Represent a process as nodes and directional links.

## Input Fields
### Required
- `nodes`: array of nodes with `id` and `label`. `edges`: array of links with `source` and `target`.

### Optional
- `layout` or direction options if supported.
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Use stable node IDs and keep the graph acyclic when you want a clear left-to-right or top-to-bottom process view.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
