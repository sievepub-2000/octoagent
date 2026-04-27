# generate_network_graph - Network Graph

## Overview
Visualize entities and their relationships as a node-link network.

## Input Fields
### Required
- `nodes`: array with `id` and optional `label` or `group`. `edges`: array with `source` and `target`.

### Optional
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Use meaningful node groups or colors when the graph contains clusters or roles.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
