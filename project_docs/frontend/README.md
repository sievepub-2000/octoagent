# OctoAgent Frontend

OctoAgent provides a minimal and flexible workspace interface built on the current repository architecture.

## Tech Stack

- **Framework**: [Next.js 16](https://nextjs.org/) with [App Router](https://nextjs.org/docs/app)
- **UI**: [React 19](https://react.dev/), [Tailwind CSS 4](https://tailwindcss.com/), [Shadcn UI](https://ui.shadcn.com/), [MagicUI](https://magicui.design/) and [React Bits](https://reactbits.dev/)
- **AI Integration**: [LangGraph SDK](https://www.npmjs.com/package/@langchain/langgraph-sdk) and [Vercel AI Elements](https://vercel.com/ai-sdk/ai-elements)

## Quick Start

### Prerequisites

- Node.js 22+
- pnpm 10.26.2+

### Installation

```bash
# Install dependencies
pnpm install

# Copy environment variables from the repository root
cp ../.env.example ../.env
# Edit .env with your configuration
```

### Development

```bash
# Start development server
pnpm dev

# The app will be available at http://localhost:19830
```

### Build

```bash
# Type check
pnpm typecheck

# Lint
pnpm lint

# Build for production
pnpm build

# Start production server
pnpm start
```

## Site Map

```
├── /                    # Landing page
├── /workspace           # Workspace entry redirect
├── /workspace/chats     # Chat list
├── /workspace/chats/new # New chat page
├── /workspace/chats/[thread_id]   # Default assistant chat
├── /workspace/config/models       # Model management
├── /workspace/config/channels     # Channel runtime status and restart
├── /workspace/tasks/[task_id]     # Task workspace detail (primary route)
├── /workspace/workflows/[task_id] # Workflow detail compatibility route
├── /workspace/agents    # Custom agent gallery
└── /workspace/agents/[agent_name]/chats/[thread_id] # Agent-specific chat
```

## Configuration

### Environment Variables

Key environment variables (see `.env.example` for full list):

```bash
# Required for production builds
BETTER_AUTH_SECRET="generate-a-random-secret"
BETTER_AUTH_BASE_URL="http://localhost:19830"

# Backend API URLs (optional, uses nginx proxy by default)
NEXT_PUBLIC_BACKEND_BASE_URL="http://localhost:19832"
# LangGraph API URLs (optional, uses nginx proxy by default)
NEXT_PUBLIC_LANGGRAPH_BASE_URL="http://localhost:19824"
```

Notes:

- `BETTER_AUTH_SECRET` is required when `NODE_ENV=production`, so `pnpm build` will fail without it.
- Generate a local secret with `openssl rand -base64 32`.
- Set `BETTER_AUTH_BASE_URL` to the public frontend origin used for auth callbacks and redirects.
- `SKIP_ENV_VALIDATION=1 pnpm build` is available for constrained Docker or CI workflows, but it should not replace a real secret in normal deployments.

## Project Structure

```
src/
├── app/                    # Next.js App Router pages
│   ├── api/                # API routes
│   ├── workspace/          # Main workspace pages
│   └── mock/               # Mock/demo pages
├── components/             # React components
│   ├── ui/                 # Reusable UI components
│   ├── workspace/          # Workspace-specific components
│   ├── landing/            # Landing page components
│   └── ai-elements/        # AI-related UI elements
├── core/                   # Core business logic
│   ├── api/                # API client & data fetching
│   │   └── http.ts         # Shared backend HTTP interface layer
│   ├── artifacts/          # Artifact management
│   ├── config/              # App configuration
│   ├── i18n/               # Internationalization
│   ├── mcp/                # MCP integration
│   ├── messages/           # Message handling
│   ├── models/             # Data models & types
│   ├── channels/           # Channel runtime status/restart client
│   ├── settings/           # User settings
│   ├── setup/              # Onboarding/setup API client and hooks
│   ├── skills/             # Skills system
│   ├── system-execution/   # System-level execution capability clients
│   ├── threads/            # Thread management
│   ├── todos/              # Todo system
│   └── utils/              # Utility functions
├── hooks/                  # Custom React hooks
├── lib/                    # Shared libraries & utilities
├── server/                 # Server-side helpers
│   └── better-auth/        # Authentication scaffolding
└── styles/                 # Global styles
```

## Scripts

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start development server with Turbopack |
| `pnpm build` | Build for production |
| `pnpm start` | Start production server |
| `pnpm lint` | Run ESLint |
| `pnpm lint:fix` | Fix ESLint issues |
| `pnpm typecheck` | Run TypeScript type checking |
| `pnpm check` | Run both lint and typecheck |

## Development Notes

- Uses pnpm workspaces (see `packageManager` in package.json)
- Turbopack enabled by default in development for faster builds
- Environment validation can be skipped with `SKIP_ENV_VALIDATION=1` (useful for Docker)
- Backend API URLs are optional; nginx proxy is used by default in development
- Workspace settings currently include appearance, bootstrap, system guard, system execution, notification, memory, and about sections
- Feature modules under `src/core/*/api.ts` should prefer the shared transport helpers in `src/core/api/http.ts` instead of direct ad hoc `fetch`
- The first-run setup wizard should consume the typed setup client under `src/core/setup` instead of component-local HTTP calls

## Rowboat Benchmark Integration Direction

Rowboat is now a direct benchmark for the next OctoAgent frontend layer. The goal is not to copy its styling, but to match its product coherence: workflow authoring, runtime inspection, debugging, and assistant guidance should eventually live in one connected operator surface.

Frontend implications now in scope:

1. The task/workflow detail experience should evolve toward a studio layout with panelized runtime state, logs, handoffs, and builder assistance.
2. Future builder/copilot UI should be colocated with workflow context rather than presented as detached planning text.
3. Channel settings should evolve from isolated configuration status pages toward workflow-binding and ingress-observability surfaces.
4. New runtime panels should preserve the current OctoAgent visual baseline while increasing information density and observability.

## License

MIT License. See [LICENSE](../LICENSE) for details.

## Documentation Navigation

- [Repository Documentation Index](../docs/README.md)
- [Root README](../README.md)
- [Backend README](../backend/README.md)
