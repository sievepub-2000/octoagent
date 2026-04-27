# generate_mind_map - Mind Map

## Overview
Organize a topic into a centered tree of subtopics and related ideas.

## Input Fields
### Required
- `root`: the central topic. `children`: nested child nodes that expand the topic tree.

### Optional
- `layout` or direction options if supported.
- `style.backgroundColor`, `style.palette`, `style.texture`.
- `theme`, `width`, `height`, `title`.

## Usage Notes
Keep each node label short. If the map becomes too dense, split it into multiple smaller maps.

## Return Value
- Returns a rendered chart asset URL and keeps the effective configuration in `_meta.spec` for downstream reuse or tracing.
