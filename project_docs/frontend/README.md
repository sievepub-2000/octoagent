# OctoAgent WebUI

The WebUI is a project-first engineering workspace built with Next.js 16, React 19, Tailwind CSS 4, shadcn/ui, TanStack Query, and the LangGraph SDK.

## Product structure

- **Projects** are persistent working directories with repository metadata, instructions, model and permission defaults, memory, and associated tasks.
- **Tasks** are LangGraph chat threads. A task may belong to one project through `project_id`.
- **Context panel** contains Activity, generated Files, and live System resource/service health.
- **Settings** contains advanced model, agent, skill, MCP, channel, runtime, memory, and update controls. These are intentionally absent from primary navigation.
- Legacy `/workspace/tasks/*` and `/workspace/workflows/*` routes redirect to Projects. Runtime orchestration remains internal.

## Design rules

- Use shadcn-style components and familiar controls.
- Prefer flat bordered surfaces, restrained color, and compact engineering-tool density.
- Do not add workflow builders, decorative gradients, nested card walls, or marketing-style welcome art to the workspace.
- Keep the main shell stable: project/task navigation on the left, work in the center, contextual detail on the right.

## Verification

```bash
pnpm exec eslint src --max-warnings=0
pnpm exec tsc --noEmit
pnpm run build
```

Local production entry is served through nginx at `http://192.168.110.2:19800` on machine 2.
