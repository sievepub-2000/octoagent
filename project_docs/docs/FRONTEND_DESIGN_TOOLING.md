# Frontend Design Tooling Baseline

This document defines the recommended baseline for frontend UI generation, iteration, and review in OctoAgent.

## Recommended Stack

Use three layers instead of trying to force one tool to do everything:

1. Component baseline: `shadcn` + local `src/components/ui/*`
2. Motion baseline: `motion/react`
3. Design guidance and review: repository skills plus optional external fetch/research tools

## Why This Split

### 1. Component foundation: shadcn

The repository already uses shadcn-style primitives under [frontend/src/components/ui](../frontend/src/components/ui) and now has an explicit CLI baseline through [frontend/components.json](../../frontend/components.json).

Use shadcn for:

- adding or regenerating standard primitives
- keeping alias paths and CSS-variable assumptions consistent
- preserving the repo's Radix + Tailwind v4 structure

Use the CLI from [frontend](../../frontend):

```bash
pnpm exec shadcn add button
pnpm exec shadcn add dialog
```

Do not treat shadcn as the design system by itself. It is the primitive/component substrate.

### 2. Animation foundation: Motion

The repository already uses `motion/react` in multiple UI surfaces, and `motion` is already installed in [frontend/package.json](../../frontend/package.json).

Do not add `framer-motion` separately unless a third-party dependency explicitly requires the old package name. Today, `motion` and `framer-motion` are on the same version line, so installing both only duplicates runtime surface and creates ambiguity.

Use Motion for:

- page-enter and section-enter transitions
- inspector and panel transitions
- animated counters, shimmer, and progressive reveal
- high-value interaction states that are hard to express with CSS-only animation

### 3. Guidance/review foundation: Skills first, MCP second

For UI creation and critique, use skills as the primary reasoning layer and MCP-like external fetch as the secondary support layer.

Repository-local design skills already exist under:

- [project_docs/skills/public/frontend-design/SKILL.md](../skills/public/frontend-design/SKILL.md)
- [project_docs/skills/public/web-design-guidelines/SKILL.md](../skills/public/web-design-guidelines/SKILL.md)

Recommended division:

- `frontend-design`: generate or refine distinctive UI direction
- `web-design-guidelines`: review finished UI against stricter web-interface heuristics
- MCP/Web fetch/search: only for external references, docs, examples, icons, or standards that are not already captured locally

## Practical Recommendation

When starting a new frontend slice:

1. Start from existing local primitives in [frontend/src/components/ui](../frontend/src/components/ui).
2. Use shadcn CLI only when a primitive is missing or needs standardized regeneration.
3. Use `motion/react` for meaningful animation moments.
4. Use local design skills to decide aesthetic direction and review quality.
5. Use external fetch/MCP only for missing reference material, not as the primary UI system.

## Current 3.0.3 UI Direction

The current workspace baseline is no longer the earlier green-accent shell. New UI work should preserve these repo-level decisions unless a change explicitly replaces them end to end:

- brand artwork lives under [frontend/public/images](../../frontend/public/images) and is consumed through [frontend/src/components/brand/octo-mark.tsx](../../frontend/src/components/brand/octo-mark.tsx)
- the primary palette is warm ivory, coral, and soft gold rather than generic blue/purple SaaS defaults
- shared panel treatment comes from `.octo-panel` and canvas texture from `.octo-grid` in [frontend/src/styles/globals.css](../../frontend/src/styles/globals.css)
- workflow views should feel like a light editorial canvas, with system-card nodes, minimap, and graph controls rather than plain boxes on a blank background
- multilingual typography should stay compact, refined, and highly legible; avoid reverting to heavier default stacks without a deliberate design reason

## Validation Hooks

Frontend design changes in this repository should preserve the release validation path, not just visual appearance.

- workspace settings can now be opened directly with `?settings=<section>` on workspace routes; this is a supported deep-link for operator flows and smoke automation
- real browser validation lives in [backend/scripts/run_webui_smoke.py](../../backend/scripts/run_webui_smoke.py)
- release validation must continue to pass through `make release-precheck`, not only isolated `pnpm` checks

## Decision Summary

The correct baseline is:

- UI primitives: `shadcn`
- animation: `motion/react`
- design generation/review workflow: `skills`
- external augmentation: `MCP` or web fetch only when needed

That is more stable than trying to use skills or MCP as the actual component foundation.